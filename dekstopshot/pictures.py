"""Optional local PNG copies, using the user's configured Windows Pictures folder."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QStandardPaths, Signal


def pictures_directory() -> Path:
    """Resolve on demand so disabled saving never touches the Pictures directory."""
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
    if not location:
        raise OSError("Не удалось определить системную папку «Изображения».")
    return Path(location) / "DekstopShot"


def save_png(png: bytes, *, directory: Path | None = None,
             captured_at: datetime | None = None) -> Path:
    """Write the encoded clipboard PNG losslessly without replacing existing files."""
    directory = pictures_directory() if directory is None else directory
    directory.mkdir(parents=True, exist_ok=True)
    stamp = (captured_at or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S-%f")
    for index in range(10_000):
        suffix = "" if index == 0 else f"-{index + 1}"
        destination = directory / f"DekstopShot_{stamp}{suffix}.png"
        try:
            stream = destination.open("xb")
        except FileExistsError:
            continue
        try:
            with stream:
                stream.write(png)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            # Only this exclusively created file belongs to us; existing files
            # were skipped above and are never removed or overwritten.
            destination.unlink(missing_ok=True)
            raise
        return destination
    raise FileExistsError("Could not allocate a unique screenshot filename.")


class PictureSaveSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)


class PictureSaveJob(QRunnable):
    """Keep slow or redirected Pictures-folder writes off the GUI thread."""

    def __init__(self, png: bytes):
        super().__init__()
        self.png = png
        self.signals = PictureSaveSignals()

    def run(self):
        try:
            path = save_png(self.png)
        except Exception as error:  # Worker boundary; clipboard is already published.
            self.signals.failed.emit(str(error))
        else:
            self.signals.succeeded.emit(path)
