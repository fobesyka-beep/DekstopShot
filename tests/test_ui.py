from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QKeyEvent

from dekstopshot.core import Hotkey, Monitor, Settings, WindowTarget
from dekstopshot.ui import KeyRecorder, MainWindow


def test_missing_monitor_is_explicit_and_does_not_select_first_available(qapp):
    window = MainWindow(Settings(monitor_id="disconnected"))
    window.update_monitors([Monitor("available", "DISPLAY1", "Dell", 0, 0, 1920, 1080, True)], "disconnected")
    assert window.monitor_combo.currentData() is None
    assert "отключён" in window.monitor_detail.text()
    window.deleteLater()


def test_window_picker_distinguishes_identical_titles_by_handle_and_process(qapp):
    window = MainWindow(Settings(capture_mode="window"))
    one = WindowTarget(101, 1, 1000, "Документ", "notepad.exe")
    two = WindowTarget(202, 2, 2000, "Документ", "notepad.exe")
    window.update_windows([one, two], two)
    assert window.window_combo.currentData() == two
    window.update_windows([one], two)
    assert window.window_combo.currentData() is None
    assert "закрыто" in window.window_title.text()
    window.deleteLater()


def test_recorder_preserves_numpad_minus_native_key(qapp):
    recorder = KeyRecorder(Hotkey())
    recorder.recording = True
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Minus, Qt.KeyboardModifier.KeypadModifier,
                      0, 0x6D, 0, "-")
    recorder.keyPressEvent(event)
    assert recorder.candidate == Hotkey(0x6D)
    assert not recorder.recording
    recorder.deleteLater()


def test_glass_window_clips_all_native_backdrop_corners_after_resize(qapp):
    window = MainWindow(Settings())
    window.show()
    for width, height in (MainWindow.DEFAULT_SIZE, MainWindow.MINIMUM_SIZE):
        window.resize(width, height)
        qapp.processEvents()
        region = window.mask()
        assert not region.isEmpty()
        assert region.contains(QPoint(width // 2, height // 2))
        assert region.contains(QPoint(width // 2, 1))
        for x, y in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
            assert not region.contains(QPoint(x, y))
    window.hide()
    window.deleteLater()
