"""Live three-press shortcut probe using only owned Qt windows and a synthetic fixture.

The operator presses the normal top-row minus once in each displayed phase.
This script never injects input. It writes no screenshot pixels to disk.
Start the synthetic target with ``tools/windows_smoke.py --show-target`` first.
"""

from __future__ import annotations

import json
import multiprocessing
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if sys.platform != "win32":
        raise SystemExit("This probe requires an interactive Windows desktop")
    os.environ["QT_QPA_PLATFORM"] = "windows"
    os.environ["LOCALAPPDATA"] = str(ROOT / ".validation" / "hotkey-profile")
    sys.path.insert(0, str(ROOT))

    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QVBoxLayout, QWidget

    from dekstopshot.app import Controller
    from dekstopshot.core import Hotkey, Settings, SettingsStore, WindowTarget
    from dekstopshot.native import WindowsAPI
    from dekstopshot.version import VERSION

    api = WindowsAPI()
    api.enable_dpi()
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    output = ROOT / ".validation" / "hotkey-input-smoke.json"
    results = []
    state = {"phase": "starting", "captures": 0, "paused_input_at": None, "done": False, "exit": 1}
    started = time.monotonic()
    controller = None

    host = QWidget(None, Qt.WindowType.Window)
    host.setWindowTitle("DekstopShot hotkey validation")
    host.resize(600, 230)
    layout = QVBoxLayout(host)
    status = QLabel("Preparing synthetic capture target...")
    status.setObjectName("probe_phase")
    status.setWordWrap(True)
    layout.addWidget(status)
    edit = QLineEdit()
    edit.setObjectName("shortcut_input")
    edit.setAccessibleName("Hotkey validation input")
    edit.setPlaceholderText("Press the normal top-row minus once when instructed")
    layout.addWidget(edit)
    counts = QLabel("Captures: 0")
    layout.addWidget(counts)

    def save_report():
        report = {"utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
                  "python": platform.python_version(), "version": VERSION,
                  "generated_input": False, "captures_requested": state["captures"], "results": results,
                  "limitations": ["Synthetic capture fixture and own QLineEdit only",
                                  "Input supplied by the operator, not by this script",
                                  "No claim for protected desktops or elevated applications"]}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Report: {output}", flush=True)

    def finish():
        if controller is not None:
            controller.quit()
        host.close()
        app.quit()

    def complete(ok, message):
        if state["done"]:
            return
        state["done"] = True
        state["exit"] = 0 if ok else 1
        timer.stop()
        if not ok:
            results.append({"name": state["phase"], "status": "failed", "error": message})
        status.setText(message)
        save_report()
        QTimer.singleShot(1000, finish)

    def captured():
        state["captures"] += 1
        counts.setText(f"Captures: {state['captures']}")

    def clipboard_pattern():
        image = app.clipboard().image()
        expected = ((235, 35, 45), (35, 220, 55), (40, 65, 235), (235, 215, 35))
        if image.isNull():
            raise AssertionError("The actual Windows clipboard contains no image")
        for (xf, yf), rgb in zip(((.25, .25), (.75, .25), (.25, .75), (.75, .75)), expected):
            color = image.pixelColor(int(image.width() * xf), int(image.height() * yf))
            observed = (color.red(), color.green(), color.blue())
            if any(abs(a - b) > 20 for a, b in zip(observed, rgb)):
                raise AssertionError(f"Unexpected synthetic clipboard color: {observed} != {rgb}")
        return {"width": image.width(), "height": image.height(), "quadrant_rgb_match": True}

    def set_phase(name, instruction):
        state["phase"] = name
        edit.clear()
        state["paused_input_at"] = None
        status.setText(instruction)
        edit.setFocus()
        print(f"Phase: {name}", flush=True)

    def copied():
        return not controller.busy and controller.window.message.text().startswith("Copied")

    def tick():
        try:
            if time.monotonic() - started > 120:
                complete(False, "Timed out waiting for the three operator key presses")
                return
            phase, requested, text = state["phase"], state["captures"], edit.text()
            if phase == "passthrough":
                if requested > 1:
                    raise AssertionError("One key press requested more than one capture")
                if text == "-" and requested == 1 and copied():
                    detail = clipboard_pattern()
                    results.append({"name": "passthrough_key_delivered_and_captured", "status": "passed",
                                    "detail": {"input": text, "captures": requested, **detail}})
                    controller.toggle_pause()
                    if not controller.paused or controller.hotkeys.registered:
                        raise AssertionError("Pause did not release the shortcut observer")
                    set_phase("paused", "Paused: press the normal minus once. It must type without a capture.")
            elif phase == "paused":
                if requested != 1 or controller.busy:
                    raise AssertionError("A screenshot was requested while paused")
                if text == "-":
                    if state["paused_input_at"] is None:
                        state["paused_input_at"] = time.monotonic()
                    elif time.monotonic() - state["paused_input_at"] >= .5:
                        results.append({"name": "paused_key_delivered_without_capture", "status": "passed",
                                        "detail": {"input": text, "captures": requested}})
                        controller.toggle_pause()
                        controller.change_option("hotkey_passthrough", False)
                        if (controller.paused or controller.settings.hotkey_passthrough
                                or controller.hotkeys.passthrough or not controller.hotkeys.registered):
                            raise AssertionError("Could not enter exclusive shortcut mode")
                        set_phase("exclusive", "Exclusive: press the normal minus once. Capture 2; input stays empty.")
            elif phase == "exclusive":
                if text:
                    raise AssertionError("The exclusive shortcut leaked into the text field")
                if requested > 2:
                    raise AssertionError("The exclusive shortcut repeated captures")
                if requested == 2 and copied():
                    detail = clipboard_pattern()
                    results.append({"name": "exclusive_key_captured_without_text", "status": "passed",
                                    "detail": {"input": text, "captures": requested, **detail}})
                    complete(True, "All three phases passed: pass-through, pause and exclusive shortcut.")
        except Exception as error:
            complete(False, f"{type(error).__name__}: {error}")

    timer = QTimer(host)
    timer.setInterval(100)
    timer.timeout.connect(tick)
    try:
        metadata = json.loads((ROOT / ".validation" / "target.json").read_text(encoding="utf-8"))
        if metadata["title"] != "DekstopShot validation target":
            raise ValueError("The selected target is not the synthetic fixture")
        target = WindowTarget(*(metadata[key] for key in ("hwnd", "pid", "process_start", "title", "executable")))
        api.validate_window(target)
        if not any((window.hwnd, window.pid, window.process_start, window.title) ==
                   (target.hwnd, target.pid, target.process_start, target.title) for window in api.windows()):
            raise ValueError("The synthetic fixture is stale or its HWND was reused")
        settings = Settings(hotkey=Hotkey(), notifications=False, start_hidden=True,
                            capture_mode="window", language="en", hotkey_passthrough=True)
        store = SettingsStore()
        store.save(settings)
        controller = Controller(app, api, check_updates=False, store=store, settings=settings)
        controller.select_window(target)
        controller.window.hide()
        controller.restore_window = False
        if controller.paused or not controller.hotkeys.registered:
            raise RuntimeError("The pass-through shortcut observer did not start")
        controller.hotkeys.events.capture_requested.connect(captured)
        set_phase("passthrough", "Pass-through: press the normal minus once. It must type and capture.")
        timer.start()
    except Exception as error:
        complete(False, f"Startup failed: {type(error).__name__}: {error}")

    host.show()
    host.raise_()
    host.activateWindow()
    edit.setFocus()
    ready = ROOT / ".validation" / "hotkey-probe-ready.json"
    ready.parent.mkdir(parents=True, exist_ok=True)
    ready.write_text(json.dumps({"hwnd": int(host.winId()), "pid": os.getpid(), "title": host.windowTitle()},
                                indent=2), encoding="utf-8")
    app.exec()
    if controller is not None:
        controller.quit()
        controller.pool.waitForDone(10000)
    # Verify that neither hotkey backend remains registered after teardown.
    if controller is not None and controller.hotkeys.registered:
        raise RuntimeError("Shortcut remained registered after the probe")
    return state["exit"]


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
