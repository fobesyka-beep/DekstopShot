"""Small RU/EN catalogue shared by widgets, controller and Windows errors."""

from __future__ import annotations

import re

_language: str | None = None


def language_for_locale(name: str) -> str:
    return "ru" if name.lower().replace("_", "-").split("-")[0] == "ru" else "en"


def system_language() -> str:
    from PySide6.QtCore import QLocale

    locale = QLocale.system()
    languages = locale.uiLanguages()
    return language_for_locale(languages[0] if languages else locale.name())


def get_language() -> str:
    return _language or system_language()


def set_language(language: str):
    if language not in ("ru", "en"):
        raise ValueError("Unsupported interface language")
    global _language
    _language = language


EN = {
    "СНИМОК В БУФЕР": "SCREEN TO CLIPBOARD",
    "СНИМОК В БУФЕР ОБМЕНА": "SCREEN TO CLIPBOARD",
    "ОБЩЕЕ": "GENERAL",
    "Язык": "Language",
    "Инструкция": "Instructions",
    "  Инструкция": "  Instructions",
    "Пауза": "Pause",
    "  Пауза": "  Pause",
    "Продолжить": "Resume",
    "  Продолжить": "  Resume",
    "Скрыть в трей": "Hide to tray",
    "  Скрыть в трей": "  Hide to tray",
    "Скрыть окно": "Hide window",
    "Выйти": "Quit",
    "Источник снимка": "Capture source",
    "Горячая клавиша": "Hotkey",
    "Изменить клавишу": "Change hotkey",
    "Весь выбранный монитор": "Entire selected monitor",
    "Окно приложения": "Application window",
    "Выберите монитор": "Select a monitor",
    "Выберите окно приложения": "Select an application window",
    "Выберите открытое окно…": "Select an open window…",
    "Окно закрыто — выберите другое": "Window closed — select another",
    "Закреплённый монитор недоступен": "Pinned monitor unavailable",
    "Закреплён · {resolution} px": "Pinned · {resolution} px",
    " · основной экран": " · primary monitor",
    "Только выбранное окно. Перед снимком разверните его.": "Only the selected window. Restore it before capture.",
    "Продолжи с AI": "Continue with AI",
    "При запуске — сразу в трей": "Start in the system tray",
    "При запуске скрывать окно": "Hide window on startup",
    "Работать без значка в трее": "Run without a tray icon",
    "Когда окно скрыто, DekstopShot продолжает делать снимки по горячей клавише. Значок в трее скрывается. Запустите DekstopShot ещё раз, чтобы открыть окно.": "When the window is hidden, DekstopShot keeps taking screenshots with the hotkey and hides the tray icon. Launch DekstopShot again to reopen the window.",
    "Сохранять в «Изображения»": "Save to Pictures",
    "Сохранять PNG в подпапке DekstopShot системной папки «Изображения».": "Save PNG files in the DekstopShot subfolder of the system Pictures folder.",
    "Готово к работе. Снимок идёт в буфер обмена.": "Ready. Screenshots go to the clipboard.",
    "Готово к работе. Снимок идёт в буфер и сохраняется в «Изображения».": "Ready. Screenshots go to the clipboard and Pictures folder.",
    "Готово к работе. Скриншоты не сохраняются в файлы.": "Ready. Screenshots are not saved to files.",
    "Передавать нажатие активному приложению": "Pass the key to the active app",
    "Не блокировать клавишу": "Allow the key in other apps",
    "Клавиша работает и в других приложениях.": "The key also works in other applications.",
    "Клавиша используется только для снимка.": "The key is reserved for screenshots.",
    "Мониторы не найдены": "No monitors found",
    "На паузе": "Paused",
    "Делаю снимок…": "Capturing…",
    "Выберите источник": "Select a source",
    "Готов к работе": "Ready",
    "Расположение мониторов; выбор также доступен в списке ниже": "Monitor layout; selection is also available in the list below",
    "Компактная схема. Номера совпадают со списком мониторов.": "Compact layout. Numbers match the monitor list.",
    "Перетащить окно настроек": "Drag the settings window",
    "Скрыть в трей; DekstopShot продолжит работать": "Hide to tray; DekstopShot will keep running",
    "Скрыть окно. DekstopShot продолжит работать в фоне.": "Hide the window. DekstopShot will keep running in the background.",
    "Обновить список мониторов": "Refresh the monitor list",
    "Обновить мониторы": "Refresh monitors",
    "Режим захвата: монитор или приложение": "Capture mode: monitor or application",
    "Закреплённый монитор для скриншотов": "Pinned monitor for screenshots",
    "Открытые окна приложений": "Open application windows",
    "Открыть {title} в браузере": "Open {title} in your browser",
    "Открыть {title} в браузере по умолчанию": "Open {title} in your default browser",
    "Открыть диалог": "Open chat",
    "Открыть Gemini": "Open Gemini",
    "Открыть Claude": "Open Claude",
    "Поиск в интернете": "Search the web",
    "Нажмите сочетание…": "Press a shortcut…",
    "Выберите без Win": "Choose a shortcut without Win",
    "Другая клавиша…": "Choose another key…",
    "Твоя горячая клавиша": "Your hotkey",
    "Нажмите клавишу или сочетание с Ctrl, Alt и Shift.\nEsc — отмена. Клавиша Win не поддерживается.": "Press a key or a shortcut with Ctrl, Alt and Shift.\nEsc cancels. The Windows key is not supported.",
    "Минус над буквами и Num − — разные клавиши.": "The top-row minus and numpad minus are different keys.",
    "Отмена": "Cancel",
    "Сохранить": "Save",
    "Понятно": "Got it",
    "Открыть DekstopShot": "Open DekstopShot",
    "Сделать снимок": "Take a screenshot",
    "Сделать снимок  ·  {hotkey}": "Take a screenshot  ·  {hotkey}",
    "Выйти из DekstopShot": "Quit DekstopShot",
    "пауза": "paused",
    "выберите источник": "select a source",
    "Не удалось сохранить настройки: {error}": "Could not save settings: {error}",
    "Монитор закреплён. Горячая клавиша будет снимать именно его.": "Monitor pinned. The hotkey will capture this monitor.",
    "Окно выбрано. После закрытия или перезапуска приложения выберите его заново.": "Window selected. Select it again after closing or restarting the application.",
    "Захват на паузе. Клавиша освобождена.": "Capture paused. The hotkey is released.",
    "Захват снова работает.": "Capture resumed.",
    "Не удалось сохранить настройки. Старая клавиша сохранена.": "Could not save settings. The previous hotkey is kept.",
    "Источник недоступен. Выберите монитор или открытое окно приложения.": "Source unavailable. Select a monitor or an open application window.",
    "Буфер обмена занят другим приложением. Повторите снимок через секунду.": "The clipboard is busy. Try taking the screenshot again in a moment.",
    "Скопировано · {width} × {height} px · {time} · Вставка: Ctrl + V": "Copied · {width} × {height} px · {time} · Paste: Ctrl + V",
    "DekstopShot — требуется внимание": "DekstopShot — attention required",
    "Не удалось открыть браузер. Проверьте браузер по умолчанию в Windows.": "Could not open your browser. Check the default browser in Windows.",
    "Как пользоваться DekstopShot": "How to use DekstopShot",
    "Снимок за одно нажатие": "A screenshot in one keypress",
    "Эта клавиша не поддерживается. F12 зарезервирована Windows.": "This key is not supported. F12 is reserved by Windows.",
    "Используйте Ctrl, Alt и Shift. Сочетания с Win зарезервированы системой.": "Use Ctrl, Alt and Shift. Shortcuts with Win are reserved by the system.",
    "Windows не обнаружила доступных мониторов.": "Windows did not detect any available monitors.",
    "Закреплённый монитор отключён. Выберите доступный экран в настройках.": "The pinned monitor is disconnected. Select an available monitor in settings.",
    "Неизвестный формат настроек.": "Unknown settings format.",
    "Повреждены настройки клавиши.": "Hotkey settings are damaged.",
    "Некорректный идентификатор монитора.": "Invalid monitor identifier.",
    "Некорректные параметры настроек.": "Invalid settings values.",
    "Неизвестный режим захвата.": "Unknown capture mode.",
    "Неизвестный язык интерфейса.": "Unknown interface language.",
    "Некорректный режим горячей клавиши.": "Invalid hotkey mode.",
    "Некорректный режим сохранения снимков.": "Invalid screenshot saving mode.",
    "Не удалось определить системную папку «Изображения».": "Could not locate the system Pictures folder.",
    "Скопировано и сохранено · {width} × {height} px · {time} · Вставка: Ctrl + V": "Copied and saved · {width} × {height} px · {time} · Paste: Ctrl + V",
    "Снимок скопирован в буфер, но не удалось сохранить PNG: {error}": "The screenshot was copied to the clipboard, but could not be saved as PNG: {error}",
    "Не удалось прочитать настройки. Используются начальные значения.": "Could not read settings. Default values are being used.",
    "Не удалось прочитать настройки прежней версии. Используются начальные значения.": "Could not read the previous version's settings. Default values are being used.",
    "Настройки прежней версии загружены, но не удалось сохранить их для DekstopShot.": "Previous settings loaded, but could not be saved for DekstopShot.",
    "Некорректный размер изображения.": "Invalid image dimensions.",
    "Захват и глобальные клавиши доступны только в Windows.": "Capture and global hotkeys are only available on Windows.",
    "Приложение": "Application",
    "Выбранное окно закрыто. Выберите приложение заново.": "The selected window is closed. Select the application again.",
    "Выбранное окно изменилось. Выберите приложение заново.": "The selected window has changed. Select the application again.",
    "Окно приложения свёрнуто. Разверните его перед снимком.": "The application window is minimized. Restore it before capture.",
    "Окно приложения скрыто. Откройте его перед снимком.": "The application window is hidden. Open it before capture.",
    "Клавиша {hotkey} занята Windows или другим приложением. Выберите другое сочетание.": "The hotkey {hotkey} is in use by Windows or another application. Choose another shortcut.",
    "Не удалось подготовить буфер захвата.": "Could not prepare the capture buffer.",
    "Не удалось завершить захват экрана.": "Could not complete the screen capture.",
    "Недостаточно памяти для буфера обмена.": "Not enough memory for the clipboard.",
    "Буфер обмена временно занят.": "The clipboard is temporarily busy.",
    "Windows не вернула изображение окна. Проверьте, что оно открыто.": "Windows did not return a window image. Check that the window is open.",
    "Окно не ответило за 8 секунд. Разверните его и повторите снимок.": "The window did not respond within 8 seconds. Restore it and try again.",
    "Windows прервала захват окна. Попробуйте выбрать его заново.": "Windows interrupted window capture. Try selecting the window again.",
    "Не удалось захватить окно: {error}": "Could not capture the window: {error}",
    "Не удалось подготовить изображение для буфера обмена.": "Could not prepare the clipboard image.",
    "Выберите окно приложения в настройках.": "Select an application window in settings.",
    "Системный трей недоступен. Запустите приложение в обычном сеансе Windows.": "The system tray is unavailable. Run the application in a normal Windows session.",
    "DekstopShot уже работает": "DekstopShot is already running",
    "Откройте значок DekstopShot в трее рядом с часами. Он может быть скрыт под стрелкой ↑.": "Open the DekstopShot tray icon next to the clock. It may be hidden under the ↑ arrow.",
    "Не удалось включить фоновый режим без значка в трее.": "Could not enable background operation without a tray icon.",
    "Не удалось открыть окно уже запущенного приложения.": "Could not reopen the running application.",
    "Произошла ошибка. Закройте DekstopShot и запустите его снова.": "An error occurred. Close DekstopShot and start it again.",
    "Журнал: {path}": "Log: {path}",
    "Обновление {version}": "Update {version}",
    "Открыть страницу релиза {version}": "Open the release page for {version}",
    "Доступно обновление": "Update available",
    "Доступна версия {version}. Откройте настройки, чтобы скачать её.": "Version {version} is available. Open settings to download it.",
    "Не удалось включить передачу горячей клавиши (ошибка Windows {code}).": "Could not enable hotkey pass-through (Windows error {code}).",
    "Не удалось освободить горячую клавишу (ошибка Windows {code}).": "Could not release the hotkey (Windows error {code}).",
    "Передача горячей клавиши доступна только в Windows.": "Hotkey pass-through is only available on Windows.",
    "В блоке «Общее» выберите русский или английский язык. При первом запуске язык определяется по системе.": "Choose Russian or English in General. On first launch, the interface language follows your system.",
    "В боковой панели выберите русский или английский язык. При первом запуске язык определяется по системе.": "Choose Russian or English in the sidebar. On first launch, the interface language follows your system.",
    "Включите сохранение в «Изображения», чтобы каждый успешный снимок также сохранялся в PNG в подпапке DekstopShot системной папки «Изображения». По умолчанию сохранение выключено. Буфер обмена работает в обоих режимах.": "Enable Save to Pictures to save each successful screenshot as a PNG file in the DekstopShot subfolder of your system Pictures folder. Saving is off by default. The clipboard works in both modes.",
    "Кнопки сервисов открывают сайты; снимок вставляется вручную. Google открывает обычный поиск. Приложение не отправляет скриншоты в сеть.": "Service buttons open websites; paste the screenshot manually. Google opens regular web search. The application does not upload screenshots.",
    "Если включено «Передавать нажатие активному приложению», клавиша одновременно работает в других программах. Выключите этот режим, чтобы зарезервировать сочетание для снимка. На паузе захват отключён.": "When key pass-through is enabled, the key also works in other applications. Disable this mode to reserve the shortcut for screenshots. Pausing disables capture.",
    "Если включено «Не блокировать клавишу», клавиша одновременно работает в других программах. Выключите этот режим, чтобы зарезервировать сочетание для снимка. На паузе захват отключён.": "When Allow the key in other apps is enabled, the key also works in other applications. Disable this mode to reserve the shortcut for screenshots. Pausing disables capture.",
    "При запуске DekstopShot проверяет новые версии на GitHub. Если доступно обновление, откройте его страницу по кнопке в настройках и скачайте архив. Автоматической установки нет.": "DekstopShot checks GitHub for new versions at startup. If an update is available, use the button in settings to open its release page and download the archive. Updates are not installed automatically.",
    "Крестик и «Скрыть в трей» скрывают настройки. Чтобы открыть их снова, нажмите значок рядом с часами. Для завершения выберите «Выйти из DekstopShot» в меню трея.": "The close button and Hide to tray hide settings. Click the icon next to the clock to open them again. Choose Quit DekstopShot in the tray menu to exit.",
    "Крестик и «Скрыть окно» скрывают настройки. Чтобы открыть их снова, нажмите значок рядом с часами. Для завершения выберите «Выйти из DekstopShot» в меню трея.": "The close button and Hide window hide settings. Click the icon next to the clock to open them again. Choose Quit DekstopShot in the tray menu to exit.",
    "В режиме без значка повторно запустите DekstopShot, чтобы открыть настройки. Кнопка «Выйти» завершает приложение.": "When running without a tray icon, launch DekstopShot again to reopen settings. Use Quit to exit the application.",
    "Для снимка приложения окно должно быть открыто и не свёрнуто. После закрытия окна или перезапуска DekstopShot выберите его заново.": "To capture an application, its window must be open and not minimized. Select it again after closing the window or restarting DekstopShot.",
    "Кнопки сервисов открывают сайты; снимок вставляется вручную. Google открывает обычный поиск. Скриншоты не записываются в файлы и не отправляются приложением.": "Service buttons open websites; paste the screenshot manually. Google opens regular web search. The application does not save screenshots to files or upload them.",
    "1. Выберите монитор или открытое окно приложения.": "1. Select a monitor or an open application window.",
    "2. Нажмите горячую клавишу. По умолчанию — минус над буквами.": "2. Press your hotkey. The default is the top-row minus key.",
    "3. Откройте нужную программу и нажмите Ctrl + V.": "3. Open the application you need and press Ctrl + V.",
}


def _match_template(template: str, value: str):
    fields = re.findall(r"\{(\w+)\}", template)
    if not fields:
        return None
    expression = re.escape(template)
    for field in fields:
        expression = expression.replace(re.escape("{" + field + "}"), f"(?P<{field}>.+?)")
    return re.fullmatch(expression, value, re.DOTALL)


def canonical_source(text: str) -> str:
    """Keep feedback switchable even when a caller has translated it already."""
    for source, english in EN.items():
        if text == english:
            return source
        match = _match_template(english, text)
        if match:
            return source.format(**{key: canonical_source(value) for key, value in match.groupdict().items()})
    return text


def t(source: str, **values) -> str:
    """Translate a source/template, including errors arriving from a capture child."""
    source = canonical_source(source)
    result = source
    if get_language() == "en":
        result = EN.get(source, source)
        if result == source and not values:
            # Child-process and native exceptions can arrive already formatted.
            for template, english in EN.items():
                match = _match_template(template, source)
                if match:
                    result = english.format(**{key: t(value) for key, value in match.groupdict().items()})
                    break
    if values:
        return result.format(**values)
    return result
