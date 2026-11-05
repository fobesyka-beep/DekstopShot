from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from PySide6.QtCore import QStandardPaths
from PySide6.QtGui import QImage

from dekstopshot.capture import encode_frame
from dekstopshot.core import Frame
from dekstopshot.pictures import pictures_directory, save_png


def test_picture_directory_uses_system_location_without_creating_it(tmp_path, monkeypatch):
    redirected = tmp_path / "OneDrive – Личный" / "Фотографии"
    requested = []

    def resolve(location):
        requested.append(location)
        return str(redirected)

    monkeypatch.setattr("dekstopshot.pictures.QStandardPaths.writableLocation", resolve)
    assert pictures_directory() == redirected / "DekstopShot"
    assert requested == [QStandardPaths.StandardLocation.PicturesLocation]
    assert not redirected.exists()


def test_missing_system_picture_location_is_reported_without_fallback(monkeypatch):
    monkeypatch.setattr("dekstopshot.pictures.QStandardPaths.writableLocation", lambda _: "")
    with pytest.raises(OSError, match="Изображения"):
        pictures_directory()


def test_saved_png_has_the_exact_clipboard_pixels_and_orientation(tmp_path, qapp):
    frame = Frame(2, 2, bytes([0, 0, 255, 0, 0, 255, 0, 0,
                              255, 0, 0, 0, 255, 255, 255, 0]))
    payload = encode_frame(frame)
    directory = tmp_path / "new" / "DekstopShot"
    saved = save_png(payload.png, directory=directory)
    assert saved.parent == directory
    assert saved.read_bytes() == payload.png
    image = QImage(str(saved))
    assert image.size().width() == image.size().height() == 2
    assert [image.pixelColor(x, y).getRgb() for y in range(2) for x in range(2)] == [
        (255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (255, 255, 255, 255)]


def test_simultaneous_same_timestamp_saves_never_replace_files(tmp_path):
    stamp = datetime(2026, 11, 5, 12, 34, 56, 123456)

    def write(index):
        data = f"encoded-png-{index}".encode()
        return save_png(data, directory=tmp_path, captured_at=stamp), data

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(write, range(8)))
    assert len({path for path, _ in results}) == 8
    assert all(path.read_bytes() == data for path, data in results)
    assert len(list(tmp_path.glob("*.png"))) == 8


def test_failed_write_removes_only_its_partial_file(tmp_path, monkeypatch):
    existing = tmp_path / "already-here.png"
    existing.write_bytes(b"original")

    def fail(_):
        raise OSError("disk full")

    monkeypatch.setattr("dekstopshot.pictures.os.fsync", fail)
    with pytest.raises(OSError, match="disk full"):
        save_png(b"partial", directory=tmp_path)
    assert list(tmp_path.iterdir()) == [existing]
    assert existing.read_bytes() == b"original"
