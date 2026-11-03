import sys
from types import SimpleNamespace

import pytest

from dekstopshot.capture import _window_process
from dekstopshot.core import Frame, WindowTarget


class RecordingConnection:
    def __init__(self):
        self.messages = []
        self.closed = False

    def send(self, payload):
        self.messages.append(payload)

    def close(self):
        self.closed = True


@pytest.mark.parametrize("build, draw_border", [(19045, None), (20348, False), (26200, False)])
def test_window_capture_requests_borderless_when_supported_before_first_frame(monkeypatch, build, draw_border):
    target = WindowTarget(123, 456, 789, "Test window", "test.exe")
    connection = RecordingConnection()
    calls = []
    validated = []
    stopped = []

    class Capture:
        def __init__(self, **options):
            calls.append(options)
            self.handlers = {}

        def event(self, handler):
            self.handlers[handler.__name__] = handler
            return handler

        def start(self):
            assert calls == [{"cursor_capture": False, "draw_border": draw_border, "window_hwnd": target.hwnd}]
            pixels = SimpleNamespace(tobytes=lambda order: bytes((10, 20, 30, 0)))
            frame = SimpleNamespace(width=1, height=1, frame_buffer=pixels)
            control = SimpleNamespace(stop=lambda: stopped.append(True))
            self.handlers["on_frame_arrived"](frame, control)

    monkeypatch.setitem(sys.modules, "windows_capture", SimpleNamespace(WindowsCapture=Capture))
    monkeypatch.setattr("dekstopshot.capture.sys.getwindowsversion", lambda: SimpleNamespace(build=build), raising=False)
    monkeypatch.setattr("dekstopshot.native.WindowsAPI",
                        lambda: SimpleNamespace(validate_window=validated.append))

    _window_process(connection, target)

    assert validated == [target]
    assert stopped == [True]
    assert connection.messages == [(True, Frame(1, 1, bytes((10, 20, 30, 0))))]
    assert connection.closed


def test_borderless_capture_failure_is_not_retried_with_a_border(monkeypatch):
    target = WindowTarget(123, 456, 789, "Test window", "test.exe")
    connection = RecordingConnection()
    calls = []

    class Capture:
        def __init__(self, **options):
            calls.append(options)
            raise RuntimeError("Borderless capture is unavailable")

    monkeypatch.setitem(sys.modules, "windows_capture", SimpleNamespace(WindowsCapture=Capture))
    monkeypatch.setattr("dekstopshot.capture.sys.getwindowsversion", lambda: SimpleNamespace(build=26200), raising=False)
    monkeypatch.setattr("dekstopshot.native.WindowsAPI",
                        lambda: SimpleNamespace(validate_window=lambda _: None))

    _window_process(connection, target)

    assert calls == [{"cursor_capture": False, "draw_border": False, "window_hwnd": target.hwnd}]
    assert connection.messages == [(False, "Borderless capture is unavailable")]
    assert connection.closed
