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

    def setContextMenu(self, _):
        pass

    def setToolTip(self, _):
        pass

    def show(self):
        pass

    def hide(self):
        pass

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
    SettingsStore().save(Settings(monitor_id="main", start_hidden=True))
    api = FakeDesktop()
    controller = Controller(qapp, api)
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


def test_application_mode_requires_explicit_window_selection(controller):
    controller, api = controller
    controller.select_mode("window")
    assert controller.settings.capture_mode == "window"
    assert controller.unavailable
    controller.capture()
    assert api.capture_count == 0
    assert not controller.busy
