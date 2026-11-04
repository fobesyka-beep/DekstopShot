"""An opt-in, non-consuming shortcut observer for the current Windows desktop.

Only the configured shortcut is matched. No text is decoded, retained or logged.
The installing Qt GUI thread must continue pumping Windows messages.
"""

from __future__ import annotations

import ctypes as C
import sys
from ctypes import wintypes as W

from .core import MOD_ALT, MOD_CONTROL, MOD_SHIFT, Hotkey
from .i18n import t

WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105
KEY_DOWN_MESSAGES = (WM_KEYDOWN, WM_SYSKEYDOWN)
KEY_UP_MESSAGES = (WM_KEYUP, WM_SYSKEYUP)


class KBDLLHOOKSTRUCT(C.Structure):
    _fields_ = [("vkCode", C.c_uint32), ("scanCode", C.c_uint32),
                ("flags", C.c_uint32), ("time", C.c_uint32), ("dwExtraInfo", C.c_size_t)]


class ShortcutMatcher:
    """Match a fresh target-key down, using physical modifier state, without consuming it."""

    def __init__(self, hotkey: Hotkey, get_key_state):
        self.hotkey, self.get_key_state = hotkey, get_key_state
        # Starting/resuming while the target is held must not create a repeat capture.
        self.target_down = self._down(hotkey.vk)

    def _down(self, vk: int) -> bool:
        return bool(self.get_key_state(vk) & 0x8000)

    def handle(self, message: int, vk: int, flags=0) -> bool:
        if vk != self.hotkey.vk:
            return False
        if message in KEY_UP_MESSAGES:
            self.target_down = False
            return False
        if message not in KEY_DOWN_MESSAGES:
            return False
        repeated = self.target_down
        self.target_down = True
        if repeated or self._down(0x5B) or self._down(0x5C):  # Left/right Windows key.
            return False
        modifiers = 0
        for vk_modifier, modifier in ((0x11, MOD_CONTROL), (0x12, MOD_ALT), (0x10, MOD_SHIFT)):
            if self._down(vk_modifier):  # Generic VK covers both left and right modifiers, including AltGr.
                modifiers |= modifier
        if flags & 0x20:  # LLKHF_ALTDOWN is also available for system-key messages.
            modifiers |= MOD_ALT
        return modifiers == self.hotkey.modifiers


class PassThroughKeyboardHook:
    """WH_KEYBOARD_LL observer. CallNextHookEx is used for every event, even on failure."""

    def __init__(self, hotkey: Hotkey, on_pressed):
        if sys.platform != "win32":
            raise OSError(t("Передача горячей клавиши доступна только в Windows."))
        self.user = C.WinDLL("user32", use_last_error=True)
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.on_pressed = on_pressed
        self._handle = None
        self._callback_type = C.WINFUNCTYPE(C.c_ssize_t, C.c_int, C.c_size_t, C.c_ssize_t)
        self._bind(self.user, "SetWindowsHookExW", [C.c_int, self._callback_type, C.c_void_p, W.DWORD], C.c_void_p)
        self._bind(self.user, "CallNextHookEx", [C.c_void_p, C.c_int, C.c_size_t, C.c_ssize_t], C.c_ssize_t)
        self._bind(self.user, "UnhookWindowsHookEx", [C.c_void_p], W.BOOL)
        self._bind(self.user, "GetAsyncKeyState", [C.c_int], C.c_short)
        self._bind(self.kernel, "GetModuleHandleW", [W.LPCWSTR], C.c_void_p)
        self.matcher = ShortcutMatcher(hotkey, self.user.GetAsyncKeyState)
        # Keep the ctypes thunk alive until UnhookWindowsHookEx has succeeded.
        self._procedure = self._callback_type(self._dispatch)

    @staticmethod
    def _bind(dll, name, arguments, result):
        function = getattr(dll, name)
        function.argtypes, function.restype = arguments, result

    def start(self):
        if self._handle:
            return
        module = self.kernel.GetModuleHandleW(None)
        handle = self.user.SetWindowsHookExW(13, self._procedure, module, 0)
        if not handle:
            code = C.get_last_error()
            raise OSError(code, t("Не удалось включить передачу горячей клавиши (ошибка Windows {code}).", code=code))
        self._handle = handle

    def close(self):
        if not self._handle:
            return
        if not self.user.UnhookWindowsHookEx(self._handle):
            code = C.get_last_error()
            if code != 1404:  # ERROR_INVALID_HOOK_HANDLE: Windows has already removed the observer.
                raise OSError(code, t("Не удалось освободить горячую клавишу (ошибка Windows {code}).", code=code))
        self._handle = None

    def _dispatch(self, code, message, data_address):
        try:
            if code >= 0 and self._handle and message in (*KEY_DOWN_MESSAGES, *KEY_UP_MESSAGES):
                event = C.cast(data_address, C.POINTER(KBDLLHOOKSTRUCT)).contents
                if self.matcher.handle(message, event.vkCode, event.flags):
                    # The supplied callback only posts a Qt notification; it performs no capture or I/O.
                    self.on_pressed()
        except Exception:
            # Exceptions cannot cross a native callback boundary or suppress someone else's key.
            pass
        return self.user.CallNextHookEx(self._handle, code, message, data_address)
