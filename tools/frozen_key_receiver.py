"""Observe a real minus key and clipboard capture from the separately running exe.

This fixture does not synthesize input, register a hotkey, or store image pixels.
The parent validation drives its single input field through the desktop tool.
"""

from __future__ import annotations

import ctypes as C
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    if sys.platform != "win32":
        raise SystemExit("This validation fixture requires Windows")
    os.environ["QT_QPA_PLATFORM"] = "windows"

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QVBoxLayout, QWidget

    from dekstopshot.native import WindowsAPI
    from dekstopshot.version import VERSION

    api = WindowsAPI()
    api.enable_dpi()
    api._signature(api.user, "GetClipboardSequenceNumber", [], C.c_uint32)
    app = QApplication([])
    app.setStyle("Fusion")
    app.setApplicationName("DekstopShot frozen hotkey validation")
    initial_sequence = int(api.user.GetClipboardSequenceNumber())
    initial_image = app.clipboard().image()
    initial_size = [initial_image.width(), initial_image.height()]
    del initial_image
    monitor_sizes = {(monitor.width, monitor.height) for monitor in api.monitors()}
    started = time.monotonic()
    completed = False
    output = ROOT / ".validation" / "frozen-input-smoke.json"

    window = QWidget()
    window.setWindowTitle("DekstopShot frozen hotkey validation")
    window.resize(520, 180)
    layout = QVBoxLayout(window)
    layout.addWidget(QLabel("Press the ordinary minus key in the field below.\n"
                           "The separately running DekstopShot.exe should capture a monitor."))
    field = QLineEdit()
    field.setAccessibleName("Frozen hotkey input")
    field.setObjectName("frozenHotkeyInput")
    field.setMaxLength(1)
    field.setMinimumHeight(40)
    field.setStyleSheet("font-size: 24px;")
    layout.addWidget(field)
    state = QLabel("Waiting for input and a new clipboard image…")
    layout.addWidget(state)

    def finish(status: str, reason: str, image_size=None):
        nonlocal completed
        if completed:
            return
        completed = True
        timer.stop()
        payload = {
            "utc": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "reason": reason,
            "input": "-" if field.text() == "-" else "",
            "expected_version": VERSION,
            "clipboard_sequence_initial": initial_sequence,
            "clipboard_sequence_final": int(api.user.GetClipboardSequenceNumber()),
            "clipboard_initial_size": initial_size,
            "capture_width": image_size[0] if image_size else None,
            "capture_height": image_size[1] if image_size else None,
            "monitor_sizes": sorted([list(size) for size in monitor_sizes]),
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "image_pixels_stored": False,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        state.setText("Validation passed." if status == "passed" else "Validation failed: " + reason)
        QTimer.singleShot(1000, window.close)

    def poll():
        if field.text() == "-" and int(api.user.GetClipboardSequenceNumber()) != initial_sequence:
            image = app.clipboard().image()
            image_size = (image.width(), image.height())
            if image_size in monitor_sizes:
                finish("passed", "Minus reached the input and a new monitor image reached the clipboard.", image_size)
                return
        if time.monotonic() - started >= 90:
            finish("failed", "Timed out waiting for both the minus key and a new monitor clipboard image.")

    timer = QTimer(window)
    timer.setInterval(100)
    timer.timeout.connect(poll)
    window.show()
    field.setFocus()
    timer.start()
    app.exec()
    if not completed:
        finish("failed", "The receiver window closed before validation completed.")
    return 0 if completed and json.loads(output.read_text(encoding="utf-8"))["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
