from PySide6.QtCore import QEvent, QPoint, QRectF, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest

from dekstopshot.core import Hotkey, Monitor, Settings, WindowTarget
from dekstopshot.ui import DisplayMap, KeyRecorder, MainWindow


def test_missing_monitor_is_explicit_and_does_not_select_first_available(qapp):
    window = MainWindow(Settings(monitor_id="disconnected", language="ru"))
    window.update_monitors([Monitor("available", "DISPLAY1", "Dell", 0, 0, 1920, 1080, True)], "disconnected")
    assert window.monitor_combo.currentData() is None
    assert "отключён" in window.monitor_detail.text()
    window.deleteLater()


def test_monitor_map_preserves_mixed_screen_positions_when_readable(qapp):
    display_map = DisplayMap()
    display_map.resize(380, 140)
    monitors = [
        Monitor("main", "DISPLAY1", "Main", 0, 0, 2560, 1440, True),
        Monitor("left", "DISPLAY2", "Left", -1440, -120, 1440, 1920),
        Monitor("right", "DISPLAY3", "Right", 2560, 240, 1920, 1080),
    ]
    display_map.set_monitors(monitors, "main")
    (main, left, right), compact = display_map._display_rects()
    assert not compact
    assert left.right() < main.left() < main.right() < right.left()
    assert left.top() < main.top() < right.top()
    assert main.width() > right.width()
    display_map.deleteLater()


def test_dense_monitor_map_reflows_and_each_monitor_is_clickable(qapp):
    display_map = DisplayMap()
    display_map.resize(300, 108)
    monitors = [
        Monitor(str(index), f"DISPLAY{index}", f"Screen {index}", 0, -index * 1440, 2560, 1440)
        for index in range(12)
    ]
    display_map.set_monitors(monitors, monitors[-1].id)
    picked = []
    display_map.selected.connect(picked.append)
    display_map.show()
    try:
        for width in (300, 240):
            display_map.resize(width, 108)
            qapp.processEvents()
            rects, compact = display_map._display_rects()
            assert compact
            assert len(rects) == len(monitors)
            assert all(QRectF(display_map.rect()).contains(rect) for rect in rects)
            picked.clear()
            for rect in rects:
                QTest.mouseClick(display_map, Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
            assert picked == [monitor.id for monitor in monitors]
    finally:
        display_map.close()
        display_map.deleteLater()


def test_window_picker_distinguishes_identical_titles_by_handle_and_process(qapp):
    window = MainWindow(Settings(capture_mode="window", language="ru"))
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
