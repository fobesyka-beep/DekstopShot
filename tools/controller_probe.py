"""Opt-in live Controller probe using the synthetic windows_smoke --show-target fixture.

Replaces the system clipboard only with the fixture's synthetic color pattern.
Settings, synthetic PNG copies and JSON results stay in the checkout's .validation directory.
Does not synthesize physical input or operate any other application's UI.
"""

from __future__ import annotations

import ctypes as C
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
        raise SystemExit("This diagnostic requires Windows")
    os.environ["QT_QPA_PLATFORM"] = "windows"
    os.environ["LOCALAPPDATA"] = str(ROOT / ".validation" / "controller-profile")
    sys.path.insert(0, str(ROOT))

    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    from dekstopshot import pictures
    from dekstopshot.app import Controller
    from dekstopshot.core import Settings, SettingsStore, WindowTarget
    from dekstopshot.native import WindowsAPI

    results = []
    controller = None
    api = WindowsAPI()
    api.enable_dpi()
    app = QApplication([])
    app.setApplicationName("DekstopShot controller validation")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")

    def pump(milliseconds=200):
        deadline = time.monotonic() + milliseconds / 1000
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)

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
        return result["status"] == "passed"

    def initialize():
        nonlocal controller
        assert QSystemTrayIcon.isSystemTrayAvailable(), "System tray is not available"
        SettingsStore().save(Settings(notifications=False, start_hidden=False, language="ru"))
        controller = Controller(app, api, check_updates=False)
        pump(500)
        assert controller.hotkeys.registered, "Default hotkey was not registered"
        assert not controller.paused, "Controller started paused"
        assert controller.tray.isVisible(), "Tray icon was not requested visible"
        return {"system_tray_available": True, "tray_requested_visible": True,
                "hotkey": controller.settings.hotkey.label, "registered": True}

    def native_window():
        api._signature(api.user, "GetWindowLongPtrW", [C.c_void_p, C.c_int], C.c_ssize_t)
        api._signature(api.gdi, "CreateRectRgn", [C.c_int] * 4, C.c_void_p)
        api._signature(api.user, "GetWindowRgn", [C.c_void_p, C.c_void_p], C.c_int)
        api._signature(api.gdi, "PtInRegion", [C.c_void_p, C.c_int, C.c_int], C.c_bool)
        exstyle = api.user.GetWindowLongPtrW(controller.hwnd, -20)
        region = api.gdi.CreateRectRgn(0, 0, 0, 0)
        assert region, "Cannot allocate a window region for corner validation"
        try:
            assert api.user.GetWindowRgn(controller.hwnd, region) > 0, "Native window has no clipping region"
            scale = controller.window.devicePixelRatio()
            width = round(controller.window.width() * scale)
            height = round(controller.window.height() * scale)
            assert api.gdi.PtInRegion(region, width // 2, height // 2)
            for x, y in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
                assert not api.gdi.PtInRegion(region, x, y), "Backdrop can still paint a square corner"
        finally:
            api.gdi.DeleteObject(region)
        details = {"qt_visible": controller.window.isVisible(),
                   "native_visible": bool(api.user.IsWindowVisible(controller.hwnd)),
                   "extended_style": hex(exstyle), "toolwindow": bool(exstyle & 0x80),
                   "appwindow": bool(exstyle & 0x40000),
                   "native_region_clips_all_corners": True,
                   "backdrop_api_success": bool(controller.window.backdrop),
                   "visual_acrylic_tested": False}
        assert details["qt_visible"], details
        assert details["native_visible"], details
        assert details["toolwindow"] and not details["appwindow"], details
        return details

    def select_fixture():
        metadata = json.loads((ROOT / ".validation" / "target.json").read_text(encoding="utf-8"))
        assert metadata["title"] == "DekstopShot validation target", "Not the synthetic test fixture"
        target = WindowTarget(*(metadata[key] for key in ("hwnd", "pid", "process_start", "title", "executable")))
        api.validate_window(target)
        # Reject stale/reused HWNDs before capturing anything.
        assert any((window.hwnd, window.pid, window.process_start, window.title) ==
                   (target.hwnd, target.pid, target.process_start, target.title) for window in api.windows()), (
            "Synthetic fixture is not in the real window list"
        )
        controller.select_mode("window")
        controller.select_window(target)
        assert not controller.unavailable, "Controller did not accept the synthetic target"
        assert controller.settings.capture_mode == "window"
        return {"synthetic_target_selected": True, "title": target.title}

    def capture_fixture():
        controller.show_window()
        pump()
        controller.capture()
        assert controller.busy, "Capture did not begin"
        assert not controller.window.isVisible(), "Own window did not hide before capture"
        assert not api.user.IsWindowVisible(controller.hwnd), "Native own window stayed visible"
        deadline = time.monotonic() + 15
        while controller.busy and time.monotonic() < deadline:
            pump(25)
        assert not controller.busy, "Capture did not finish by the diagnostic deadline"
        message = controller.window.message.text()
        assert "Скопировано" in message, message
        assert controller.window.isVisible(), "Own window did not restore after capture"
        assert api.user.IsWindowVisible(controller.hwnd), "Native own window did not restore"
        image = app.clipboard().image()
        assert not image.isNull(), "Clipboard image could not be decoded by Qt"
        expected = ((235, 35, 45), (35, 220, 55), (40, 65, 235), (235, 215, 35))
        for (xf, yf), rgb in zip(((.25, .25), (.75, .25), (.25, .75), (.75, .75)), expected):
            color = image.pixelColor(int(image.width() * xf), int(image.height() * yf))
            observed = (color.red(), color.green(), color.blue())
            assert all(abs(a - b) <= 20 for a, b in zip(observed, rgb)), (observed, rgb)
        return {"width": image.width(), "height": image.height(), "message": message,
                "own_window_hidden_then_restored": True, "clipboard_quadrants_match_fixture": True,
                "external_app_paste_tested": False}

    def pause_resume():
        controller.toggle_pause()
        assert controller.paused and not controller.hotkeys.registered
        controller.capture()
        assert not controller.busy, "Capture ran while paused"
        # A different native ID can acquire the actual binding while it is released.
        temporary_id = 0x5D20
        api.register_hotkey(temporary_id, controller.settings.hotkey)
        api.unregister_hotkey(temporary_id)
        controller.toggle_pause()
        assert not controller.paused and controller.hotkeys.registered
        return {"pause_blocks_capture": True, "binding_released": True, "resume_registered": True}

    def optional_png_saving():
        from PySide6.QtGui import QImage

        directory = ROOT / ".validation" / ("pictures-probe-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
        system_resolver = pictures.pictures_directory
        pictures.pictures_directory = lambda: directory
        try:
            controller.change_option("save_screenshots", False)
            capture_fixture()
            assert not directory.exists(), "Disabled saving touched the picture folder"
            controller.change_option("save_screenshots", True)
            capture_fixture()
            saved = list(directory.glob("*.png"))
            assert len(saved) == 1, "Enabled saving did not create one PNG"
            file_image = QImage(str(saved[0]))
            clipboard_image = app.clipboard().image()
            assert file_image.size() == clipboard_image.size()
            for xf, yf in ((.25, .25), (.75, .25), (.25, .75), (.75, .75)):
                x, y = int(file_image.width() * xf), int(file_image.height() * yf)
                assert file_image.pixelColor(x, y) == clipboard_image.pixelColor(x, y)
            assert "сохранено" in controller.window.message.text()
            controller.change_option("save_screenshots", False)
            capture_fixture()
            assert list(directory.glob("*.png")) == saved, "Disabled mode created another file"
            return {"disabled_creates_no_directory": True, "enabled_creates_png": True,
                    "file_clipboard_dimensions_and_colors_match": True,
                    "disabling_keeps_existing_png_only": True,
                    "only_synthetic_fixture_written": str(saved[0])}
        finally:
            pictures.pictures_directory = system_resolver
            controller.change_option("save_screenshots", False)

    def close_to_tray():
        controller.window.close()
        pump()
        assert not controller.window.isVisible(), "Close did not hide settings"
        assert not api.user.IsWindowVisible(controller.hwnd), "Native window did not hide"
        assert controller.hotkeys.registered and not controller.quitting
        assert controller.tray.isVisible()
        controller.show_window()
        pump()
        assert controller.window.isVisible() and api.user.IsWindowVisible(controller.hwnd)
        return {"close_hides_window": True, "hotkey_retained": True,
                "tray_requested_visible": True, "show_restores_window": True}

    def persisted():
        controller.change_option("start_hidden", True)
        reloaded = SettingsStore().load()
        assert reloaded == controller.settings, "Settings did not round-trip"
        assert reloaded.capture_mode == "window" and reloaded.start_hidden
        data = json.loads(controller.store.path.read_text(encoding="utf-8"))
        assert not any(key in data for key in ("hwnd", "pid", "target")), "HWND was persisted"
        return {"settings_round_trip": True, "window_mode": True, "start_hidden": True,
                "hwnd_not_persisted": True, "path": str(controller.store.path)}

    def language_and_key_mode():
        previous_hwnd = controller.hwnd
        previous_target = controller.target
        controller.change_language("en")
        pump()
        assert controller.settings.language == "en"
        assert controller.window.mode_combo.currentText() == "Application window"
        assert controller.target == previous_target
        assert controller.hwnd == previous_hwnd == int(controller.window.winId())
        controller.change_option("hotkey_passthrough", False)
        assert not controller.hotkeys.passthrough and controller.hotkeys.registered
        controller.change_option("hotkey_passthrough", True)
        assert controller.hotkeys.passthrough and controller.hotkeys.registered
        assert SettingsStore().load().language == "en"
        controller.change_language("ru")
        return {"ru_en_switch_same_hwnd_target": True, "language_persisted": True,
                "exclusive_and_passthrough_registered": True}

    try:
        if record("controller_initialize_real_tray_hotkey", initialize):
            record("native_toolwindow_visibility_backdrop_api", native_window)
            if record("select_real_synthetic_fixture", select_fixture):
                record("controller_capturejob_wgc_clipboard_restore", capture_fixture)
                record("optional_png_saving_real_wgc_clipboard_disk", optional_png_saving)
            record("pause_releases_binding_resume_restores", pause_resume)
            record("close_to_tray_retains_hotkey_and_reopen", close_to_tray)
            record("language_and_hotkey_mode_switch", language_and_key_mode)
            record("settings_persisted_without_window_handle", persisted)
    finally:
        if controller is not None:
            controller.quit()
            controller.pool.waitForDone(10000)
            pump()
            assert not controller.hotkeys.registered
    report = {"utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
              "python": platform.python_version(), "results": results,
              "limitations": ["Public slots invoked directly; no physical WM_HOTKEY input",
                              "System tray availability and icon request; no Explorer visual assertion",
                              "Backdrop API success only; no visual Acrylic assertion",
                              "Synthetic source fixture only; no third-party app paste",
                              "Source Controller only; no frozen executable"]}
    output = ROOT / ".validation" / "controller-smoke.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {output}", flush=True)
    return int(any(result["status"] == "failed" for result in results))


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
