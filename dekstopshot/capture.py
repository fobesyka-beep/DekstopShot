"""One-shot jobs: GDI for displays, Windows Graphics Capture for individual windows."""

from __future__ import annotations

import multiprocessing
import sys
import time
from dataclasses import dataclass

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QRunnable, Signal
from PySide6.QtGui import QImage

from .core import Frame, Settings, WindowTarget, choose_monitor


def _window_process(connection, target: WindowTarget):
    """Isolate GPU/native capture so a stalled capture has a strict parent-side deadline."""
    try:
        from windows_capture import WindowsCapture

        from .native import WindowsAPI

        WindowsAPI().validate_window(target)
        # IsBorderRequired first appeared in build 20348. Older Windows 10 still
        # captures with its system indicator; newer builds request borderless capture
        # before StartCapture. Do not retry a rejected request with a bordered session.
        draw_border = False if sys.getwindowsversion().build >= 20348 else None
        capture = WindowsCapture(cursor_capture=False, draw_border=draw_border, window_hwnd=target.hwnd)
        frames = []

        @capture.event
        def on_frame_arrived(frame, capture_control):
            if not frames:
                frames.append(Frame(frame.width, frame.height, frame.frame_buffer.tobytes(order="C")))
            capture_control.stop()

        @capture.event
        def on_closed():
            pass

        capture.start()
        if not frames:
            raise RuntimeError("Windows не вернула изображение окна. Проверьте, что оно открыто.")
        connection.send((True, frames[0]))
    except Exception as error:  # Child-process boundary; deliver native errors to the UI.
        connection.send((False, str(error)))
    finally:
        connection.close()


def capture_window(target: WindowTarget, timeout=8.0) -> Frame:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_window_process, args=(sender, target), daemon=True)
    try:
        process.start()
        sender.close()
        if not receiver.poll(timeout):
            raise TimeoutError("Окно не ответило за 8 секунд. Разверните его и повторите снимок.")
        try:
            success, value = receiver.recv()
        except EOFError as error:
            raise RuntimeError("Windows прервала захват окна. Попробуйте выбрать его заново.") from error
        if not success:
            raise RuntimeError(f"Не удалось захватить окно: {value}")
        return value
    finally:
        sender.close()
        receiver.close()
        if process.pid:
            process.join(.3)
            if process.is_alive():
                process.terminate()
                process.join(1)


@dataclass(frozen=True)
class CapturePayload:
    width: int
    height: int
    dib: bytes
    png: bytes
    elapsed_ms: int


def encode_frame(frame: Frame, elapsed_ms: int = 0) -> CapturePayload:
    image = QImage(frame.bgra, frame.width, frame.height, frame.width * 4, QImage.Format.Format_RGB32)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise OSError("Не удалось подготовить изображение для буфера обмена.")
    buffer.close()
    return CapturePayload(frame.width, frame.height, frame.dib(), bytes(data), elapsed_ms)


class JobSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)


class CaptureJob(QRunnable):
    def __init__(self, api, settings: Settings, target: WindowTarget | None):
        super().__init__()
        self.api, self.settings, self.target = api, settings, target
        self.signals = JobSignals()

    def run(self):
        try:
            start = time.monotonic()
            if self.settings.capture_mode == "window":
                if self.target is None:
                    raise ValueError("Выберите окно приложения в настройках.")
                self.api.validate_window(self.target)
                frame = capture_window(self.target)
            else:
                monitor = choose_monitor(self.api.monitors(), self.settings.monitor_id)
                frame = self.api.capture(monitor)
            payload = encode_frame(frame, int((time.monotonic() - start) * 1000))
            self.signals.succeeded.emit(payload)
        except Exception as error:  # Worker boundary: errors are handled on the GUI thread.
            self.signals.failed.emit(str(error))
