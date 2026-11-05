from dataclasses import replace
from types import SimpleNamespace

import pytest
from PySide6 import QtCore
from PySide6.QtWidgets import QLabel, QPushButton

from dekstopshot.core import Monitor, Settings
from dekstopshot.i18n import EN, get_language, language_for_locale, set_language, system_language, t
from dekstopshot.ui import MainWindow


@pytest.fixture(autouse=True)
def restore_language():
    original = get_language()
    yield
    set_language(original)


@pytest.mark.parametrize("locale, expected", [("ru_RU", "ru"), ("ru-UA", "ru"), ("en_US", "en"),
                                                ("de_DE", "en"), ("C", "en")])
def test_locale_selection_uses_russian_or_english_fallback(locale, expected):
    assert language_for_locale(locale) == expected


def test_system_language_reads_preferred_ui_language(monkeypatch):
    class SystemLocale:
        @staticmethod
        def system():
            return SimpleNamespace(uiLanguages=lambda: ["ru-RU"], name=lambda: "en_US")

    monkeypatch.setattr(QtCore, "QLocale", SystemLocale)
    assert system_language() == "ru"


def test_formatted_capture_errors_translate_and_switch_back():
    source = "Не удалось захватить окно: Окно приложения свёрнуто. Разверните его перед снимком."
    set_language("en")
    english = t(source)
    assert english == "Could not capture the window: The application window is minimized. Restore it before capture."
    assert t("Скопировано · {width} × {height} px · {time} · Вставка: Ctrl + V",
             width=400, height=300, time="12:34:56") == "Copied · 400 × 300 px · 12:34:56 · Paste: Ctrl + V"
    set_language("ru")
    assert t(english) == source
    assert t("A document title") == "A document title"


def test_native_hotkey_conflict_is_english_before_oserror_adds_errno(monkeypatch):
    import ctypes

    from dekstopshot.core import Hotkey
    from dekstopshot.native import WindowsAPI

    api = WindowsAPI.__new__(WindowsAPI)
    api.user = SimpleNamespace(RegisterHotKey=lambda *_: False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 1409, raising=False)
    set_language("en")
    with pytest.raises(OSError) as failure:
        api.register_hotkey(123, Hotkey(0x53, 3))
    assert "The hotkey Ctrl + Alt + S is in use" in str(failure.value)
    assert failure.value.errno == 1409


def test_every_help_paragraph_has_an_english_translation():
    from dekstopshot.app import HELP_PARAGRAPHS

    set_language("en")
    for paragraph in HELP_PARAGRAPHS:
        assert paragraph in EN
        assert t(paragraph) != paragraph


def test_language_switch_keeps_window_target_options_and_update_link(qapp):
    settings = Settings(language="ru", hotkey_passthrough=True)
    window = MainWindow(settings)
    hwnd = int(window.winId())
    monitor = Monitor("selected", "DISPLAY1", "Test monitor", 0, 0, 1920, 1080, True)
    window.update_monitors([monitor], monitor.id)
    window.update_available("1.2.0", "https://github.com/fobesyka-beep/DekstopShot/releases/tag/v1.2.0")
    requested = []
    window.settings_requested.connect(lambda name, value: requested.append((name, value)))
    english = replace(settings, language="en", hotkey_passthrough=False)
    window.retranslate(english)
    window.update_monitors([monitor], monitor.id)
    texts = [child.text() for child in window.findChildren(QLabel)]
    assert "Capture source" in texts and "Hotkey" in texts
    assert "GENERAL" in texts and "Language" not in texts
    assert "SCREEN TO CLIPBOARD" in texts
    general_heading = next(child for child in window.findChildren(QLabel) if child.text() == "GENERAL")
    assert general_heading.alignment() == QtCore.Qt.AlignmentFlag.AlignCenter
    assert "Instructions" in [child.text().strip() for child in window.findChildren(QPushButton)]
    assert not any(child.text().strip() == "Скриншот" for child in window.findChildren(QPushButton))
    assert window.mode_combo.itemText(0) == "Entire selected monitor"
    assert window.monitor_combo.currentData() == "selected"
    assert window.language_combo.currentData() == "en"
    assert not window.hotkey_passthrough.isChecked()
    assert not requested  # Changing language does not toggle saved preferences.
    assert window.update_button.text() == "Update 1.2.0"
    assert window._update_url.endswith("/v1.2.0")
    assert int(window.winId()) == hwnd
    window.retranslate(settings)
    assert "ОБЩЕЕ" in [child.text() for child in window.findChildren(QLabel)]
    assert "СНИМОК В БУФЕР ОБМЕНА" in [child.text() for child in window.findChildren(QLabel)]
    assert window.update_button.text() == "Обновление 1.2.0"
    assert window.message is window.capture_status
    window.deleteLater()


def test_passthrough_preference_emits_only_user_changes(qapp):
    window = MainWindow(Settings(language="ru", hotkey_passthrough=True))
    requested = []
    window.settings_requested.connect(lambda name, value: requested.append((name, value)))
    window.hotkey_passthrough.setChecked(False)
    window.hotkey_passthrough.setChecked(True)
    assert requested == [("hotkey_passthrough", False), ("hotkey_passthrough", True)]
    window.deleteLater()


def test_saving_preference_switches_language_without_emitting_setting_changes(qapp):
    settings = Settings(language="ru", save_screenshots=False)
    window = MainWindow(settings)
    requested = []
    window.settings_requested.connect(lambda name, value: requested.append((name, value)))
    window.save_screenshots.setChecked(True)
    assert requested == [("save_screenshots", True)]
    saved = replace(settings, language="en", save_screenshots=True)
    window.retranslate(saved)
    assert window.save_screenshots.isChecked()
    assert window.save_screenshots.text() == "Save to Pictures"
    assert "Pictures" in window.capture_status.text()
    assert requested == [("save_screenshots", True)]
    window.retranslate(settings)
    assert not window.save_screenshots.isChecked()
    assert "буфере обмена" in window.capture_status.text()
    assert requested == [("save_screenshots", True)]
    window.deleteLater()


def test_saving_status_sync_preserves_last_capture_feedback(qapp):
    settings = Settings(language="ru", save_screenshots=False)
    window = MainWindow(settings)
    window.show_message("Скопировано · 400 × 300 px · 12:34:56 · Вставка: Ctrl + V")
    window.sync_settings(replace(settings, save_screenshots=True))
    assert window.save_screenshots.isChecked()
    assert window.capture_status.text() == "Скопировано · 400 × 300 px · 12:34:56 · Вставка: Ctrl + V"
    window.retranslate(replace(settings, language="en", save_screenshots=True))
    assert window.capture_status.text() == "Copied · 400 × 300 px · 12:34:56 · Paste: Ctrl + V"
    window.deleteLater()
