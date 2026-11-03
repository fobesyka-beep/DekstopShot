from __future__ import annotations

from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QTimer, Signal

from .core import Hotkey


class NativeEvents(QObject):
    capture_requested = Signal()
    displays_changed = Signal()


class HotkeyManager(QAbstractNativeEventFilter):
    """Registration stays on the Qt GUI thread, where WM_HOTKEY is delivered."""

    def __init__(self, api, app, hotkey: Hotkey):
        super().__init__()
        self.api, self.app, self.current = api, app, hotkey
        self.events = NativeEvents()
        self.identifier = 0x4730
        self.registered = False
        app.installNativeEventFilter(self)

    def replace(self, hotkey: Hotkey):
        if self.registered and hotkey == self.current:
            return
        next_id = 0x4731 if self.identifier == 0x4730 else 0x4730
        # Acquire the new binding first. A conflict leaves the old one intact.
        self.api.register_hotkey(next_id, hotkey)
        if self.registered:
            self.api.unregister_hotkey(self.identifier)
        self.identifier, self.current, self.registered = next_id, hotkey, True

    def suspend(self):
        if self.registered:
            self.api.unregister_hotkey(self.identifier)
            self.registered = False

    def resume(self):
        self.replace(self.current)

    def close(self):
        self.suspend()
        self.app.removeNativeEventFilter(self)

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam == self.identifier and self.registered:
                QTimer.singleShot(0, self.events.capture_requested.emit)
                return True, 0
            if msg.message in (0x007E, 0x0219):  # WM_DISPLAYCHANGE / WM_DEVICECHANGE
                QTimer.singleShot(0, self.events.displays_changed.emit)
        return False, 0
