"""Opt-in observation of Windows' capture indicator around a synthetic window.

The positive control explicitly requests a border, then the same window is
captured without a border. GDI samples only narrow strips over our own navy
backdrop. No desktop image, capture frame, or clipboard content is saved.
If the system overlay is absent from GDI, the outcome is inconclusive.
"""

from __future__ import annotations

import ctypes as C
import json
import os
import platform
import sys
import threading
import time
from ctypes import wintypes as W
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    if sys.platform != "win32" or sys.getwindowsversion().build < 20348:
        raise SystemExit("The borderless capture probe requires Windows build 20348 or newer")
    os.environ["QT_QPA_PLATFORM"] = "windows"
    import numpy as np
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPainter
    from PySide6.QtWidgets import QApplication, QWidget
    from windows_capture import WindowsCapture

    from dekstopshot.core import Monitor
    from dekstopshot.native import WindowsAPI

    api = WindowsAPI()
    api.enable_dpi()
    api._signature(api.user, "GetWindowRect", [C.c_void_p, C.POINTER(W.RECT)], W.BOOL)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)

    class SolidWindow(QWidget):
        def __init__(self, color, title, parent=None):
            super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                             | Qt.WindowType.WindowStaysOnTopHint)
            self.color = color
            self.setWindowTitle(title)

        def paintEvent(self, _event):
            painter = QPainter(self)
            painter.fillRect(self.rect(), self.color)

    def pump(duration=.1):
        until = time.monotonic() + duration
        while time.monotonic() < until:
            app.processEvents()
            time.sleep(.005)

    guard = SolidWindow(QColor(25, 35, 55), "DekstopShot border probe backdrop")
    guard.resize(640, 480)
    guard.move(app.primaryScreen().availableGeometry().center() - guard.rect().center())
    target = SolidWindow(QColor(30, 80, 150), "DekstopShot border probe target", guard)
    target.resize(400, 280)
    target.move(guard.pos() + guard.rect().center() - target.rect().center())
    guard.show()
    target.show()
    target.raise_()
    pump(.3)
    hwnd = int(target.winId())
    native_rect = W.RECT()
    if not api.user.GetWindowRect(hwnd, C.byref(native_rect)):
        raise C.WinError(C.get_last_error())
    x, y = native_rect.left, native_rect.top
    width, height = native_rect.right - x, native_rect.bottom - y
    # The guard is larger than the target, so these strips contain our own
    # fixture plus any Windows indicator, never other application content.
    thickness = 14
    half = thickness // 2
    strips = ((x - half, y - half, width + thickness, thickness),
              (x - half, y + height - half, width + thickness, thickness),
              (x - half, y - half, thickness, height + thickness),
              (x + width - half, y - half, thickness, height + thickness))

    def sample_ring():
        yellow = total = 0
        for left, top, strip_width, strip_height in strips:
            frame = api.capture(Monitor("probe", "probe", "probe", left, top, strip_width, strip_height))
            pixels = np.frombuffer(frame.bgra, dtype=np.uint8).reshape(-1, 4)
            blue, green, red = pixels[:, 0], pixels[:, 1], pixels[:, 2]
            yellow += int(np.count_nonzero((red >= 200) & (green >= 140) & (blue <= 85)))
            total += len(pixels)
        return yellow, total

    phases = []
    try:
        baseline, ring_pixels = sample_ring()
        for border in (True, False):
            capture = WindowsCapture(cursor_capture=False, draw_border=border, window_hwnd=hwnd)
            first_frame = threading.Event()
            frame_count = [0]

            @capture.event
            def on_frame_arrived(_frame, _control):
                frame_count[0] += 1
                first_frame.set()

            @capture.event
            def on_closed():
                pass

            control = None
            try:
                control = capture.start_free_threaded()
                deadline = time.monotonic() + 3
                while not first_frame.is_set() and time.monotonic() < deadline:
                    pump(.02)
                if not first_frame.is_set():
                    raise RuntimeError("Capture did not produce its first frame")
                samples = []
                until = time.monotonic() + .9
                while time.monotonic() < until:
                    pump(.025)
                    samples.append(sample_ring()[0])
                phases.append({"draw_border": border, "capture_frames": frame_count[0],
                               "samples": len(samples), "peak_yellow_pixels": max(samples),
                               "minimum_yellow_pixels": min(samples), "ring_pixels": ring_pixels})
            finally:
                if control is not None:
                    control.stop()
                    control.wait()
                pump(.3)
    finally:
        target.close()
        guard.close()
        app.processEvents()

    bordered_peak = phases[0]["peak_yellow_pixels"]
    borderless_peak = phases[1]["peak_yellow_pixels"]
    visible_control = bordered_peak > baseline + 20
    if not visible_control:
        status = "inconclusive"
        reason = "The explicitly enabled indicator was not distinguishable in GDI; no visual claim is possible."
    elif borderless_peak <= baseline + 4:
        status = "passed"
        reason = "GDI saw the positive-control yellow border and no yellow border with draw_border=False."
    else:
        status = "failed"
        reason = "Yellow pixels remain with draw_border=False; inspect other active capture sessions or permissions."
    report = {"utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
              "status": status, "reason": reason, "baseline_yellow_pixels": baseline,
              "fixture_physical_size": [width, height], "phases": phases,
              "limitations": ["Synthetic owned fixture only", "GDI numerical observation; no saved images",
                              "This test does not prove the overlay behavior on other Windows versions"]}
    output = ROOT / ".validation" / "border-probe.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)
    return int(status == "failed")


if __name__ == "__main__":
    raise SystemExit(main())
