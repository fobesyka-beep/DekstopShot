import json
import struct
from dataclasses import replace

import pytest

from dekstopshot.core import Frame, Hotkey, Monitor, Settings, SettingsStore, choose_monitor


def displays():
    return [Monitor("left", "DISPLAY2", "LG", -1920, -240, 1920, 1080),
            Monitor("main", "DISPLAY1", "Dell", 0, 0, 2560, 1440, True)]


def test_display_selection_survives_order_and_primary_change():
    monitors = displays()
    selected = choose_monitor(monitors, "left")
    changed = [replace(monitors[0], primary=True), replace(monitors[1], primary=False)]
    assert choose_monitor(list(reversed(changed)), "left").id == selected.id
    assert choose_monitor(monitors, "").id == "main"
    assert selected.left == -1920 and selected.top == -240


def test_disconnected_display_never_falls_back_to_another_screen():
    with pytest.raises(ValueError, match="отключён"):
        choose_monitor(displays(), "disconnected")
    with pytest.raises(ValueError, match="не обнаружила"):
        choose_monitor([], "")


@pytest.mark.parametrize("vk,modifiers", [(0x7B, 0), (0x10, 2), (0xBD, 8), (True, 0), (0xBD, True)])
def test_rejects_reserved_or_invalid_hotkeys(vk, modifiers):
    with pytest.raises(ValueError):
        Hotkey(vk, modifiers)


def test_keyboard_minus_and_numpad_minus_are_distinct():
    assert Hotkey().label == "−"
    assert Hotkey(0x6D).label == "Num −"
    assert Hotkey(0x53, 7).label == "Ctrl + Alt + Shift + S"


def test_settings_round_trip_and_no_window_handles_on_disk(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    settings = Settings(Hotkey(0x53, 3), "display-123", False, True, "window")
    store.save(settings)
    assert store.load() == settings
    assert "hwnd" not in store.path.read_text()
    assert json.loads(store.path.read_text())["capture_mode"] == "window"


def test_failed_atomic_save_keeps_the_previous_file(tmp_path, monkeypatch):
    store = SettingsStore(tmp_path / "settings.json")
    store.save(Settings())
    original = store.path.read_bytes()

    def fail(*_):
        raise PermissionError("test failure")

    monkeypatch.setattr("dekstopshot.core.os.replace", fail)
    with pytest.raises(PermissionError):
        store.save(Settings(hotkey=Hotkey(0x53, 3)))
    assert store.path.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


def test_corrupt_settings_preserve_original_and_load_defaults(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.path.write_text('{"hotkey": {"vk": 123}}')  # F12 is not allowed.
    assert store.load() == Settings()
    backups = list(tmp_path.glob("settings.broken-*.json"))
    assert len(backups) == 1
    assert '"vk": 123' in backups[0].read_text()
    assert store.warning


def test_renamed_app_imports_legacy_settings_without_changing_the_original(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    legacy = SettingsStore(tmp_path / "GlassShot" / "settings.json")
    settings = Settings(Hotkey(0x53, 3), "display-123", False, True, "window")
    legacy.save(settings)
    original = legacy.path.read_bytes()

    store = SettingsStore()
    assert store.path == tmp_path / "DekstopShot" / "settings.json"
    assert store.load() == settings
    assert store.path.is_file()
    assert legacy.path.read_bytes() == original
    assert not store.warning

    # Once migrated, the new application's settings take precedence.
    store.save(Settings())
    assert SettingsStore().load() == Settings()


def test_legacy_settings_are_not_used_for_an_explicit_store(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    SettingsStore(tmp_path / "GlassShot" / "settings.json").save(Settings(monitor_id="legacy"))
    explicit = SettingsStore(tmp_path / "custom" / "settings.json")
    assert explicit.load() == Settings()
    assert not explicit.path.exists()


def test_corrupt_legacy_settings_remain_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    legacy = tmp_path / "GlassShot" / "settings.json"
    legacy.parent.mkdir()
    legacy.write_text("not json", encoding="utf-8")
    store = SettingsStore()
    assert store.load() == Settings()
    assert legacy.read_text(encoding="utf-8") == "not json"
    assert not store.path.exists()
    assert store.warning


def test_legacy_settings_can_be_used_when_migration_cannot_be_saved(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    settings = Settings(monitor_id="legacy")
    SettingsStore(tmp_path / "GlassShot" / "settings.json").save(settings)
    store = SettingsStore()

    def fail(*_):
        raise PermissionError("test failure")

    monkeypatch.setattr(store, "save", fail)
    assert store.load() == settings
    assert store.warning
    assert not store.path.exists()


def test_dib_is_bottom_up_32_bit_without_alpha_dependency():
    # Top row: red, green. Bottom row: blue, white. GDI's unused alpha bytes are zero.
    frame = Frame(2, 2, bytes([0, 0, 255, 0, 0, 255, 0, 0,
                              255, 0, 0, 0, 255, 255, 255, 0]))
    dib = frame.dib()
    assert struct.unpack("<IiiHHIIiiII", dib[:40])[:5] == (40, 2, 2, 1, 32)
    assert dib[40:48] == frame.bgra[8:16]
    assert dib[48:56] == frame.bgra[0:8]


def test_png_and_dib_represent_the_same_colors_and_orientation(qapp):
    from PySide6.QtGui import QImage

    from dekstopshot.capture import encode_frame

    frame = Frame(1, 2, bytes([0, 0, 255, 0, 255, 0, 0, 0]))
    payload = encode_frame(frame)
    image = QImage.fromData(payload.png, "PNG")
    assert image.pixelColor(0, 0).getRgb() == (255, 0, 0, 255)
    assert image.pixelColor(0, 1).getRgb() == (0, 0, 255, 255)
    assert payload.dib[40:44] == bytes([255, 0, 0, 0])
