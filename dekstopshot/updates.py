"""One quiet, asynchronous check of the public GitHub stable release feed.

Only release metadata is requested. This module never downloads installers,
opens URLs, sends screenshots, or installs updates.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from http.client import HTTPException
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot

from .version import REPOSITORY, VERSION

log = logging.getLogger("dekstopshot")

LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
REQUEST_TIMEOUT = 5.0
MAX_RESPONSE_BYTES = 256 * 1024
_STABLE_VERSION = re.compile(r"[vV]?(0|[1-9][0-9]{0,7})\.(0|[1-9][0-9]{0,7})(?:\.(0|[1-9][0-9]{0,7}))?")


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    url: str
    tag: str


def parse_version(value: str) -> tuple[int, int, int] | None:
    """Compare stable major.minor[.patch] versions; prereleases are not offered."""
    if not isinstance(value, str):
        return None
    match = _STABLE_VERSION.fullmatch(value)
    if match is None:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def release_from_metadata(data: object, current_version: str) -> ReleaseInfo | None:
    """Accept a newer stable release only from this repository's GitHub page."""
    current = parse_version(current_version)
    if current is None or not isinstance(data, dict):
        return None
    if data.get("draft") is not False or data.get("prerelease") is not False:
        return None
    tag = data.get("tag_name")
    version = parse_version(tag)
    if version is None or version <= current:
        return None
    url = data.get("html_url")
    if not isinstance(url, str):
        return None
    # The accepted tag alphabet is already restricted to stable numeric versions.
    # Exact equality rejects credentials, ports, redirects, encoded paths, and
    # control characters as well as URLs to a different host/repository.
    if url != f"https://github.com/{REPOSITORY}/releases/tag/{tag}":
        return None
    return ReleaseInfo(".".join(map(str, version)), url, tag)


def check_for_update(current_version: str = VERSION, *, opener=None) -> ReleaseInfo | None:
    """Read bounded public metadata with standard TLS verification and a timeout.

    Network errors, unavailable releases, invalid payloads, and rate limits are
    normal here: they leave startup unaffected and produce no UI notification.
    ``opener`` is injectable for tests; no authentication credentials are used.
    """
    if parse_version(current_version) is None:
        return None
    request = Request(LATEST_RELEASE_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"DekstopShot/{VERSION}",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with (opener or urlopen)(request, timeout=REQUEST_TIMEOUT) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            log.info("Update metadata exceeded the response limit")
            return None
        return release_from_metadata(json.loads(payload), current_version)
    except HTTPError as error:
        # HTTPError may own a response stream even when urlopen raises it.
        try:
            log.info("Update check unavailable (HTTP %s)", error.code)
        finally:
            error.close()
    except (OSError, HTTPException, ValueError, TypeError, RecursionError) as error:
        log.info("Update check unavailable: %s", error)
    return None


class _JobSignals(QObject):
    # Deliberately unparented: the worker owns this object until it returns,
    # even if the Controller/checker QObject has already been destroyed.
    completed = Signal(object)


class _UpdateJob(QRunnable):
    def __init__(self, current_version: str, cancelled: threading.Event,
                 check: Callable[[str], ReleaseInfo | None]):
        super().__init__()
        self.current_version = current_version
        self.cancelled = cancelled
        self.check = check
        self.signals = _JobSignals()

    def run(self):
        if self.cancelled.is_set():
            return
        try:
            release = self.check(self.current_version)
        except Exception:  # Background boundary: unexpected failures must not affect startup.
            log.exception("Unexpected update check failure")
            release = None
        if not self.cancelled.is_set():
            try:
                self.signals.completed.emit(release)
            except RuntimeError:
                # The application may have already destroyed its Qt objects.
                log.debug("Update delivery skipped during application shutdown")


class UpdateChecker(QObject):
    """Start at most once; deliver results on the Qt GUI thread.

    ``close()`` suppresses any pending result and finishes immediately. An
    already-running HTTP call is allowed to reach its bounded network timeout.
    Connect ``available`` before ``start`` and close this checker before quit.
    """

    available = Signal(object)  # ReleaseInfo
    finished = Signal()

    def __init__(self, parent: QObject | None = None, *, check=None, pool: QThreadPool | None = None):
        super().__init__(parent)
        self._check = check or check_for_update
        self._pool = pool or QThreadPool.globalInstance()
        self._cancelled = threading.Event()
        self._job: _UpdateJob | None = None
        self._started = False
        self._finished = False
        self._closed = False

    @property
    def is_running(self) -> bool:
        return self._started and not self._finished

    def start(self, current_version: str = VERSION) -> bool:
        if self._started or self._closed:
            return False
        self._started = True
        self._job = _UpdateJob(current_version, self._cancelled, self._check)
        self._job.signals.completed.connect(self._complete, Qt.ConnectionType.QueuedConnection)
        self._pool.start(self._job)
        return True

    @Slot(object)
    def _complete(self, release):
        if self._closed:
            return
        self._job = None
        if isinstance(release, ReleaseInfo):
            self.available.emit(release)
        self._finish()

    def _finish(self):
        if self._started and not self._finished:
            self._finished = True
            self.finished.emit()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._cancelled.set()
        self._finish()
