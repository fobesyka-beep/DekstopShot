"""Small, explicitly typed Win32 boundary. No hooks, admin rights or screen files."""

from __future__ import annotations

import ctypes as C
import os
import sys
from ctypes import wintypes as W
from pathlib import PureWindowsPath

from .core import Frame, Hotkey, Monitor, WindowTarget

DWORD = C.c_uint32
LONG = C.c_int32
HANDLE = C.c_void_p


class BITMAPINFOHEADER(C.Structure):
    _fields_ = [("biSize", DWORD), ("biWidth", LONG), ("biHeight", LONG),
                ("biPlanes", C.c_uint16), ("biBitCount", C.c_uint16),
                ("biCompression", DWORD), ("biSizeImage", DWORD),
                ("biXPelsPerMeter", LONG), ("biYPelsPerMeter", LONG),
                ("biClrUsed", DWORD), ("biClrImportant", DWORD)]


class BITMAPINFO(C.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", DWORD * 3)]


class MONITORINFOEXW(C.Structure):
    _fields_ = [("cbSize", DWORD), ("rcMonitor", W.RECT),
                ("rcWork", W.RECT), ("dwFlags", DWORD), ("szDevice", W.WCHAR * 32)]


class DISPLAY_DEVICEW(C.Structure):
    _fields_ = [("cb", DWORD), ("DeviceName", W.WCHAR * 32),
                ("DeviceString", W.WCHAR * 128), ("StateFlags", DWORD),
                ("DeviceID", W.WCHAR * 128), ("DeviceKey", W.WCHAR * 128)]


class ACCENT_POLICY(C.Structure):
    _fields_ = [("AccentState", C.c_int32), ("AccentFlags", DWORD),
                ("GradientColor", DWORD), ("AnimationId", DWORD)]


class COMPOSITION_ATTRIBUTE_DATA(C.Structure):
    _fields_ = [("attribute", C.c_int32), ("data", C.c_void_p), ("size", C.c_size_t)]


class ClipboardBusy(OSError):
    pass


class WindowsAPI:
    def __init__(self):
        if sys.platform != "win32":
            raise OSError("Захват и глобальные клавиши доступны только в Windows.")
        self.user = C.WinDLL("user32", use_last_error=True)
        self.gdi = C.WinDLL("gdi32", use_last_error=True)
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.dwm = C.WinDLL("dwmapi", use_last_error=True)
        self._bind()

    @staticmethod
    def _signature(dll, name, args, result):
        function = getattr(dll, name)
        function.argtypes, function.restype = args, result
        return function

    def _bind(self):
        f = self._signature
        self.monitor_callback = C.WINFUNCTYPE(W.BOOL, HANDLE, HANDLE, C.POINTER(W.RECT), C.c_ssize_t)
        self.window_callback = C.WINFUNCTYPE(W.BOOL, HANDLE, C.c_ssize_t)
        f(self.user, "EnumDisplayMonitors", [HANDLE, C.c_void_p, self.monitor_callback, C.c_ssize_t], W.BOOL)
        f(self.user, "GetMonitorInfoW", [HANDLE, C.POINTER(MONITORINFOEXW)], W.BOOL)
        f(self.user, "EnumDisplayDevicesW", [W.LPCWSTR, DWORD, C.POINTER(DISPLAY_DEVICEW), DWORD], W.BOOL)
        f(self.user, "EnumWindows", [self.window_callback, C.c_ssize_t], W.BOOL)
        f(self.user, "IsWindow", [HANDLE], W.BOOL)
        f(self.user, "IsWindowVisible", [HANDLE], W.BOOL)
        f(self.user, "IsIconic", [HANDLE], W.BOOL)
        f(self.user, "GetWindow", [HANDLE, W.UINT], HANDLE)
        f(self.user, "GetWindowTextLengthW", [HANDLE], C.c_int)
        f(self.user, "GetWindowTextW", [HANDLE, W.LPWSTR, C.c_int], C.c_int)
        f(self.user, "GetWindowThreadProcessId", [HANDLE, C.POINTER(DWORD)], DWORD)
        f(self.kernel, "OpenProcess", [DWORD, W.BOOL, DWORD], HANDLE)
        f(self.kernel, "QueryFullProcessImageNameW", [HANDLE, DWORD, W.LPWSTR, C.POINTER(DWORD)], W.BOOL)
        f(self.kernel, "GetProcessTimes", [HANDLE, *[C.POINTER(W.FILETIME)] * 4], W.BOOL)
        f(self.user, "RegisterHotKey", [HANDLE, C.c_int, W.UINT, W.UINT], W.BOOL)
        f(self.user, "UnregisterHotKey", [HANDLE, C.c_int], W.BOOL)
        f(self.user, "GetDC", [HANDLE], HANDLE)
        f(self.user, "ReleaseDC", [HANDLE, HANDLE], C.c_int)
        f(self.gdi, "CreateCompatibleDC", [HANDLE], HANDLE)
        f(self.gdi, "CreateDIBSection", [HANDLE, C.POINTER(BITMAPINFO), W.UINT,
                                       C.POINTER(C.c_void_p), HANDLE, DWORD], HANDLE)
        f(self.gdi, "SelectObject", [HANDLE, HANDLE], HANDLE)
        f(self.gdi, "BitBlt", [HANDLE, C.c_int, C.c_int, C.c_int, C.c_int,
                              HANDLE, C.c_int, C.c_int, DWORD], W.BOOL)
        f(self.gdi, "DeleteObject", [HANDLE], W.BOOL)
        f(self.gdi, "DeleteDC", [HANDLE], W.BOOL)
        f(self.gdi, "GdiFlush", [], W.BOOL)
        f(self.user, "OpenClipboard", [HANDLE], W.BOOL)
        f(self.user, "EmptyClipboard", [], W.BOOL)
        f(self.user, "CloseClipboard", [], W.BOOL)
        f(self.user, "SetClipboardData", [W.UINT, HANDLE], HANDLE)
        f(self.user, "RegisterClipboardFormatW", [W.LPCWSTR], W.UINT)
        f(self.kernel, "GlobalAlloc", [W.UINT, C.c_size_t], HANDLE)
        f(self.kernel, "GlobalLock", [HANDLE], HANDLE)
        f(self.kernel, "GlobalUnlock", [HANDLE], W.BOOL)
        f(self.kernel, "GlobalFree", [HANDLE], HANDLE)
        f(self.kernel, "CreateMutexW", [C.c_void_p, W.BOOL, W.LPCWSTR], HANDLE)
        f(self.kernel, "CloseHandle", [HANDLE], W.BOOL)
        f(self.dwm, "DwmSetWindowAttribute", [HANDLE, DWORD, C.c_void_p, DWORD], LONG)
        f(self.dwm, "DwmGetWindowAttribute", [HANDLE, DWORD, C.c_void_p, DWORD], LONG)
        f(self.dwm, "DwmFlush", [], LONG)

    def enable_dpi(self):
        """Must run before QApplication creates any HWNDs."""
        try:
            self._signature(self.user, "SetProcessDpiAwarenessContext", [HANDLE], W.BOOL)
            self.user.SetProcessDpiAwarenessContext(C.c_void_p(-4))
        except AttributeError:
            # Supported target is Windows 10 1809+, kept for graceful degradation.
            self.user.SetProcessDPIAware()

    def acquire_instance(self):
        handle = self.kernel.CreateMutexW(None, False, "Local\\DekstopShot.Desktop.1")
        if not handle:
            raise C.WinError(C.get_last_error())
        if C.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            self.kernel.CloseHandle(handle)
            return None
        return handle

    def monitors(self) -> list[Monitor]:
        result, errors = [], []

        @self.monitor_callback
        def callback(handle, _dc, _rect, _param):
            # Never let a Python exception escape a ctypes callback.
            try:
                info = MONITORINFOEXW()
                info.cbSize = C.sizeof(info)
                if not self.user.GetMonitorInfoW(handle, C.byref(info)):
                    raise C.WinError(C.get_last_error())
                name, identity = info.szDevice, info.szDevice
                for index in range(64):
                    child = DISPLAY_DEVICEW()
                    child.cb = C.sizeof(child)
                    if not self.user.EnumDisplayDevicesW(info.szDevice, index, C.byref(child), 1):
                        break
                    if child.StateFlags & 1:  # DISPLAY_DEVICE_ACTIVE: ignore disconnected children.
                        name = child.DeviceString or name
                        identity = child.DeviceID or identity
                        break
                r = info.rcMonitor
                if r.right > r.left and r.bottom > r.top:
                    result.append(Monitor(identity, info.szDevice, name,
                                          r.left, r.top, r.right - r.left, r.bottom - r.top,
                                          bool(info.dwFlags & 1)))
            except Exception as error:
                errors.append(error)
                return False
            return True

        if not self.user.EnumDisplayMonitors(None, None, callback, 0):
            raise errors[0] if errors else C.WinError(C.get_last_error())
        return sorted(result, key=lambda m: (not m.primary, m.left, m.top, m.device))

    def _process_details(self, pid: int) -> tuple[str, int]:
        handle = self.kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return "Приложение", 0
        try:
            path = C.create_unicode_buffer(32768)
            length = DWORD(len(path))
            executable = "Приложение"
            if self.kernel.QueryFullProcessImageNameW(handle, 0, path, C.byref(length)):
                executable = PureWindowsPath(path.value).name
            creation, exit_time, kernel, user = (W.FILETIME() for _ in range(4))
            started = 0
            if self.kernel.GetProcessTimes(handle, C.byref(creation), C.byref(exit_time),
                                           C.byref(kernel), C.byref(user)):
                started = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            return executable, started
        finally:
            self.kernel.CloseHandle(handle)

    def windows(self) -> list[WindowTarget]:
        result = []

        @self.window_callback
        def callback(hwnd, _param):
            if not self.user.IsWindowVisible(hwnd) or self.user.GetWindow(hwnd, 4):
                return True  # Exclude invisible and owned/tool windows.
            length = self.user.GetWindowTextLengthW(hwnd)
            if not length:
                return True
            pid = DWORD()
            self.user.GetWindowThreadProcessId(hwnd, C.byref(pid))
            if pid.value == os.getpid():
                return True
            cloaked = DWORD()
            if self.dwm.DwmGetWindowAttribute(hwnd, 14, C.byref(cloaked), 4) >= 0 and cloaked.value:
                return True
            title = C.create_unicode_buffer(min(length + 1, 32768))
            self.user.GetWindowTextW(hwnd, title, len(title))
            if title.value and title.value != "Program Manager":
                executable, started = self._process_details(pid.value)
                result.append(WindowTarget(int(hwnd), pid.value, started, title.value, executable))
            return True

        if not self.user.EnumWindows(callback, 0):
            raise C.WinError(C.get_last_error())
        return sorted(result, key=lambda window: window.label.casefold())

    def validate_window(self, target: WindowTarget):
        if not self.user.IsWindow(target.hwnd):
            raise ValueError("Выбранное окно закрыто. Выберите приложение заново.")
        pid = DWORD()
        self.user.GetWindowThreadProcessId(target.hwnd, C.byref(pid))
        _name, started = self._process_details(pid.value)
        if pid.value != target.pid or (target.process_start and started != target.process_start):
            raise ValueError("Выбранное окно изменилось. Выберите приложение заново.")
        if self.user.IsIconic(target.hwnd):
            raise ValueError("Окно приложения свёрнуто. Разверните его перед снимком.")
        if not self.user.IsWindowVisible(target.hwnd):
            raise ValueError("Окно приложения скрыто. Откройте его перед снимком.")

    def register_hotkey(self, identifier: int, hotkey: Hotkey):
        if not self.user.RegisterHotKey(None, identifier, hotkey.modifiers | 0x4000, hotkey.vk):
            code = C.get_last_error()
            raise OSError(code, f"Клавиша {hotkey.label} занята Windows или другим приложением. "
                          "Выберите другое сочетание.")

    def unregister_hotkey(self, identifier: int):
        self.user.UnregisterHotKey(None, identifier)

    def capture(self, monitor: Monitor) -> Frame:
        """Physical-pixel rectangle, including negative virtual-desktop coordinates."""
        screen = self.user.GetDC(None)
        if not screen:
            raise C.WinError(C.get_last_error())
        memory = bitmap = previous = None
        try:
            memory = self.gdi.CreateCompatibleDC(screen)
            if not memory:
                raise C.WinError(C.get_last_error())
            info = BITMAPINFO()
            info.bmiHeader = BITMAPINFOHEADER(40, monitor.width, -monitor.height, 1, 32,
                                            0, monitor.width * monitor.height * 4, 0, 0, 0, 0)
            pixels = C.c_void_p()
            bitmap = self.gdi.CreateDIBSection(screen, C.byref(info), 0, C.byref(pixels), None, 0)
            if not bitmap or not pixels.value:
                raise C.WinError(C.get_last_error())
            previous = self.gdi.SelectObject(memory, bitmap)
            if not previous or previous == C.c_void_p(-1).value:
                previous = None
                raise OSError("Не удалось подготовить буфер захвата.")
            self.dwm.DwmFlush()
            if not self.gdi.BitBlt(memory, 0, 0, monitor.width, monitor.height,
                                   screen, monitor.left, monitor.top, 0x40CC0020):
                raise C.WinError(C.get_last_error())
            if not self.gdi.GdiFlush():
                raise OSError("Не удалось завершить захват экрана.")
            return Frame(monitor.width, monitor.height,
                         C.string_at(pixels, monitor.width * monitor.height * 4))
        finally:
            if previous:
                self.gdi.SelectObject(memory, previous)
            if bitmap:
                self.gdi.DeleteObject(bitmap)
            if memory:
                self.gdi.DeleteDC(memory)
            self.user.ReleaseDC(None, screen)

    def write_clipboard(self, hwnd: int, dib: bytes, png: bytes):
        """Allocate first; transfer ownership to Windows only after SetClipboardData succeeds."""
        payloads = [(8, dib)]  # CF_DIB is mandatory; PNG is an extra interoperable format.
        png_format = self.user.RegisterClipboardFormatW("PNG")
        if png_format and png:
            payloads.append((png_format, png))
        allocations = []
        try:
            for fmt, data in payloads:
                handle = self.kernel.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
                if not handle:
                    raise MemoryError("Недостаточно памяти для буфера обмена.")
                allocations.append([fmt, handle])
                pointer = self.kernel.GlobalLock(handle)
                if not pointer:
                    raise C.WinError(C.get_last_error())
                try:
                    C.memmove(pointer, data, len(data))
                finally:
                    self.kernel.GlobalUnlock(handle)
            if not self.user.OpenClipboard(hwnd):
                raise ClipboardBusy("Буфер обмена временно занят.")
            try:
                if not self.user.EmptyClipboard():
                    raise C.WinError(C.get_last_error())
                for fmt_handle in allocations:
                    if not self.user.SetClipboardData(*fmt_handle):
                        if fmt_handle[0] == 8:
                            raise C.WinError(C.get_last_error())
                        # DIB has already been published; do not report a false failure.
                        continue
                    fmt_handle[1] = None  # Now Windows owns the HGLOBAL.
            finally:
                self.user.CloseClipboard()
        finally:
            for _fmt, handle in allocations:
                if handle:
                    self.kernel.GlobalFree(handle)

    def apply_backdrop(self, hwnd: int) -> bool:
        """Desktop blur behind the live window, not an image captured from the desktop."""
        build = sys.getwindowsversion().build
        if build >= 22000:
            for attribute, value in ((20, 1), (33, 2)):
                number = C.c_int(value)
                self.dwm.DwmSetWindowAttribute(hwnd, attribute, C.byref(number), C.sizeof(number))
        class Margins(C.Structure):
            _fields_ = [(name, C.c_int) for name in ("left", "right", "top", "bottom")]
        self._signature(self.dwm, "DwmExtendFrameIntoClientArea", [HANDLE, C.POINTER(Margins)], LONG)
        margins = Margins(-1, -1, -1, -1)
        self.dwm.DwmExtendFrameIntoClientArea(hwnd, C.byref(margins))
        if build >= 22621:
            value = C.c_int(3)  # DWMSBT_TRANSIENTWINDOW / Desktop Acrylic
            if self.dwm.DwmSetWindowAttribute(hwnd, 38, C.byref(value), C.sizeof(value)) >= 0:
                return True
        # Windows 10 has no public Desktop Acrylic DWM attribute. This optional
        # compositor entry point is checked at runtime, and never required for startup.
        try:
            compose = self._signature(self.user, "SetWindowCompositionAttribute",
                                      [HANDLE, C.POINTER(COMPOSITION_ATTRIBUTE_DATA)], W.BOOL)
        except AttributeError:
            return False
        accent = ACCENT_POLICY(4, 0, 0x664D3B28, 0)  # AABBGGRR translucent blue-grey tint
        data = COMPOSITION_ATTRIBUTE_DATA(19, C.cast(C.pointer(accent), C.c_void_p), C.sizeof(accent))
        return bool(compose(hwnd, C.byref(data)))
