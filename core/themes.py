"""Theme presets and card-less open-space QSS stylesheet builder."""

from __future__ import annotations

from dataclasses import dataclass

from core.config import AppearanceConfig


@dataclass(frozen=True)
class ThemePreset:
    name: str
    bg_color: str
    surface_color: str
    accent_color: str
    ambient_glow_color: str
    text_color: str
    muted_color: str


THEMES: dict[str, ThemePreset] = {
    "Warm Obsidian": ThemePreset(
        name="Warm Obsidian",
        bg_color="#0B0B0E",
        surface_color="#15151A",
        accent_color="#E2A86B",
        ambient_glow_color="#7A4E28",
        text_color="#F4F2EE",
        muted_color="#8C877E",
    ),
    "Obsidian": ThemePreset(
        name="Obsidian",
        bg_color="#0A0C10",
        surface_color="#131720",
        accent_color="#5E81FF",
        ambient_glow_color="#23387A",
        text_color="#F1F5F9",
        muted_color="#7C8BA1",
    ),
    "Midnight": ThemePreset(
        name="Midnight",
        bg_color="#080F1E",
        surface_color="#111C33",
        accent_color="#38BDF8",
        ambient_glow_color="#154D6E",
        text_color="#F0F6FF",
        muted_color="#7B93B2",
    ),
    "Emerald": ThemePreset(
        name="Emerald",
        bg_color="#091210",
        surface_color="#12211C",
        accent_color="#34D399",
        ambient_glow_color="#14533C",
        text_color="#ECFDF5",
        muted_color="#749B8E",
    ),
    "Crimson": ThemePreset(
        name="Crimson",
        bg_color="#11090D",
        surface_color="#1D1117",
        accent_color="#F43F5E",
        ambient_glow_color="#6E182A",
        text_color="#FFF1F2",
        muted_color="#A17C86",
    ),
}

ACCENT_SWATCHES = [
    "#E2A86B",
    "#5E81FF",
    "#38BDF8",
    "#34D399",
    "#A855F7",
    "#F43F5E",
]


def apply_preset(appearance: AppearanceConfig, theme_name: str) -> None:
    """Apply a named preset's colors to AppearanceConfig."""
    preset = THEMES.get(theme_name)
    if not preset:
        return
    appearance.theme_name = preset.name
    appearance.bg_color = preset.bg_color
    appearance.surface_color = preset.surface_color
    appearance.accent_color = preset.accent_color
    appearance.ambient_glow_color = preset.ambient_glow_color
    appearance.text_color = preset.text_color
    appearance.muted_color = preset.muted_color


def build_pill_qss(a: AppearanceConfig) -> str:
    """Build open-space, borderless Qt stylesheet for the droplet."""
    return f"""
    QWidget {{
        color: {a.text_color};
        font-family: "Segoe UI Variable Display", "Segoe UI", sans-serif;
        background: transparent;
    }}
    QLabel#MutedLabel {{
        color: {a.muted_color};
        font-size: 11px;
    }}
    QLabel#SectionLabel {{
        color: {a.muted_color};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.9px;
    }}
    QLabel#AccentLabel {{
        color: {a.accent_color};
        font-size: 11px;
        font-weight: 600;
    }}
    QLabel#BigMetric {{
        color: {a.text_color};
        font-size: 26px;
        font-weight: 600;
    }}
    QPushButton {{
        background-color: rgba(255, 255, 255, 0.045);
        color: {a.text_color};
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-radius: 9px;
        padding: 4px 10px;
        font-size: 11px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        border-color: {a.accent_color};
        background-color: rgba(255, 255, 255, 0.08);
    }}
    QPushButton[active="true"] {{
        background-color: rgba(255, 255, 255, 0.11);
        border: 1px solid {a.accent_color};
        color: {a.text_color};
    }}
    QPushButton#IconBtn {{
        background-color: transparent;
        border: none;
        border-radius: 8px;
        padding: 0px;
    }}
    QPushButton#IconBtn:hover {{
        background-color: rgba(255, 255, 255, 0.08);
    }}
    QPushButton#AccentBtn {{
        background-color: {a.accent_color};
        color: #0B0B0E;
        border: none;
        border-radius: 9px;
        padding: 4px 12px;
        font-size: 11px;
        font-weight: 700;
    }}
    QPushButton#AccentBtn:hover {{
        background-color: {a.accent_color};
    }}
    QLineEdit {{
        background-color: rgba(255, 255, 255, 0.05);
        color: {a.text_color};
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        padding: 4px 9px;
        font-size: 11px;
    }}
    QSpinBox {{
        background-color: rgba(255, 255, 255, 0.07);
        color: {a.text_color};
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 8px;
        padding: 3px 4px;
        font-size: 11px;
        font-weight: 600;
    }}
    QSpinBox::up-button, QSpinBox::down-button {{
        width: 0px;
        height: 0px;
        border: none;
        background: transparent;
    }}
    QLineEdit:focus, QSpinBox:focus {{
        border-color: {a.accent_color};
        background-color: rgba(255, 255, 255, 0.09);
    }}
    QSlider::groove:horizontal {{
        height: 4px;
        background: rgba(255, 255, 255, 0.10);
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: {a.accent_color};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {a.text_color};
        width: 12px;
        height: 12px;
        margin: -4px 0;
        border-radius: 6px;
    }}
    QListWidget {{
        background-color: transparent;
        border: none;
        padding: 2px;
        outline: none;
        font-size: 12px;
    }}
    QListWidget::item {{
        padding: 6px 10px;
        border-radius: 8px;
        color: {a.text_color};
        margin-bottom: 2px;
    }}
    QListWidget::item:hover {{
        background-color: rgba(255, 255, 255, 0.055);
    }}
    QListWidget::item:selected {{
        background-color: rgba(255, 255, 255, 0.09);
        color: {a.text_color};
    }}
    QScrollBar:vertical {{
        width: 4px;
        background: transparent;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(255, 255, 255, 0.16);
        border-radius: 2px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    """
