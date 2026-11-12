"""Opt-in real Windows checks; creates only its own temporary test windows.

Run via python main.py --self-test [--clipboard] or the built exe --self-test.
The optional clipboard check replaces the clipboard with a synthetic 2x2 image.
Desktop/window captures stay in memory; the JSON report contains no image data.
The PNG-file check uses only a synthetic pattern in a temporary directory.
This does not test physical keyboard input, external application paste, or the Controller GUI.
"""

from __future__ import annotations

import argparse
import ctypes as C
import json
import os
import platform
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes as W
from datetime import datetime, timezone
from pathlib import Path

from .version import VERSION

ROOT = Path.cwd() if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clipboard", action="store_true", help="Test clipboard using a synthetic image")
    parser.add_argument("--show-target", action="store_true", help="Keep the synthetic target open for manual capture")
    parser.add_argument("--output", type=Path, default=ROOT / ".validation" / "windows-smoke.json")
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        parser.error("This diagnostic requires an interactive Windows desktop")

    # This is a live Windows diagnostic even when pytest/offscreen was used earlier.
    os.environ["QT_QPA_PLATFORM"] = "windows"
    from PySide6.QtCore import QCoreApplication, QEvent, Qt
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QApplication, QWidget

    from .capture import capture_window, encode_frame
    from .core import Frame, Hotkey, WindowTarget
    from .native import WindowsAPI
    from .pictures import pictures_directory, save_png

    api = WindowsAPI()
    api.enable_dpi()
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    results = []

    def record(name, action):
        started = time.monotonic()
        try:
            detail = action()
            result = {"name": name, "status": "passed", "detail": detail}
        except Exception as error:
            result = {"name": name, "status": "failed", "error": f"{type(error).__name__}: {error}"}
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        results.append(result)
        print(json.dumps(result, ensure_ascii=True), flush=True)

    def pump(milliseconds=150):
        deadline = time.monotonic() + milliseconds / 1000
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)

    class PatternWindow(QWidget):
        def __init__(self, solid=False):
            super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
            self.solid = solid
            self.setWindowTitle("DekstopShot diagnostic cover" if solid else "DekstopShot validation target")
            self.resize(400, 300)

        def paintEvent(self, _event):
            painter = QPainter(self)
            if self.solid:
                painter.fillRect(self.rect(), QColor(180, 35, 200))
                return
            w, h = self.width() // 2, self.height() // 2
            for x, y, color in ((0, 0, (235, 35, 45)), (w, 0, (35, 220, 55)),
                                (0, h, (40, 65, 235)), (w, h, (235, 215, 35))):
                painter.fillRect(x, y, w, h, QColor(*color))

    pattern = PatternWindow()
    cover = PatternWindow(solid=True)
    screen = app.primaryScreen()
    pattern.move(screen.availableGeometry().center() - pattern.rect().center())
    pattern.show()
    pump(300)
    hwnd = int(pattern.winId())
    executable, started = api._process_details(os.getpid())
    target = WindowTarget(hwnd, os.getpid(), started, pattern.windowTitle(), executable)

    if args.show_target:
        metadata = {"hwnd": hwnd, "pid": os.getpid(), "process_start": started,
                    "title": pattern.windowTitle(), "executable": executable,
                    "logical_width": pattern.width(), "logical_height": pattern.height(),
                    "dpi_scale": pattern.devicePixelRatio()}
        metadata_path = ROOT / ".validation" / "target.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Target ready: {metadata_path}", flush=True)
        return app.exec()

    def gdi():
        monitors = api.monitors()
        assert monitors, "No physical monitors returned"
        captures = []
        for monitor in monitors:
            frame = api.capture(monitor)
            assert (frame.width, frame.height) == (monitor.width, monitor.height)
            # Sample only numerical image characteristics, never persist desktop pixels.
            sample = frame.bgra[::max(4, len(frame.bgra) // 4096)]
            captures.append({"width": frame.width, "height": frame.height,
                             "left": monitor.left, "top": monitor.top,
                             "sample_varies": len(set(sample)) > 1})
        return {"monitors": captures, "qt_dpi_scales": [s.devicePixelRatio() for s in app.screens()]}

    def hotkeys():
        candidate = Hotkey(0x87, 7)  # Ctrl+Alt+Shift+F24: avoid reserving everyday input.
        identifier = 0x5D10
        api.register_hotkey(identifier, candidate)

        def attempt(expect_conflict):
            other = WindowsAPI()
            try:
                other.register_hotkey(identifier + 1, candidate)
            except OSError as error:
                assert expect_conflict, f"Binding stayed unavailable after release: {error}"
                assert error.errno == 1409, f"Unexpected registration error: {error}"
                return "conflict_1409"
            else:
                try:
                    assert not expect_conflict, "Another thread acquired an already reserved binding"
                    return "registered_after_release"
                finally:
                    other.unregister_hotkey(identifier + 1)

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                conflict = executor.submit(attempt, True).result(timeout=3)
        finally:
            api.unregister_hotkey(identifier)
        with ThreadPoolExecutor(max_workers=1) as executor:
            released = executor.submit(attempt, False).result(timeout=3)
        return {"binding": candidate.label, "occupied": conflict, "released": released,
                "physical_key_delivery_tested": False}

    def mutex():
        name = f"Local\\DekstopShot.Diagnostics.{os.getpid()}"
        first = api.acquire_instance(name)
        assert first, "Could not acquire the isolated diagnostic mutex"
        try:
            assert api.acquire_instance(name) is None, "Second acquisition was not rejected"
        finally:
            api.kernel.CloseHandle(first)
        again = api.acquire_instance(name)
        assert again, "Mutex was not released"
        api.kernel.CloseHandle(again)
        return {"duplicate_rejected": True, "released": True}

    def wgc():
        api.validate_window(target)
        captures = []
        for screen in app.screens():
            pattern.move(screen.availableGeometry().center() - pattern.rect().center())
            pump(300)
            cover.move(pattern.pos())
            cover.show()
            cover.raise_()
            pump(300)
            try:
                # Keep the owning GUI thread responsive during spawn-based WGC.
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(capture_window, target)
                    while not future.done():
                        pump(25)
                    frame = future.result()
                scale = pattern.devicePixelRatio()
                expected_size = (round(pattern.width() * scale), round(pattern.height() * scale))
                assert (frame.width, frame.height) == expected_size, (
                    f"Physical WGC size {(frame.width, frame.height)} != {expected_size} at DPI scale {scale}"
                )
                expected = ((235, 35, 45), (35, 220, 55), (40, 65, 235), (235, 215, 35))
                samples = []
                for (xf, yf), rgb in zip(((.25, .25), (.75, .25), (.25, .75), (.75, .75)), expected):
                    offset = (int(frame.height * yf) * frame.width + int(frame.width * xf)) * 4
                    blue, green, red, _alpha = frame.bgra[offset:offset + 4]
                    observed = (red, green, blue)
                    assert all(abs(a - b) <= 20 for a, b in zip(observed, rgb)), (
                        f"WGC pattern mismatch: observed {observed}, expected {rgb}"
                    )
                    samples.append(observed)
                captures.append({"width": frame.width, "height": frame.height, "dpi_scale": scale,
                                 "quadrant_rgb": samples, "own_cover_excluded": True})
            finally:
                cover.hide()
                pump()
        return {"captures": captures}

    def minimized():
        pattern.showMinimized()
        pump()
        try:
            try:
                api.validate_window(target)
            except ValueError as error:
                assert "свёрнуто" in str(error), str(error)
                return {"rejected": True, "message": str(error)}
            raise AssertionError("Minimized target passed validation")
        finally:
            pattern.showNormal()
            pump()

    def clipboard():
        synthetic = Frame(2, 2, bytes((0, 0, 255, 0, 0, 255, 0, 0,
                                       255, 0, 0, 0, 0, 255, 255, 0)))
        payload = encode_frame(synthetic)
        api.write_clipboard(hwnd, payload.dib, payload.png)
        api._signature(api.user, "GetClipboardData", [W.UINT], C.c_void_p)
        api._signature(api.kernel, "GlobalSize", [C.c_void_p], C.c_size_t)
        assert api.user.OpenClipboard(hwnd), "Cannot reopen clipboard for readback"
        try:
            for fmt, expected in ((8, payload.dib),
                                  (api.user.RegisterClipboardFormatW("PNG"), payload.png)):
                handle = api.user.GetClipboardData(fmt)
                assert handle, f"Clipboard format {fmt} missing"
                size = api.kernel.GlobalSize(handle)
                assert size >= len(expected), "Clipboard allocation is shorter than the published payload"
                pointer = api.kernel.GlobalLock(handle)
                assert pointer, "Cannot lock clipboard memory"
                try:
                    assert C.string_at(pointer, len(expected)) == expected, "Clipboard content differs"
                finally:
                    api.kernel.GlobalUnlock(handle)
        finally:
            api.user.CloseClipboard()
        image = app.clipboard().image()
        assert (image.width(), image.height()) == (2, 2), "Qt cannot decode the system clipboard image"
        assert image.pixelColor(0, 0).red() == 255 and image.pixelColor(0, 1).blue() == 255
        return {"dib_exact": True, "png_exact": True, "qt_readback_colors": True,
                "external_app_paste_tested": False}

    def closed():
        pattern.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        pattern.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        pump()
        try:
            api.validate_window(target)
        except ValueError as error:
            assert "закрыто" in str(error), str(error)
            return {"rejected": True, "message": str(error)}
        raise AssertionError("Destroyed target passed validation")

    def png_file_roundtrip():
        # Only a synthetic 2x2 pattern is written, in a temporary diagnostic
        # directory. Resolving Pictures does not create or alter that folder.
        destination = pictures_directory()
        assert destination.is_absolute() and destination.name == "DekstopShot"
        synthetic = Frame(2, 2, bytes((0, 0, 255, 0, 0, 255, 0, 0,
                                       255, 0, 0, 0, 0, 255, 255, 0)))
        png = encode_frame(synthetic).png
        with tempfile.TemporaryDirectory(prefix="DekstopShot-png-") as temporary:
            directory = Path(temporary) / "Изображения" / "DekstopShot"
            stamp = datetime.now()
            first = save_png(png, directory=directory, captured_at=stamp)
            second = save_png(png, directory=directory, captured_at=stamp)
            assert first != second and first.read_bytes() == second.read_bytes() == png
            image = QImage(str(first))
            assert image.width() == image.height() == 2
            assert image.pixelColor(0, 0).red() == 255 and image.pixelColor(0, 1).blue() == 255
        return {"system_pictures_resolved": str(destination), "system_pictures_written": False,
                "synthetic_png_bytes_exact": True, "same_timestamp_no_overwrite": True,
                "unicode_path_roundtrip": True, "temporary_files_removed": True}

    try:
        record("gdi_monitors", gdi)
        record("hotkey_registration_conflict_release", hotkeys)
        record("single_instance_mutex", mutex)
        record("wgc_own_pattern_behind_own_cover", wgc)
        record("minimized_target_rejected", minimized)
        if args.clipboard:
            record("clipboard_synthetic_dib_png_readback", clipboard)
        else:
            results.append({"name": "clipboard_synthetic_dib_png_readback", "status": "skipped",
                            "detail": "Add --clipboard to replace the clipboard with the synthetic test image"})
        record("closed_target_rejected", closed)
        record("optional_png_file_roundtrip", png_file_roundtrip)
    finally:
        cover.close()
        try:
            pattern.close()
        except RuntimeError:
            pass  # WA_DeleteOnClose has already destroyed it.
        app.processEvents()

    report = {"utc": datetime.now(timezone.utc).isoformat(), "app_version": VERSION,
              "platform": platform.platform(),
              "python": platform.python_version(), "frozen": bool(getattr(sys, "frozen", False)), "results": results,
              "limitations": ["No physical WM_HOTKEY input", "No external app paste", "No Controller GUI test",
                              "No system monitor layout or DPI setting changes", "No visual Acrylic assertion"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {args.output}", flush=True)
    return int(any(result["status"] == "failed" for result in results))

