import json
import threading
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QThread, QThreadPool
from PySide6.QtTest import QTest

from dekstopshot.updates import (
    LATEST_RELEASE_URL,
    MAX_RESPONSE_BYTES,
    REQUEST_TIMEOUT,
    ReleaseInfo,
    UpdateChecker,
    check_for_update,
    parse_version,
    release_from_metadata,
)
from dekstopshot.version import REPOSITORY


def metadata(tag="v1.2.0", **changes):
    result = {"tag_name": tag, "html_url": f"https://github.com/{REPOSITORY}/releases/tag/{tag}",
              "draft": False, "prerelease": False}
    result.update(changes)
    return result


@pytest.mark.parametrize("current,latest,newer", [
    ("1.1.0", "v1.1", False),
    ("1.1", "v1.1.0", False),
    ("v1.1.0", "1.1.1", True),
    ("1.1.9", "v1.10.0", True),
    ("1.10.0", "v1.2.0", False),
])
def test_stable_versions_compare_numerically(current, latest, newer):
    release = release_from_metadata(metadata(latest), current)
    assert (release is not None) is newer
    if release:
        assert release.tag == latest
        assert parse_version(release.version) == parse_version(latest)


@pytest.mark.parametrize("changes", [
    {"draft": True}, {"prerelease": True}, {"tag_name": "v1.2.0-beta.1"},
    {"tag_name": "latest"}, {"tag_name": None}, {"tag_name": "v01.2.0"},
    {"html_url": "https://example.com/update.exe"},
    {"html_url": f"http://github.com/{REPOSITORY}/releases/tag/v1.2.0"},
    {"html_url": f"https://github.com.evil.example/{REPOSITORY}/releases/tag/v1.2.0"},
    {"html_url": "https://github.com/another/repository/releases/tag/v1.2.0"},
    {"html_url": f"https://github.com/{REPOSITORY}/releases/tag/v1.2.0?redirect=external"},
    {"html_url": f"https://github.com/{REPOSITORY}/releases/tag/v1.2.0#external"},
    {"html_url": f"https://github.com/{REPOSITORY}/releases/tag/v9.9.9"},
    {"html_url": f"https://github.com/{REPOSITORY}/releases/tag/v1.2.0\n"},
    {"html_url": "https://[invalid"},
])
def test_unpublished_prerelease_and_untrusted_release_links_are_ignored(changes):
    assert release_from_metadata(metadata(**changes), "1.1.0") is None


class Response:
    def __init__(self, payload):
        self.payload = payload
        self.read_limit = None
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def read(self, limit):
        self.read_limit = limit
        return self.payload[:limit]


def test_public_request_has_timeout_bounded_body_and_no_authentication():
    response = Response(json.dumps(metadata()).encode())
    requests = []

    def opener(request, timeout):
        requests.append((request, timeout))
        return response

    release = check_for_update("1.1.0", opener=opener)
    assert release == ReleaseInfo("1.2.0", metadata()["html_url"], "v1.2.0")
    request, timeout = requests[0]
    assert request.full_url == LATEST_RELEASE_URL
    assert timeout == REQUEST_TIMEOUT
    headers = {name.lower(): value for name, value in request.header_items()}
    assert "authorization" not in headers and "cookie" not in headers
    assert headers["accept"] == "application/vnd.github+json"
    assert headers["user-agent"].startswith("DekstopShot/")
    assert response.read_limit == MAX_RESPONSE_BYTES + 1
    assert response.closed


@pytest.mark.parametrize("payload", [b"not json", b"[]", b"\xff", b"x" * (MAX_RESPONSE_BYTES + 1)],
                         ids=["invalid-json", "wrong-shape", "invalid-encoding", "oversized"])
def test_invalid_or_oversized_responses_leave_startup_unaffected(payload):
    response = Response(payload)
    assert check_for_update("1.1.0", opener=lambda *args, **kwargs: response) is None
    assert response.closed


@pytest.mark.parametrize("error", [
    URLError("offline"), TimeoutError("timed out"), HTTPException("Invalid response"),
    HTTPError(LATEST_RELEASE_URL, 404, "No published release", {}, None),
    HTTPError(LATEST_RELEASE_URL, 403, "Rate limited", {}, None),
    HTTPError(LATEST_RELEASE_URL, 429, "Rate limited", {}, None),
])
def test_network_and_release_errors_are_quiet(error):
    def opener(*_args, **_kwargs):
        raise error

    assert check_for_update("1.1.0", opener=opener) is None


def wait_until(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


def test_async_checker_runs_off_gui_thread_and_delivers_once_on_gui_thread(qapp):
    release = ReleaseInfo("1.2.0", metadata()["html_url"], "v1.2.0")
    workers = []
    delivered = []
    finished = []

    def check(version):
        workers.append((version, QThread.currentThread()))
        return release

    checker = UpdateChecker(check=check)
    checker.available.connect(lambda value: delivered.append((value, QThread.currentThread())))
    checker.finished.connect(lambda: finished.append(True))
    assert checker.start("1.1.0")
    assert not checker.start("1.1.0")
    wait_until(lambda: bool(finished))
    assert workers[0][0] == "1.1.0"
    assert workers[0][1] != qapp.thread()
    assert delivered == [(release, qapp.thread())]
    assert finished == [True]
    assert not checker.is_running
    checker.close()
    assert finished == [True]


def test_closing_checker_drops_inflight_result_without_waiting_for_network(qapp):
    entered = threading.Event()
    unblock = threading.Event()
    pool = QThreadPool()
    delivered = []
    finished = []

    def check(_version):
        entered.set()
        assert unblock.wait(2)
        return ReleaseInfo("1.2.0", metadata()["html_url"], "v1.2.0")

    checker = UpdateChecker(check=check, pool=pool)
    checker.available.connect(delivered.append)
    checker.finished.connect(lambda: finished.append(True))
    checker.start("1.1.0")
    try:
        wait_until(entered.is_set)
        checker.close()
        assert not checker.is_running
        assert finished == [True]
        assert not checker.start("1.1.0")
    finally:
        unblock.set()
        assert pool.waitForDone(2000)
    qapp.processEvents()
    assert not delivered
    assert finished == [True]


def test_destroyed_checker_is_not_called_by_worker_finishing_later(qapp):
    entered = threading.Event()
    unblock = threading.Event()
    pool = QThreadPool()
    delivered = []

    def check(_version):
        entered.set()
        assert unblock.wait(2)
        return ReleaseInfo("1.2.0", metadata()["html_url"], "v1.2.0")

    checker = UpdateChecker(check=check, pool=pool)
    checker.available.connect(delivered.append)
    checker.start("1.1.0")
    try:
        wait_until(entered.is_set)
        checker.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    finally:
        unblock.set()
        assert pool.waitForDone(2000)
    qapp.processEvents()
    assert not delivered
