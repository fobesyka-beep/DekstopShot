from __future__ import annotations

import logging
import sys
from dataclasses import replace
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QScrollArea, QSystemTrayIcon, QVBoxLayout

from .capture import CaptureJob, CapturePayload
from .core import Hotkey, Settings, SettingsStore, WindowTarget, choose_monitor
from .hotkeys import HotkeyManager
from .i18n import set_language, t
from .native import ClipboardBusy, WindowsAPI
from .services import QUICK_LINKS
from .ui import STYLE, GlassDialog, HotkeyDialog, MainWindow, app_icon, button, label, service_icon
from .updates import ReleaseInfo, UpdateChecker

log = logging.getLogger("dekstopshot")

HELP_PARAGRAPHS = (
    "1. Выберите монитор или открытое окно приложения.",
    "2. Нажмите горячую клавишу. По умолчанию — минус над буквами.",
    "3. Откройте нужную программу и нажмите Ctrl + V.",
    "В блоке «Общее» выберите русский или английский язык. При первом запуске язык определяется по системе.",
    "Если включено «Не блокировать клавишу», клавиша одновременно работает в других программах. "
    "Выключите этот режим, чтобы зарезервировать сочетание для снимка. На паузе захват отключён.",
    "Крестик и «Скрыть в трей» скрывают настройки. Чтобы открыть их снова, нажмите значок рядом с часами. "
    "Для завершения выберите «Выйти из DekstopShot» в меню трея.",
    "Для снимка приложения окно должно быть открыто и не свёрнуто. После закрытия окна или перезапуска "
    "DekstopShot выберите его заново.",
    "При запуске DekstopShot проверяет новые версии на GitHub. Если доступно обновление, откройте его страницу "
    "по кнопке в настройках и скачайте архив. Автоматической установки нет.",
    "Кнопки сервисов открывают сайты; снимок вставляется вручную. Google открывает обычный поиск. "
    "Скриншоты не записываются в файлы и не отправляются приложением.",
)


class Controller(QObject):
    def __init__(self, app: QApplication, api: WindowsAPI, *, check_updates=True,
                 store: SettingsStore | None = None, settings: Settings | None = None):
        super().__init__(app)
        self.app, self.api = app, api
        self.store = store if store is not None else SettingsStore()
        self.settings = settings if settings is not None else self.store.load()
        set_language(self.settings.language)
        self.update_release: ReleaseInfo | None = None
        self.updater = UpdateChecker(self)
        self.updater.available.connect(self._update_available)
        self.target: WindowTarget | None = None
        self.paused = self.busy = self.quitting = self.restore_window = False
        self.unavailable = True
        self.dialog: HotkeyDialog | None = None
        self.job = None
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.window = MainWindow(self.settings)
        self.hwnd = int(self.window.winId())
        self.backdrop_refresh = QTimer(self)
        self.backdrop_refresh.setSingleShot(True)
        self.backdrop_refresh.setInterval(0)
        self.backdrop_refresh.timeout.connect(self._apply_backdrop)
        self.hotkeys = HotkeyManager(api, app, self.settings.hotkey, passthrough=self.settings.hotkey_passthrough)
        self._connect_ui()
        self._make_tray()
        self.display_refresh = QTimer(self)
        self.display_refresh.setSingleShot(True)
        self.display_refresh.setInterval(400)
        self.display_refresh.timeout.connect(self.refresh_sources)
        self.hotkeys.events.displays_changed.connect(self.display_refresh.start)
        self.hotkeys.events.capture_requested.connect(self.capture)
        self.periodic_refresh = QTimer(self)
        self.periodic_refresh.setInterval(5000)
        self.periodic_refresh.timeout.connect(self._refresh_if_visible)
        self.periodic_refresh.start()
        self.refresh_sources()
        # Persist the first resolved language even when a 1.0 settings file
        # already contains a pinned monitor and refresh_sources need not save.
        settings_saved = self._save(self.settings)
        force_show = bool(self.store.warning) or self.unavailable or not settings_saved
        try:
            self.hotkeys.resume()
        except OSError as error:
            self.paused, force_show = True, True
            self.error(str(error))
        self._update_state()
        if self.store.warning:
            self.window.show_message(self.store.warning, True)
        if force_show or not self.settings.start_hidden:
            self.show_window()
        else:
            self.window.hide()
        if check_updates:
            QTimer.singleShot(1200, self._check_updates)

    def _connect_ui(self):
        self.window.surface_shown.connect(self.backdrop_refresh.start)
        self.window.capture_requested.connect(self.capture)
        self.window.monitor_requested.connect(self.select_monitor)
        self.window.window_requested.connect(self.select_window)
        self.window.mode_requested.connect(self.select_mode)
        self.window.refresh_requested.connect(self.refresh_sources)
        self.window.hotkey_requested.connect(self.change_hotkey)
        self.window.pause_requested.connect(self.toggle_pause)
        self.window.settings_requested.connect(self.change_option)
        self.window.language_requested.connect(self.change_language)
        self.window.open_link.connect(self.open_link)
        self.window.help_requested.connect(self.show_help)

    def _apply_backdrop(self):
        if self.quitting or not self.window.isVisible():
            return
        try:
            self.window.backdrop = self.api.apply_backdrop(int(self.window.winId()))
        except (OSError, AttributeError) as error:
            self.window.backdrop = False
            log.info("Desktop blur unavailable: %s", error)
        self.window.update()

    def _style_dialog(self, dialog: GlassDialog):
        dialog.backdrop_timer = QTimer(dialog)
        dialog.backdrop_timer.setSingleShot(True)
        dialog.backdrop_timer.setInterval(0)

        def refresh():
            if not dialog.isVisible():
                return
            try:
                dialog.backdrop = self.api.apply_backdrop(int(dialog.winId()))
            except (OSError, AttributeError):
                dialog.backdrop = False
            dialog.update()

        dialog.backdrop_timer.timeout.connect(refresh)
        dialog.surface_shown.connect(dialog.backdrop_timer.start)

    def _make_tray(self):
        self.tray = QSystemTrayIcon(app_icon(), self)
        self._refresh_tray_menu()
        self.tray.activated.connect(self._tray_activated)
        self.tray.messageClicked.connect(self.show_window)
        self.tray.show()

    def _refresh_tray_menu(self):
        previous = getattr(self, "menu", None)
        self.menu = QMenu()
        self.menu.setStyleSheet(STYLE)
        show = self.menu.addAction(t("Открыть DekstopShot"))
        show.triggered.connect(self.show_window)
        self.capture_action = self.menu.addAction(t("Сделать снимок"))
        self.capture_action.triggered.connect(self.capture)
        self.pause_action = QAction(t("Пауза"), self.menu)
        self.pause_action.setCheckable(True)
        self.pause_action.triggered.connect(self.toggle_pause)
        self.menu.addAction(self.pause_action)
        self.menu.addSeparator()
        for title, _subtitle, name, url in QUICK_LINKS:
            action = self.menu.addAction(service_icon(name), title)
            action.triggered.connect(lambda checked=False, u=url: self.open_link(u))
        self.menu.addSeparator()
        quit_action = self.menu.addAction(t("Выйти из DekstopShot"))
        quit_action.triggered.connect(self.quit)
        self.tray.setContextMenu(self.menu)
        if previous is not None:
            previous.deleteLater()

    def _check_updates(self):
        if not self.quitting:
            self.updater.start()

    def _update_available(self, release: ReleaseInfo):
        if self.quitting:
            return
        self.update_release = release
        self.window.update_available(release.version, release.url)
        self.tray.showMessage(t("Доступно обновление"),
                              t("Доступна версия {version}. Откройте настройки, чтобы скачать её.",
                                version=release.version),
                              QSystemTrayIcon.MessageIcon.Information, 5000)

    def change_language(self, language: str):
        if language not in ("ru", "en") or language == self.settings.language:
            return
        if not self._save(replace(self.settings, language=language)):
            self.window.retranslate(self.settings)
            return
        set_language(language)
        self.window.retranslate(self.settings)
        self._refresh_tray_menu()
        self.refresh_sources()
        self._update_state()
        if self.update_release:
            self.window.update_available(self.update_release.version, self.update_release.url)

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_window()

    def show_window(self):
        if self.busy:
            self.restore_window = True
            return
        self.refresh_sources()
        screen = self.window.screen() or self.app.primaryScreen()
        available = screen.availableGeometry()
        width, height = MainWindow.DEFAULT_SIZE
        self.window.resize(min(width, available.width() - 32), min(height, available.height() - 32))
        if not self.window.isVisible():
            self.window.move(available.center() - self.window.rect().center())
        self.window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()
        if self.dialog:
            self.dialog.raise_()
            self.dialog.activateWindow()

    def _refresh_if_visible(self):
        if (self.window.isVisible() and not self.busy and not self.dialog
                and not self.window.window_combo.view().isVisible()
                and not self.window.monitor_combo.view().isVisible()):
            self.refresh_sources()

    def refresh_sources(self):
        try:
            monitors = self.api.monitors()
            if not self.settings.monitor_id and monitors:
                selected = choose_monitor(monitors, "")
                # Fix the current display instead of following later primary-display changes.
                self._save(replace(self.settings, monitor_id=selected.id))
            self.window.update_monitors(monitors, self.settings.monitor_id)
            windows = self.api.windows()
            self.window.update_windows(windows, self.target)
            if self.settings.capture_mode == "window":
                self.unavailable = self.target is None or not any(
                    (w.hwnd, w.pid, w.process_start) ==
                    (self.target.hwnd, self.target.pid, self.target.process_start) for w in windows)
            else:
                try:
                    choose_monitor(monitors, self.settings.monitor_id)
                    self.unavailable = False
                except ValueError:
                    self.unavailable = True
        except (OSError, ValueError) as error:
            self.unavailable = True
            self.window.show_message(str(error), True)
            log.warning("Could not refresh capture sources: %s", error)
        self._update_state()

    def _save(self, settings) -> bool:
        try:
            self.store.save(settings)
            self.settings = settings
            return True
        except OSError as error:
            self.error(f"Не удалось сохранить настройки: {error}")
            return False

    def select_monitor(self, identity: str):
        if self._save(replace(self.settings, monitor_id=identity)):
            self.refresh_sources()
            self.window.show_message("Монитор закреплён. Горячая клавиша будет снимать именно его.")
        else:
            self.refresh_sources()

    def select_window(self, target):
        self.target = target if isinstance(target, WindowTarget) else None
        self.refresh_sources()
        if self.target:
            self.window.show_message("Окно выбрано. После закрытия или перезапуска приложения выберите его заново.")

    def select_mode(self, mode: str):
        if mode not in ("monitor", "window"):
            return
        if self._save(replace(self.settings, capture_mode=mode)):
            self.window.update_mode(mode)
        else:
            self.window.update_mode(self.settings.capture_mode)
        self.refresh_sources()

    def change_option(self, name: str, enabled: bool):
        if name not in ("start_hidden", "hotkey_passthrough"):
            return
        previous_mode = self.settings.hotkey_passthrough
        if name == "hotkey_passthrough":
            try:
                self.hotkeys.set_passthrough(enabled)
            except OSError as error:
                self.error(str(error))
                self.window.hotkey_passthrough.blockSignals(True)
                self.window.hotkey_passthrough.setChecked(previous_mode)
                self.window.hotkey_passthrough.blockSignals(False)
                return
        if not self._save(replace(self.settings, **{name: enabled})):
            if name == "hotkey_passthrough":
                try:
                    self.hotkeys.set_passthrough(previous_mode)
                except OSError as error:
                    self.paused = True
                    self.hotkeys.suspend()
                    self.hotkeys.set_passthrough(previous_mode)
                    self.error(str(error))
            control = getattr(self.window, name)
            control.blockSignals(True)
            control.setChecked(getattr(self.settings, name))
            control.blockSignals(False)
        self._update_state()

    def _update_state(self):
        self.window.set_state(self.paused, self.busy, self.unavailable)
        self.pause_action.blockSignals(True)
        self.pause_action.setChecked(self.paused)
        self.pause_action.blockSignals(False)
        self.capture_action.setEnabled(not self.paused and not self.busy and not self.unavailable)
        self.capture_action.setText(f"{t('Сделать снимок')}  ·  {self.settings.hotkey.label}")
        state = t("пауза") if self.paused else t("выберите источник") if self.unavailable else self.settings.hotkey.label
        self.tray.setToolTip(f"DekstopShot · {state}")

    def toggle_pause(self):
        if self.dialog or self.quitting:
            return
        if self.paused:
            try:
                self.hotkeys.resume()
            except OSError as error:
                self.error(str(error))
                self._update_state()
                return
            self.paused = False
        else:
            self.hotkeys.suspend()
            self.paused = True
        self._update_state()
        self.window.show_message("Захват на паузе. Клавиша освобождена." if self.paused else "Захват снова работает.")

    def change_hotkey(self):
        if self.dialog or self.busy:
            return
        old = self.settings.hotkey
        self.hotkeys.suspend()
        self.dialog = HotkeyDialog(self.window, old)
        self._style_dialog(self.dialog)

        def apply(candidate: Hotkey):
            try:
                self.hotkeys.replace(candidate)
            except OSError as error:
                self.dialog.show_error(str(error))
                return
            if not self._save(replace(self.settings, hotkey=candidate)):
                self.hotkeys.suspend()
                self.hotkeys.current = old
                self.dialog.show_error("Не удалось сохранить настройки. Старая клавиша сохранена.")
                return
            self.window.update_hotkey(candidate)
            self.dialog.accept()

        self.dialog.save_requested.connect(apply)
        self.dialog.exec()
        self.dialog.deleteLater()
        self.dialog = None
        if self.quitting:
            return
        if self.paused:
            self.hotkeys.suspend()
        else:
            try:
                self.hotkeys.resume()
            except OSError as error:
                self.paused = True
                self.error(str(error))
        self._update_state()

    def capture(self):
        if self.busy or self.paused or self.dialog or self.quitting or self.app.activeModalWidget():
            return
        self.refresh_sources()
        if self.unavailable:
            self.error("Источник недоступен. Выберите монитор или открытое окно приложения.")
            return
        self.busy = True
        self.restore_window = self.window.isVisible()
        self._update_state()
        self.window.hide()
        # Let DWM remove our own window and the tray menu before taking the screenshot.
        QTimer.singleShot(220, self._start_job)

    def _start_job(self):
        if self.quitting:
            self._finish()
            return
        self.job = CaptureJob(self.api, self.settings, self.target)
        self.job.signals.succeeded.connect(self._copy_result)
        self.job.signals.failed.connect(self._capture_failed)
        self.pool.start(self.job)

    def _copy_result(self, payload: CapturePayload, attempt=0):
        if self.quitting:
            self._finish()
            return
        try:
            self.api.write_clipboard(self.hwnd, payload.dib, payload.png)
        except ClipboardBusy:
            if attempt < 7:
                QTimer.singleShot(60 + attempt * 40, lambda: self._copy_result(payload, attempt + 1))
                return
            self._capture_failed("Буфер обмена занят другим приложением. Повторите снимок через секунду.")
            return
        except (OSError, MemoryError) as error:
            self._capture_failed(str(error))
            return
        text = f"Скопировано · {payload.width} × {payload.height} px · {datetime.now():%H:%M:%S} · Вставка: Ctrl + V"
        self.window.show_message(text)
        self._finish()

    def _capture_failed(self, message: str):
        self.error(message)
        self._finish()

    def _finish(self):
        self.busy = False
        self.job = None
        if self.quitting:
            self.app.quit()
            return
        self._update_state()
        if self.restore_window:
            self.window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.window.show()
            self.restore_window = False

    def error(self, message: str):
        log.warning("%s", message)
        self.window.show_message(t(message), True)
        # Report failures; successful captures stay silent in the system tray.
        self.tray.showMessage(t("DekstopShot — требуется внимание"), t(message),
                              QSystemTrayIcon.MessageIcon.Warning, 4500)

    def open_link(self, url: str):
        if not QDesktopServices.openUrl(QUrl(url)):
            self.error("Не удалось открыть браузер. Проверьте браузер по умолчанию в Windows.")

    def show_help(self):
        dialog = GlassDialog(self.window)
        self._style_dialog(dialog)
        dialog.setWindowTitle(t("Как пользоваться DekstopShot"))
        dialog.setMinimumSize(440, 400)
        available = (self.window.screen() or self.app.primaryScreen()).availableGeometry()
        dialog.resize(min(600, available.width() - 40), min(700, available.height() - 40))
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(28, 25, 28, 25)
        layout.setSpacing(16)
        layout.addWidget(label(t("Снимок за одно нажатие"), "title"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(label("\n\n".join(t(paragraph) for paragraph in HELP_PARAGRAPHS), wrap=True))
        layout.addWidget(scroll, 1)
        close = button(t("Понятно"), role="primary")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        self.hotkeys.suspend()
        dialog.exec()
        dialog.deleteLater()
        if self.quitting:
            return
        if not self.paused:
            try:
                self.hotkeys.resume()
            except OSError as error:
                self.paused = True
                self.error(str(error))
                self._update_state()

    def quit(self):
        if self.quitting:
            return
        self.quitting = True
        self.updater.close()
        self.hotkeys.close()
        self.tray.hide()
        self.window.hide()
        if not self.busy:
            self.app.quit()


def configure_logging() -> Path:
    path = SettingsStore().path.parent / "dekstopshot.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=300_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.setLevel(logging.INFO)
    log.addHandler(handler)
    return path


def main() -> int:
    if sys.platform != "win32":
        print("DekstopShot предназначен для Windows 10/11 x64. Предпросмотр: python tools/preview.py")
        return 1
    api = WindowsAPI()
    api.enable_dpi()
    app = QApplication(sys.argv)
    app.setApplicationName("DekstopShot")
    app.setOrganizationName("DekstopShot")
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    startup_store = SettingsStore()
    startup_settings = startup_store.load()
    set_language(startup_settings.language)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "DekstopShot",
                             t("Системный трей недоступен. Запустите приложение в обычном сеансе Windows."))
        return 1
    mutex = api.acquire_instance()
    if not mutex:
        QMessageBox.information(None, t("DekstopShot уже работает"),
                                t("Откройте значок DekstopShot в трее рядом с часами. Он может быть скрыт под стрелкой ↑."))
        return 0
    try:
        try:
            log_path = configure_logging()
        except OSError:
            log_path = None
            log.addHandler(logging.NullHandler())

        def exception_hook(exc_type, value, traceback):
            log.critical("Unhandled exception", exc_info=(exc_type, value, traceback))
            text = t("Произошла ошибка. Закройте DekstopShot и запустите его снова.")
            if log_path:
                text += "\n" + t("Журнал: {path}", path=log_path)
            QMessageBox.critical(None, "DekstopShot", text)

        sys.excepthook = exception_hook
        controller = Controller(app, api, store=startup_store, settings=startup_settings)
        result = app.exec()
        controller.pool.waitForDone(10000)
        return result
    finally:
        api.kernel.CloseHandle(mutex)
