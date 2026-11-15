"""Configuration management for Pill v3."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def app_base_dir() -> Path:
    """Return persistent directory next to Pill.exe (frozen) or project root (dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(rel_path: str) -> Path:
    """Resolve bundled read-only asset path inside PyInstaller _MEIPASS or repo root."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidate = Path(meipass) / rel_path
        if candidate.exists():
            return candidate
    return app_base_dir() / rel_path


def default_downloads_dir() -> str:
    """Return the user's default Downloads folder path."""
    return str(Path.home() / "Downloads")


def default_quick_folders() -> list[dict[str, Any]]:
    """Return default quick folders (up to 5) shown in the Home slide-out Folders menu."""
    dl = default_downloads_dir()
    items: list[dict[str, Any]] = [{"name": "Downloads", "path": dl, "watch": True}]
    docs = Path.home() / "Documents"
    if docs.exists():
        items.append({"name": "Documents", "path": str(docs), "watch": False})
    return items[:5]


@dataclass
class AppearanceConfig:
    theme_name: str = "Warm Obsidian"
    bg_color: str = "#0B0B0E"
    surface_color: str = "#15151A"
    accent_color: str = "#E2A86B"
    ambient_glow_color: str = "#7A4E28"
    text_color: str = "#F4F2EE"
    muted_color: str = "#8C877E"
    base_opacity: float = 0.96
    idle_fade_enabled: bool = True
    idle_opacity: float = 0.42
    idle_delay_sec: int = 8
    always_on_top: bool = True
    hidden: bool = False
    vertical_offset_px: int = 72
    # UI language ("en" | "uk" | "ru")
    language: str = "en"
    # Static PNG character / avatar
    mascot_path: str = ""
    mascot_size: int = 24
    # Dynamic closed-pill elements (auto-shrinks width so there is zero empty gap)
    compact_show_mascot: bool = True
    compact_show_clock: bool = True
    compact_show_weather: bool = True
    compact_show_music: bool = True
    compact_show_timer: bool = True


@dataclass
class ModulesConfig:
    show_clock: bool = True
    show_weather: bool = True
    show_music: bool = True
    show_volume: bool = True
    show_day_progress: bool = True
    show_overview_tiles: bool = True
    overview_tile_1: str = "cpu"
    overview_tile_2: str = "ram"
    overview_tile_3: str = "disk_c"
    show_capslock_toast: bool = True
    show_device_toast: bool = True
    show_download_toast: bool = True
    show_clipboard: bool = True
    ocr_api_key: str = ""


@dataclass
class DownloadsConfig:
    watch_folders: list[str] = field(default_factory=lambda: [default_downloads_dir()])
    quick_folders: list[dict[str, Any]] = field(default_factory=default_quick_folders)


@dataclass
class WeatherConfig:
    api_key: str = ""
    city: str = "London"
    units: str = "metric"  # "metric" or "imperial"
    refresh_minutes: int = 15


@dataclass
class ClipboardConfig:
    max_items: int = 15


@dataclass
class FocusConfig:
    todo_items: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {"text": "Explore dashboard modules", "done": False},
            {"text": "Choose PNG mascot", "done": False},
        ]
    )
    alarms: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AppConfig:
    appearance: AppearanceConfig = field(default_factory=AppearanceConfig)
    modules: ModulesConfig = field(default_factory=ModulesConfig)
    downloads: DownloadsConfig = field(default_factory=DownloadsConfig)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    clipboard: ClipboardConfig = field(default_factory=ClipboardConfig)
    focus: FocusConfig = field(default_factory=FocusConfig)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        """Create AppConfig from a dictionary, filling missing keys with defaults."""
        cfg = cls()
        _update_dataclass(cfg.appearance, data.get("appearance", {}))
        _update_dataclass(cfg.modules, data.get("modules", {}))
        _update_dataclass(cfg.downloads, data.get("downloads", {}))
        _update_dataclass(cfg.weather, data.get("weather", {}))
        _update_dataclass(cfg.clipboard, data.get("clipboard", {}))
        _update_dataclass(cfg.focus, data.get("focus", {}))

        cfg.appearance.base_opacity = max(0.3, min(1.0, float(cfg.appearance.base_opacity)))
        cfg.appearance.idle_opacity = max(0.1, min(1.0, float(cfg.appearance.idle_opacity)))
        cfg.appearance.idle_delay_sec = max(1, min(300, int(cfg.appearance.idle_delay_sec)))
        cfg.appearance.vertical_offset_px = max(20, min(700, int(cfg.appearance.vertical_offset_px)))
        cfg.appearance.mascot_size = max(16, min(44, int(cfg.appearance.mascot_size)))
        if cfg.appearance.language not in ("uk", "ru", "en"):
            cfg.appearance.language = "en"
        cfg.weather.refresh_minutes = max(5, min(120, int(cfg.weather.refresh_minutes)))
        cfg.clipboard.max_items = max(3, min(50, int(cfg.clipboard.max_items)))
        if not cfg.downloads.watch_folders:
            cfg.downloads.watch_folders = [default_downloads_dir()]
        if not isinstance(cfg.downloads.quick_folders, list) or not cfg.downloads.quick_folders:
            cfg.downloads.quick_folders = default_quick_folders()
        else:
            cfg.downloads.quick_folders = cfg.downloads.quick_folders[:5]
        if not isinstance(cfg.focus.todo_items, list):
            cfg.focus.todo_items = []
        if not isinstance(cfg.focus.alarms, list):
            cfg.focus.alarms = []
        return cfg


def _update_dataclass(obj: Any, values: dict[str, Any]) -> None:
    if not isinstance(values, dict):
        return
    for key, val in values.items():
        if hasattr(obj, key):
            setattr(obj, key, val)


class ConfigManager:
    """Handles loading and saving AppConfig to a JSON file."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else app_base_dir() / "config.json"
        self.config = self.load()

    def load(self) -> AppConfig:
        if not self.path.exists():
            cfg = AppConfig()
            self.save(cfg)
            return cfg
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return AppConfig.from_dict(raw)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return AppConfig()

    def save(self, cfg: AppConfig | None = None) -> None:
        if cfg is not None:
            self.config = cfg
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.config.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
