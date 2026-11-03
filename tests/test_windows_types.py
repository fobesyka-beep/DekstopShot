import ctypes as C
import sys

import pytest

from dekstopshot.native import DISPLAY_DEVICEW, MONITORINFOEXW, WindowsAPI


@pytest.mark.skipif(sys.platform != "win32", reason="Real Win32 ABI requires Windows")
def test_real_windows_structures_and_function_bindings():
    assert C.sizeof(MONITORINFOEXW) == 104
    assert C.sizeof(DISPLAY_DEVICEW) == 840
    api = WindowsAPI()
    assert api.user.RegisterHotKey.restype is not None
    assert api.user.GetDC.restype is C.c_void_p
    assert api.kernel.GlobalAlloc.restype is C.c_void_p
