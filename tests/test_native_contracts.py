import ctypes as C
from types import SimpleNamespace

import pytest

from dekstopshot.core import Hotkey, Monitor
from dekstopshot.hotkeys import HotkeyManager
from dekstopshot.native import BITMAPINFOHEADER, ClipboardBusy, WindowsAPI


class FakeHotkeyAPI:
    def __init__(self):
        self.bindings = {}
        self.fail = False

    def register_hotkey(self, identifier, hotkey):
        if self.fail:
            raise OSError("already taken")
        self.bindings[identifier] = hotkey

    def unregister_hotkey(self, identifier):
        self.bindings.pop(identifier, None)


def test_hotkey_conflict_preserves_working_binding(qapp):
    api = FakeHotkeyAPI()
    manager = HotkeyManager(api, qapp, Hotkey())
    manager.resume()
    original_id = manager.identifier
    api.fail = True
    with pytest.raises(OSError):
        manager.replace(Hotkey(0x53, 3))
    assert manager.current == Hotkey()
    assert manager.registered
    assert api.bindings == {original_id: Hotkey()}
    manager.close()


def test_pause_releases_key_and_resume_registers_it(qapp):
    api = FakeHotkeyAPI()
    manager = HotkeyManager(api, qapp, Hotkey())
    manager.resume()
    manager.suspend()
    assert not api.bindings
    manager.resume()
    assert list(api.bindings.values()) == [Hotkey()]
    manager.close()
    assert not api.bindings


class FakeClipboard:
    def __init__(self, busy=False, fail_format=None):
        self.heap = {}
        self.transferred = {}
        self.empty_called = self.close_called = False
        self.busy, self.fail_format = busy, fail_format
        self.user = SimpleNamespace(
            RegisterClipboardFormatW=lambda _: 999,
            OpenClipboard=lambda _: not self.busy,
            EmptyClipboard=self.empty,
            CloseClipboard=self.close,
            SetClipboardData=self.set_data,
        )
        self.kernel = SimpleNamespace(GlobalAlloc=self.allocate, GlobalLock=lambda h: h,
                                      GlobalUnlock=lambda _: True, GlobalFree=self.free)

    def allocate(self, _flag, size):
        buffer = C.create_string_buffer(size)
        address = C.addressof(buffer)
        self.heap[address] = buffer
        return address

    def free(self, handle):
        self.heap.pop(handle)

    def empty(self):
        self.empty_called = True
        return True

    def close(self):
        self.close_called = True

    def set_data(self, fmt, handle):
        if fmt == self.fail_format:
            return 0
        self.transferred[fmt] = bytes(self.heap[handle])
        self.heap.pop(handle)  # Simulate ownership being taken by Windows.
        return handle


def api_with_clipboard(fake):
    api = object.__new__(WindowsAPI)
    api.user, api.kernel = fake.user, fake.kernel
    return api


def test_busy_clipboard_does_not_erase_existing_data_or_leak_memory():
    fake = FakeClipboard(busy=True)
    with pytest.raises(ClipboardBusy):
        api_with_clipboard(fake).write_clipboard(123, b"DIB", b"PNG")
    assert not fake.empty_called
    assert not fake.heap


def test_clipboard_transfers_both_formats_and_keeps_transferred_memory():
    fake = FakeClipboard()
    api_with_clipboard(fake).write_clipboard(123, b"DIB", b"PNG")
    assert fake.transferred == {8: b"DIB", 999: b"PNG"}
    assert fake.close_called and not fake.heap


def test_optional_png_failure_does_not_discard_successful_dib():
    fake = FakeClipboard(fail_format=999)
    api_with_clipboard(fake).write_clipboard(123, b"DIB", b"PNG")
    assert fake.transferred == {8: b"DIB"}
    assert not fake.heap
    assert fake.close_called


@pytest.mark.parametrize("bitblt_success", [True, False])
def test_capture_uses_physical_negative_coordinates_and_always_frees_gdi(monkeypatch, bitblt_success):
    assert C.sizeof(BITMAPINFOHEADER) == 40
    monkeypatch.setattr(C, "get_last_error", lambda: 5, raising=False)
    monkeypatch.setattr(C, "WinError", lambda _: OSError("capture failed"), raising=False)
    api = object.__new__(WindowsAPI)
    released, deleted, selected, blits = [], [], [], []
    buffer = C.create_string_buffer(bytes(range(16)))

    def dib(_screen, info, _mode, out_pixels, _section, _offset):
        assert info._obj.bmiHeader.biWidth == 2
        assert info._obj.bmiHeader.biHeight == -2
        C.cast(out_pixels, C.POINTER(C.c_void_p))[0] = C.addressof(buffer)
        return 303

    def select(dc, bitmap):
        selected.append((dc, bitmap))
        return 404

    def blit(*args):
        blits.append(args)
        return bitblt_success

    api.user = SimpleNamespace(GetDC=lambda _: 101, ReleaseDC=lambda *args: released.append(args))
    api.dwm = SimpleNamespace(DwmFlush=lambda: 0)
    api.gdi = SimpleNamespace(CreateCompatibleDC=lambda _: 202, CreateDIBSection=dib,
                              SelectObject=select, BitBlt=blit, GdiFlush=lambda: True,
                              DeleteObject=lambda h: deleted.append(("bitmap", h)),
                              DeleteDC=lambda h: deleted.append(("dc", h)))
    monitor = Monitor("test", "DISPLAY2", "test", -1920, -240, 2, 2)
    if bitblt_success:
        assert api.capture(monitor).bgra == bytes(range(16))
    else:
        with pytest.raises(OSError):
            api.capture(monitor)
    assert blits[0][6:8] == (-1920, -240)
    assert selected == [(202, 303), (202, 404)]
    assert deleted == [("bitmap", 303), ("dc", 202)]
    assert released == [(None, 101)]


@pytest.mark.parametrize("build,legacy_available,expected", [
    (22621, False, True), (19045, True, True), (19045, False, False),
])
def test_desktop_blur_uses_supported_or_optional_compositor_without_startup_dependency(
        monkeypatch, build, legacy_available, expected):
    from dekstopshot.native import ACCENT_POLICY

    monkeypatch.setattr("dekstopshot.native.sys.getwindowsversion",
                        lambda: SimpleNamespace(build=build), raising=False)
    api = object.__new__(WindowsAPI)
    api.user = SimpleNamespace()
    api.dwm = SimpleNamespace(DwmExtendFrameIntoClientArea=lambda *_: 0,
                              DwmSetWindowAttribute=lambda *_: 0)
    if legacy_available:
        def compose(_hwnd, data):
            assert data._obj.attribute == 19
            assert data._obj.size == 16
            policy = C.cast(data._obj.data, C.POINTER(ACCENT_POLICY)).contents
            assert policy.AccentState == 4
            assert policy.GradientColor >> 24 < 160  # Translucent tint, not an opaque fill.
            return True
        api.user.SetWindowCompositionAttribute = compose
    assert api.apply_backdrop(123) is expected
