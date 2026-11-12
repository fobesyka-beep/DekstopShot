"""Platform-independent settings, key validation and display selection."""

from __future__ import annotations

import json
import os
import struct
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


def _system_language() -> str:
    from .i18n import system_language

    return system_language()

MOD_ALT = 1
MOD_CONTROL = 2
MOD_SHIFT = 4

KEY_NAMES = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x13: "Pause",
    0x20: "Space", 0x21: "Page Up", 0x22: "Page Down", 0x23: "End",
    0x24: "Home", 0x25: "←", 0x26: "↑", 0x27: "→", 0x28: "↓",
    0x2C: "Print Screen", 0x2D: "Insert", 0x2E: "Delete",
    0x6A: "Num *", 0x6B: "Num +", 0x6D: "Num −", 0x6E: "Num .", 0x6F: "Num /",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "−", 0xBE: ".",
    0xBF: "/", 0xC0: "`", 0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'",
}
KEY_NAMES.update({i: chr(i) for i in range(0x30, 0x3A)})
KEY_NAMES.update({i: chr(i) for i in range(0x41, 0x5B)})
KEY_NAMES.update({0x60 + i: f"Num {i}" for i in range(10)})
KEY_NAMES.update({0x70 + i: f"F{i + 1}" for i in range(24) if i != 11})


@dataclass(frozen=True)
class Hotkey:
    vk: int = 0xBD
    modifiers: int = 0

    def __post_init__(self):
        if type(self.vk) is not int or self.vk not in KEY_NAMES:
            raise ValueError("Эта клавиша не поддерживается. F12 зарезервирована Windows.")
        if type(self.modifiers) is not int or not 0 <= self.modifiers <= 7:
            raise ValueError("Используйте Ctrl, Alt и Shift. Сочетания с Win зарезервированы системой.")

    @property
    def label(self) -> str:
        parts = [name for flag, name in ((2, "Ctrl"), (1, "Alt"), (4, "Shift"))
                 if self.modifiers & flag]
        return " + ".join([*parts, KEY_NAMES[self.vk]])


@dataclass(frozen=True)
class Monitor:
    id: str
    device: str
    name: str
    left: int
    top: int
    width: int
    height: int
    primary: bool = False

    @property
    def resolution(self) -> str:
        return f"{self.width} × {self.height}"


@dataclass(frozen=True)
class WindowTarget:
    hwnd: int
    pid: int
    process_start: int
    title: str
    executable: str

    @property
    def label(self) -> str:
        return f"{self.executable} — {self.title}"


def choose_monitor(monitors: list[Monitor], selected_id: str) -> Monitor:
    if not monitors:
        raise ValueError("Windows не обнаружила доступных мониторов.")
    if selected_id:
        for monitor in monitors:
            if monitor.id == selected_id:
                return monitor
        raise ValueError("Закреплённый монитор отключён. Выберите доступный экран в настройках.")
    return next((monitor for monitor in monitors if monitor.primary), monitors[0])


@dataclass(frozen=True)
class Settings:
    hotkey: Hotkey = field(default_factory=Hotkey)
    monitor_id: str = ""
    notifications: bool = False  # Legacy JSON field; successful captures never show a notification.
    start_hidden: bool = False
    capture_mode: str = "monitor"
    version: int = 1
    language: str = field(default_factory=_system_language)
    hotkey_passthrough: bool = True
    save_screenshots: bool = False
    hide_tray_icon: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> Settings:
        if not isinstance(data, dict) or data.get("version", 1) != 1:
            raise ValueError("Неизвестный формат настроек.")
        key = data.get("hotkey", {})
        if not isinstance(key, dict):
            raise ValueError("Повреждены настройки клавиши.")
        monitor_id = data.get("monitor_id", "")
        notifications = data.get("notifications", False)
        hidden = data.get("start_hidden", False)
        mode = data.get("capture_mode", "monitor")
        language = data.get("language", _system_language())
        passthrough = data.get("hotkey_passthrough", True)
        save_screenshots = data.get("save_screenshots", False)
        hide_tray_icon = data.get("hide_tray_icon", False)
        if not isinstance(monitor_id, str) or len(monitor_id) > 4096:
            raise ValueError("Некорректный идентификатор монитора.")
        if any(type(option) is not bool for option in (notifications, hidden, hide_tray_icon)):
            raise ValueError("Некорректные параметры настроек.")
        if mode not in ("monitor", "window"):
            raise ValueError("Неизвестный режим захвата.")
        if language not in ("ru", "en"):
            raise ValueError("Неизвестный язык интерфейса.")
        if type(passthrough) is not bool:
            raise ValueError("Некорректный режим горячей клавиши.")
        if type(save_screenshots) is not bool:
            raise ValueError("Некорректный режим сохранения снимков.")
        return cls(hotkey=Hotkey(key.get("vk", 0xBD), key.get("modifiers", 0)),
                   monitor_id=monitor_id, notifications=notifications,
                   start_hidden=hidden, capture_mode=mode,
                   language=language, hotkey_passthrough=passthrough,
                   save_screenshots=save_screenshots, hide_tray_icon=hide_tray_icon)


class SettingsStore:
    def __init__(self, path: Path | None = None):
        root = Path(os.getenv("LOCALAPPDATA") or Path.home() / ".config")
        self.path = path or root / "DekstopShot" / "settings.json"
        self._legacy_path = root / "GlassShot" / "settings.json" if path is None else None
        self.warning = ""

    def load(self) -> Settings:
        try:
            return Settings.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return self._load_legacy()
        except (OSError, ValueError, TypeError, RecursionError):
            self.warning = "Не удалось прочитать настройки. Используются начальные значения."
            if self.path.exists():
                try:
                    suffix = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                    self.path.rename(self.path.with_suffix(f".broken-{suffix}.json"))
                except OSError:
                    pass
            return Settings()

    def _load_legacy(self) -> Settings:
        """Import valid settings once, leaving the former application's data untouched."""
        if self._legacy_path is None:
            return Settings()
        try:
            settings = Settings.from_dict(json.loads(self._legacy_path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return Settings()
        except (OSError, ValueError, TypeError, RecursionError):
            self.warning = "Не удалось прочитать настройки прежней версии. Используются начальные значения."
            return Settings()
        try:
            self.save(settings)
        except OSError:
            self.warning = "Настройки прежней версии загружены, но не удалось сохранить их для DekstopShot."
        return settings

    def save(self, settings: Settings):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix="settings-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(asdict(settings), stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)


@dataclass(frozen=True)
class Frame:
    width: int
    height: int
    bgra: bytes  # BGRX, top-down, 4 bytes per pixel; alpha is ignored.

    def __post_init__(self):
        if self.width <= 0 or self.height <= 0 or len(self.bgra) != self.width * self.height * 4:
            raise ValueError("Некорректный размер изображения.")

    def dib(self) -> bytes:
        """CF_DIB with a positive height and bottom-up scanlines for broad compatibility."""
        stride = self.width * 4
        header = struct.pack("<IiiHHIIiiII", 40, self.width, self.height, 1, 32,
                             0, len(self.bgra), 0, 0, 0, 0)
        return header + b"".join(self.bgra[y:y + stride]
                                  for y in range(len(self.bgra) - stride, -1, -stride))
