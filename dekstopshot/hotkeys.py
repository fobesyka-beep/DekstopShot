from __future__ import annotations

from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QTimer, Signal

from .core import Hotkey
from .keyboard_hook import PassThroughKeyboardHook


class NativeEvents(QObject):
    capture_requested = Signal()
    displays_changed = Signal()


class HotkeyManager(QAbstractNativeEventFilter):
    """Exclusive registration or a non-consuming observer, owned by the Qt GUI thread."""

    def __init__(self, api, app, hotkey: Hotkey, passthrough=False, *, hook_factory=None):
        super().__init__()
        self.api, self.app, self.current = api, app, hotkey
        self.events = NativeEvents()
        self.identifier = 0x4730
        self.registered = False
        self.passthrough = bool(passthrough)
        self._hook_factory = hook_factory or PassThroughKeyboardHook
        self._hook = None
        self._generation = 0
        self._closed = False
        app.installNativeEventFilter(self)

    def replace(self, hotkey: Hotkey):
        if self.registered and hotkey == self.current:
            return
        if self.passthrough:
            self._replace_hook(hotkey)
            return
        next_id = 0x4731 if self.identifier == 0x4730 else 0x4730
        # Acquire the new binding first. A conflict leaves the old one intact.
        self.api.register_hotkey(next_id, hotkey)
        if self.registered:
            self.api.unregister_hotkey(self.identifier)
        self.identifier, self.current, self.registered = next_id, hotkey, True
        self._generation += 1

    def _new_hook(self, hotkey):
        generation = self._generation + 1
        candidate = self._hook_factory(hotkey, lambda: self._queue_capture(generation))
        candidate.start()
        return candidate, generation

    def _replace_hook(self, hotkey):
        candidate, generation = self._new_hook(hotkey)
        try:
            if self._hook is not None:
                self._hook.close()
        except OSError:
            candidate.close()
            raise
        self._hook, self.current = candidate, hotkey
        self._generation, self.registered = generation, True

    def set_passthrough(self, enabled: bool):
        enabled = bool(enabled)
        if enabled == self.passthrough:
            return
        if not self.registered:
            self.passthrough = enabled
            self._generation += 1
            return
        if enabled:
            candidate, generation = self._new_hook(self.current)
            try:
                self.api.unregister_hotkey(self.identifier)
            except OSError:
                candidate.close()
                raise
            self._hook = candidate
            self._generation = generation
        else:
            next_id = 0x4731 if self.identifier == 0x4730 else 0x4730
            # A conflict retains the old non-consuming observer and current mode.
            self.api.register_hotkey(next_id, self.current)
            try:
                self._hook.close()
            except OSError:
                self.api.unregister_hotkey(next_id)
                raise
            self._hook = None
            self.identifier = next_id
            self._generation += 1
        self.passthrough = enabled

    def _queue_capture(self, generation):
        QTimer.singleShot(0, lambda: self._emit_capture(generation))

    def _emit_capture(self, generation):
        if self.registered and not self._closed and generation == self._generation:
            self.events.capture_requested.emit()

    def suspend(self):
        if self.registered:
            if self.passthrough:
                self._hook.close()
                self._hook = None
            else:
                self.api.unregister_hotkey(self.identifier)
            self.registered = False
            self._generation += 1

    def resume(self):
        self.replace(self.current)

    def close(self):
        self.suspend()
        if not self._closed:
            self.app.removeNativeEventFilter(self)
            self._closed = True

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if (msg.message == 0x0312 and msg.wParam == self.identifier
                    and self.registered and not self.passthrough):
                self._queue_capture(self._generation)
                return True, 0
            if msg.message in (0x007E, 0x0219):  # WM_DISPLAYCHANGE / WM_DEVICECHANGE
                QTimer.singleShot(0, self.events.displays_changed.emit)
        return False, 0
