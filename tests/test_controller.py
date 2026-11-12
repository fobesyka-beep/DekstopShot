import json
import threading
import time
from dataclasses import replace

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QTest

from dekstopshot.app import Controller
from dekstopshot.core import Frame, Monitor, Settings, SettingsStore
from dekstopshot.native import ClipboardBusy


class QuietTray(QObject):
    activated = Signal(object)
    messageClicked = Signal()

    class MessageIcon:
        Information, Warning = 1, 2

    def __init__(self, *_):
        super().__init__()
        self.messages = []
        self.visible = False

    @staticmethod
    def isSystemTrayAvailable():
        return True

    def setContextMenu(self, _):
        pass

    def setToolTip(self, _):
        pass

    def setVisible(self, visible):
        self.visible = visible

    def isVisible(self):
        return self.visible

    def hide(self):
        self.setVisible(False)

    def showMessage(self, *args):
        self.messages.append(args)


class FakeDesktop:
    def __init__(self):
        self.bindings, self.copies = {}, []
        self.capture_count = 0
        self.busy_copies = 0

    def apply_backdrop(self, _):
        return False

    def monitors(self):
        return [Monitor("main", "DISPLAY1", "Demo", -1920, -100, 2, 2, True)]

    def windows(self):
        return []

    def register_hotkey(self, identifier, hotkey):
        self.bindings[identifier] = hotkey

    def unregister_hotkey(self, identifier):
        self.bindings.pop(identifier, None)

    def capture(self, _):
        self.capture_count += 1
        return Frame(2, 2, bytes([0, 0, 255, 0] * 4))

    def write_clipboard(self, _hwnd, dib, png):
        if self.busy_copies:
            self.busy_copies -= 1
            raise ClipboardBusy()
        self.copies.append((dib, png))


@pytest.fixture
def controller(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr("dekstopshot.app.QSystemTrayIcon", QuietTray)
    SettingsStore().save(Settings(monitor_id="main", start_hidden=True, language="ru", hotkey_passthrough=False))
    api = FakeDesktop()
    controller = Controller(qapp, api, check_updates=False, can_reopen=True)
    yield controller, api
    controller.hotkeys.close()
    controller.window.hide()
    controller.pool.waitForDone(10000)
    controller.window.deleteLater()
    controller.deleteLater()
    qapp.processEvents()


def wait_for_capture(controller):
    deadline = time.monotonic() + 3
    while controller.busy and time.monotonic() < deadline:
        QTest.qWait(20)
    assert not controller.busy


def test_capture_hides_own_window_retries_clipboard_and_restores_ui(controller):
    controller, api = controller
    controller.window.show()
    api.busy_copies = 2
    controller.capture()
    assert controller.busy
    assert not controller.window.isVisible()
    controller.capture()  # Repeated presses cannot create concurrent capture jobs.
    wait_for_capture(controller)
    assert api.capture_count == 1
    assert len(api.copies) == 1
    assert api.copies[0][1].startswith(b"\x89PNG")
    assert controller.window.isVisible()
    assert "Скопировано" in controller.window.message.text()


def test_pause_frees_key_and_blocks_capture(controller):
    controller, api = controller
    controller.toggle_pause()
    assert controller.paused and not api.bindings
    controller.capture()
    assert not controller.busy and api.capture_count == 0
    controller.toggle_pause()
    assert not controller.paused and len(api.bindings) == 1


def test_success_is_silent_even_with_notifications_enabled_in_old_settings(controller):
    controller, api = controller
    controller.settings = replace(controller.settings, notifications=True)
    controller.capture()
    wait_for_capture(controller)
    assert len(api.copies) == 1
    assert not controller.tray.messages
    assert "Скопировано" in controller.window.message.text()


def test_tray_has_no_capture_command_in_either_language(controller):
    controller, _api = controller
    for language in ("ru", "en"):
        controller.change_language(language)
        texts = [action.text() for action in controller.menu.actions()]
        assert not any("Сделать снимок" in text or "Take a screenshot" in text for text in texts)


def test_hidden_without_tray_still_captures_and_can_be_reopened(controller):
    controller, api = controller
    assert controller.tray.isVisible()
    controller.show_window()
    controller.window.hide_tray_icon.setChecked(True)
    assert controller.store.load().hide_tray_icon
    assert controller.tray.isVisible()
    assert controller.window.quit_button.isVisible()

    controller.window.close()
    assert not controller.window.isVisible() and not controller.tray.isVisible()
    assert controller.hotkeys.registered
    controller.capture()
    wait_for_capture(controller)
    assert len(api.copies) == 1
    assert not controller.window.isVisible() and not controller.tray.isVisible()

    controller.show_window()
    assert controller.window.isVisible() and controller.tray.isVisible()
    controller.window.hide_tray_icon.setChecked(False)
    controller.window.close()
    assert controller.tray.isVisible()


def test_background_option_requires_working_reopen_channel(controller):
    controller, _api = controller
    controller.can_reopen = False
    controller.window.hide_tray_icon.setChecked(True)
    assert not controller.window.hide_tray_icon.isChecked()
    assert not controller.store.load().hide_tray_icon
    assert controller.tray.isVisible()


def test_disabled_picture_saving_never_resolves_the_system_picture_folder(controller, monkeypatch):
    controller, api = controller

    def forbidden():
        pytest.fail("Disabled saving must not resolve or touch Pictures")

    monkeypatch.setattr("dekstopshot.pictures.pictures_directory", forbidden)
    controller.capture()
    wait_for_capture(controller)
    assert len(api.copies) == 1


def test_picture_saving_is_persisted_and_saves_the_clipboard_png(controller, tmp_path, monkeypatch):
    controller, api = controller
    directory = tmp_path / "Pictures" / "DekstopShot"
    monkeypatch.setattr("dekstopshot.pictures.pictures_directory", lambda: directory)
    controller.change_option("save_screenshots", True)
    assert controller.store.load().save_screenshots
    assert controller.window.save_screenshots.isChecked()
    controller.capture()
    wait_for_capture(controller)
    files = list(directory.glob("*.png"))
    assert len(api.copies) == len(files) == 1
    assert files[0].read_bytes() == api.copies[0][1]
    assert "Скопировано и сохранено" in controller.window.message.text()
    assert not controller.tray.messages


def test_picture_save_failure_keeps_clipboard_and_explains_partial_success(controller, monkeypatch):
    controller, api = controller
    controller.change_option("save_screenshots", True)

    def fail(_png):
        raise PermissionError("access denied")

    monkeypatch.setattr("dekstopshot.pictures.save_png", fail)
    controller.capture()
    wait_for_capture(controller)
    assert len(api.copies) == 1 and api.copies[0][1].startswith(b"\x89PNG")
    assert "скопирован в буфер" in controller.window.message.text()
    assert "не удалось сохранить PNG" in controller.window.message.text()
    assert len(controller.tray.messages) == 1


@pytest.mark.parametrize("initial", [False, True])
def test_picture_save_policy_is_fixed_for_the_capture_in_progress(controller, tmp_path, monkeypatch, initial):
    controller, api = controller
    directory = tmp_path / "Pictures" / "DekstopShot"
    monkeypatch.setattr("dekstopshot.pictures.pictures_directory", lambda: directory)
    controller.change_option("save_screenshots", initial)
    controller.capture()
    controller.change_option("save_screenshots", not initial)
    wait_for_capture(controller)
    assert len(api.copies) == 1
    assert len(list(directory.glob("*.png"))) == int(initial)
    assert controller.store.load().save_screenshots is not initial


def test_failed_picture_option_save_restores_checkbox_and_policy(controller, monkeypatch):
    controller, _api = controller

    def fail(_settings):
        raise OSError("settings are read-only")

    monkeypatch.setattr(controller.store, "save", fail)
    controller.window.save_screenshots.setChecked(True)
    assert not controller.settings.save_screenshots
    assert not controller.window.save_screenshots.isChecked()


def test_failed_clipboard_copy_does_not_save_a_picture(controller, monkeypatch):
    controller, api = controller
    controller.change_option("save_screenshots", True)

    def fail(*_):
        raise OSError("clipboard failure")

    def forbidden(_png):
        pytest.fail("A failed clipboard capture must not save a picture")

    monkeypatch.setattr(api, "write_clipboard", fail)
    monkeypatch.setattr("dekstopshot.pictures.save_png", forbidden)
    controller.capture()
    wait_for_capture(controller)
    assert not api.copies
    assert "clipboard failure" in controller.window.message.text()


def test_quitting_during_picture_save_finishes_without_restoring_ui(controller, tmp_path, monkeypatch):
    controller, api = controller
    controller.change_option("save_screenshots", True)
    started, release = threading.Event(), threading.Event()
    quit_calls = []

    def delayed(_png):
        started.set()
        if not release.wait(2):
            raise TimeoutError("test did not release writer")
        return tmp_path / "saved.png"

    monkeypatch.setattr("dekstopshot.pictures.save_png", delayed)
    monkeypatch.setattr(controller.app, "quit", lambda: quit_calls.append(True))
    controller.window.show()
    controller.capture()
    deadline = time.monotonic() + 2
    while not started.is_set() and time.monotonic() < deadline:
        QTest.qWait(20)
    assert started.is_set()
    controller.quit()
    assert not quit_calls
    release.set()
    wait_for_capture(controller)
    assert len(api.copies) == 1
    assert quit_calls == [True]
    assert not controller.window.isVisible()
    assert not controller.hotkeys.registered
    assert not controller.tray.messages


def test_late_capture_failure_after_quit_does_not_show_a_notification(controller, monkeypatch):
    controller, _api = controller
    quit_calls = []
    monkeypatch.setattr(controller.app, "quit", lambda: quit_calls.append(True))
    controller.busy = True
    controller.quit()
    controller._capture_failed("late capture error")
    assert quit_calls == [True]
    assert not controller.tray.messages
    assert not controller.window.isVisible()


def test_application_mode_requires_explicit_window_selection(controller):
    controller, api = controller
    controller.select_mode("window")
    assert controller.settings.capture_mode == "window"
    assert controller.unavailable
    controller.capture()
    assert api.capture_count == 0
    assert not controller.busy


def test_language_switch_updates_window_and_tray_without_losing_target(controller):
    controller, api = controller
    original_hwnd = controller.hwnd
    controller.change_language("en")
    assert controller.settings.language == "en"
    assert controller.window.language_combo.currentData() == "en"
    assert controller.hwnd == original_hwnd == int(controller.window.winId())
    assert any(action.text() == "Open DekstopShot" for action in controller.menu.actions())
    assert controller.store.load().language == "en"
    controller.change_language("ru")
    assert controller.window.language_combo.currentData() == "ru"


def test_update_available_adds_safe_download_link_without_installing(controller):
    from dekstopshot.updates import ReleaseInfo

    controller, _api = controller
    release = ReleaseInfo("1.2.0", "https://github.com/fobesyka-beep/DekstopShot/releases/tag/v1.2.0", "v1.2.0")
    controller._update_available(release)
    assert controller.update_release == release
    assert len(controller.tray.messages) == 1


def test_failed_save_and_exclusive_rollback_conflict_keeps_saved_policy(controller, monkeypatch):
    controller, api = controller

    class Hook:
        def __init__(self, *_):
            pass

        def start(self):
            pass

        def close(self):
            pass

    controller.hotkeys._hook_factory = Hook
    register = api.register_hotkey

    def save_fails(_settings):
        def conflict(*_):
            raise OSError("already taken")

        monkeypatch.setattr(api, "register_hotkey", conflict)
        return False

    monkeypatch.setattr(controller, "_save", save_fails)
    controller.change_option("hotkey_passthrough", True)
    assert controller.paused and not controller.hotkeys.registered
    assert controller.settings.hotkey_passthrough is False
    assert controller.hotkeys.passthrough is False
    assert not controller.window.hotkey_passthrough.isChecked()
    monkeypatch.setattr(api, "register_hotkey", register)
    controller.toggle_pause()
    assert controller.hotkeys.registered and not controller.hotkeys.passthrough


def test_quitting_from_help_does_not_resume_the_hotkey(controller, monkeypatch):
    controller, api = controller
    monkeypatch.setattr(controller.app, "quit", lambda: None)
    monkeypatch.setattr("dekstopshot.app.GlassDialog.exec", lambda _dialog: controller.quit())
    controller.show_help()
    assert controller.quitting
    assert not controller.hotkeys.registered
    assert not api.bindings


def test_first_run_language_is_written_for_an_already_pinned_legacy_source(controller, monkeypatch):
    existing, _api = controller
    existing.store.path.write_text(json.dumps({
        "monitor_id": "main", "start_hidden": True, "hotkey_passthrough": False,
    }), encoding="utf-8")
    monkeypatch.setattr("dekstopshot.i18n.system_language", lambda: "en")
    loaded = Controller(existing.app, FakeDesktop(), check_updates=False)
    try:
        assert loaded.settings.language == "en"
        assert json.loads(loaded.store.path.read_text(encoding="utf-8"))["language"] == "en"
        monkeypatch.setattr("dekstopshot.i18n.system_language", lambda: "ru")
        assert loaded.store.load().language == "en"
    finally:
        loaded.hotkeys.close()
        loaded.window.hide()
        loaded.window.deleteLater()
        loaded.deleteLater()
        existing.app.processEvents()
