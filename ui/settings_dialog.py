"""Inline settings (v4): animated accordion sections, fixed spinboxes, and live EN/RU/UA localization."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.config import AppConfig, AppearanceConfig, default_downloads_dir
from core.i18n import LANGUAGES, set_language, tr
from core.themes import THEMES, apply_preset
from services.autostart import is_autostart_enabled, set_autostart_enabled
from ui.anim import CollapsibleSection, PillButton
from ui.widgets import OVERVIEW_TILE_OPTIONS, SmoothCheckBox, get_tile_options


def _muted(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("MutedLabel")
    return lbl


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("SectionLabel")
    return lbl


class _Swatch(QLabel):
    def __init__(self, size: int = 22) -> None:
        super().__init__()
        self.setFixedSize(size, size)
        self._size = size

    def set_color(self, hex_str: str) -> None:
        self.setStyleSheet(
            f"background-color: {hex_str}; border-radius: {self._size // 2}px;"
            " border: 1px solid rgba(255,255,255,0.35);"
        )


class InlineSettingsPanel(QWidget):
    """Accordion-style customization page with live EN/RU/UA localization."""

    settings_applied = Signal(object)  # AppConfig
    back_requested = Signal()

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cfg = deepcopy(config)
        set_language(self._cfg.appearance.language)
        self._loading = False
        self._rgb_target = "accent_color"
        self._rgb_target_btns: dict[str, PillButton] = {}
        self._theme_buttons: dict[str, PillButton] = {}
        self._lang_btns: dict[str, PillButton] = {}
        self._checkboxes: list[SmoothCheckBox] = []
        self.sections: list[CollapsibleSection] = []
        self._build_ui()
        self.load_config(config)

    # ── Layout ─────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 2, 0, 0)
        root.setSpacing(6)

        # ── Top Language Switcher Bar (UA / RU / EN) ───────────────────
        lang_row = QHBoxLayout()
        lang_row.setContentsMargins(2, 0, 6, 2)
        lang_row.setSpacing(6)
        self.lang_title_lbl = _muted(tr("lang_label"))
        lang_row.addWidget(self.lang_title_lbl)
        lang_row.addStretch()
        for code, title in LANGUAGES:
            lb = PillButton(title)
            lb.setFixedHeight(24)
            lb.setFixedWidth(48)
            lb.clicked.connect(lambda _=False, c=code: self._select_language(c))
            self._lang_btns[code] = lb
            lang_row.addWidget(lb)
        root.addLayout(lang_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.scroll.viewport().setAutoFillBackground(False)

        content = QWidget()
        self._list_lay = QVBoxLayout(content)
        self._list_lay.setContentsMargins(0, 0, 6, 4)
        self._list_lay.setSpacing(6)

        self.sec_colors = self._add_section(tr("sec_colors_title"), "", "palette")
        self._build_colors(self.sec_colors.body_layout)

        self.sec_mascot = self._add_section(tr("sec_mascot_title"), "", "person")
        self._build_mascot(self.sec_mascot.body_layout)

        self.sec_compact = self._add_section(tr("sec_compact_title"), "", "pill")
        self._build_compact(self.sec_compact.body_layout)

        self.sec_modules = self._add_section(tr("sec_modules_title"), "", "grid")
        self._build_modules(self.sec_modules.body_layout)

        self.sec_behavior = self._add_section(tr("sec_behavior_title"), "", "sliders")
        self._build_behavior(self.sec_behavior.body_layout)

        self.sec_folders = self._add_section(tr("sec_folders_title"), "", "folder")
        self._build_folders(self.sec_folders.body_layout)

        self.sec_weather = self._add_section(tr("sec_weather_title"), "", "cloud_sun")
        self._build_weather(self.sec_weather.body_layout)

        self._list_lay.addStretch()
        self.scroll.setWidget(content)
        root.addWidget(self.scroll, 1)

    def _add_section(self, title: str, subtitle: str, icon: str) -> CollapsibleSection:
        sec = CollapsibleSection(title, subtitle, icon)
        sec.expanded_changed.connect(lambda on, s=sec: self._on_section_toggled(s, on))
        self.sections.append(sec)
        self._list_lay.addWidget(sec)
        return sec

    def _on_section_toggled(self, sec: CollapsibleSection, on: bool) -> None:
        if not on:
            return
        for other in self.sections:
            if other is not sec and other.is_expanded():
                other.set_expanded(False)
        QTimer.singleShot(340, lambda: self.scroll.ensureWidgetVisible(sec, 0, 6))

    def _make_checkbox(self, text: str) -> SmoothCheckBox:
        chk = SmoothCheckBox(text)
        chk.toggled.connect(lambda _=False: self._emit_live())
        self._checkboxes.append(chk)
        return chk

    # ── Section builders ───────────────────────────────────────────────
    def _build_colors(self, lay: QVBoxLayout) -> None:
        self.presets_sec_lbl = _section_label(tr("presets_lbl"))
        lay.addWidget(self.presets_sec_lbl)
        presets = QGridLayout()
        presets.setHorizontalSpacing(6)
        presets.setVerticalSpacing(6)
        for i, t_name in enumerate(THEMES):
            b = PillButton(t_name)
            b.setFixedHeight(26)
            b.clicked.connect(lambda _=False, n=t_name: self._select_theme(n))
            self._theme_buttons[t_name] = b
            presets.addWidget(b, i // 3, i % 3)
        lay.addLayout(presets)

        lay.addSpacing(2)
        self.custom_rgb_sec_lbl = _section_label(tr("custom_rgb_lbl"))
        lay.addWidget(self.custom_rgb_sec_lbl)
        target_row = QHBoxLayout()
        target_row.setSpacing(6)
        for field, key in (
            ("accent_color", "rgb_accent"),
            ("bg_color", "rgb_bg"),
            ("ambient_glow_color", "rgb_glow"),
        ):
            tb = PillButton(tr(key))
            tb.setFixedHeight(26)
            tb.clicked.connect(lambda _=False, f=field: self._set_rgb_target(f))
            self._rgb_target_btns[field] = tb
            target_row.addWidget(tb)
        target_row.addStretch()
        self.rgb_preview_box = _Swatch(24)
        target_row.addWidget(self.rgb_preview_box)
        self.hex_edit = QLineEdit("#E2A86B")
        self.hex_edit.setFixedWidth(82)
        self.hex_edit.setFixedHeight(26)
        self.hex_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hex_edit.returnPressed.connect(self._on_hex_entered)
        self.hex_edit.editingFinished.connect(self._on_hex_entered)
        target_row.addWidget(self.hex_edit)
        lay.addLayout(target_row)

        self.r_slider, self.r_spin = self._create_rgb_channel("R", "#F43F5E", lay)
        self.g_slider, self.g_spin = self._create_rgb_channel("G", "#34D399", lay)
        self.b_slider, self.b_spin = self._create_rgb_channel("B", "#38BDF8", lay)

    def _create_rgb_channel(self, label_text: str, color_hex: str, parent_layout: QVBoxLayout) -> tuple[QSlider, QSpinBox]:
        row = QHBoxLayout()
        row.setSpacing(10)
        lbl = QLabel(label_text)
        lbl.setFixedWidth(12)
        lbl.setStyleSheet(f"color: {color_hex}; font-weight: 800; font-size: 11px;")
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 255)
        slider.setStyleSheet(
            f"QSlider::sub-page:horizontal {{ background: {color_hex}; border-radius: 2px; }}"
        )
        # Note: avoid NoButtons on QSpinBox because Qt6 QStyleSheetStyle shrinks its lineEdit to 1px;
        # instead hide up/down subcontrols in themes.py QSS so the edit field takes full width.
        spin = QSpinBox()
        spin.setRange(0, 255)
        spin.setFixedWidth(56)
        spin.setFixedHeight(26)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        slider.valueChanged.connect(lambda v: self._on_rgb_channel_changed(slider, spin, v))
        spin.valueChanged.connect(lambda v: self._on_rgb_channel_changed(spin, slider, v))
        row.addWidget(lbl)
        row.addWidget(slider, 1)
        row.addWidget(spin)
        parent_layout.addLayout(row)
        return slider, spin

    def _build_mascot(self, lay: QVBoxLayout) -> None:
        self.mascot_path_edit = QLineEdit()
        self.mascot_path_edit.setPlaceholderText(tr("mascot_ph"))
        self.mascot_path_edit.editingFinished.connect(self._emit_live)
        lay.addWidget(self.mascot_path_edit)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.browse_png_btn = PillButton(tr("choose_file"), icon_kind="folder")
        self.browse_png_btn.setObjectName("AccentBtn")
        self.browse_png_btn.setFixedHeight(28)
        self.browse_png_btn.clicked.connect(self._browse_mascot_png)
        self.clear_png_btn = PillButton(tr("reset"), icon_kind="close")
        self.clear_png_btn.setFixedHeight(28)
        self.clear_png_btn.clicked.connect(self._clear_mascot_png)
        self.mascot_size_lbl = _muted(tr("size_lbl"))
        self.mascot_size_spin = QSpinBox()
        self.mascot_size_spin.setRange(16, 44)
        self.mascot_size_spin.setSuffix(" px")
        self.mascot_size_spin.setFixedWidth(68)
        self.mascot_size_spin.setFixedHeight(26)
        self.mascot_size_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mascot_size_spin.valueChanged.connect(lambda _=0: self._emit_live())
        row.addWidget(self.browse_png_btn)
        row.addWidget(self.clear_png_btn)
        row.addStretch()
        row.addWidget(self.mascot_size_lbl)
        row.addWidget(self.mascot_size_spin)
        lay.addLayout(row)

    def _build_compact(self, lay: QVBoxLayout) -> None:
        self.compact_hint_lbl = _muted(tr("compact_hint"))
        lay.addWidget(self.compact_hint_lbl)
        self.chk_compact_mascot = self._make_checkbox(tr("chk_c_mascot"))
        self.chk_compact_clock = self._make_checkbox(tr("chk_c_clock"))
        self.chk_compact_weather = self._make_checkbox(tr("chk_c_weather"))
        self.chk_compact_music = self._make_checkbox(tr("chk_c_music"))
        self.chk_compact_timer = self._make_checkbox(tr("chk_c_timer"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(2)
        for i, c in enumerate((
            self.chk_compact_mascot,
            self.chk_compact_clock,
            self.chk_compact_weather,
            self.chk_compact_music,
            self.chk_compact_timer,
        )):
            grid.addWidget(c, i // 2, i % 2)
        lay.addLayout(grid)

    def _build_modules(self, lay: QVBoxLayout) -> None:
        self.chk_clock = self._make_checkbox(tr("chk_clock"))
        self.chk_music = self._make_checkbox(tr("chk_music"))
        self.chk_volume = self._make_checkbox(tr("chk_volume"))
        self.chk_day_progress = self._make_checkbox(tr("chk_day_prog"))
        self.chk_overview_tiles = self._make_checkbox(tr("chk_tiles"))
        self.chk_capslock = self._make_checkbox(tr("chk_caps"))
        self.chk_devices = self._make_checkbox(tr("chk_devices"))
        self.chk_downloads = self._make_checkbox(tr("chk_dl"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(2)
        for i, c in enumerate((
            self.chk_clock,
            self.chk_music,
            self.chk_volume,
            self.chk_day_progress,
            self.chk_overview_tiles,
            self.chk_capslock,
            self.chk_devices,
            self.chk_downloads,
        )):
            grid.addWidget(c, i // 2, i % 2)
        lay.addLayout(grid)

        lay.addSpacing(4)
        self.tiles_sec_lbl = _section_label(tr("tiles_lbl"))
        lay.addWidget(self.tiles_sec_lbl)
        slots_row = QHBoxLayout()
        slots_row.setSpacing(6)
        self._overview_slot_kinds = ["cpu", "ram", "disk_c"]
        self.slot_btns: list[PillButton] = []
        for idx in range(3):
            sb = PillButton(f"#{idx + 1}: CPU", icon_kind="chevron_down", icon_size=11)
            sb.setFixedHeight(26)
            sb.clicked.connect(lambda _=False, i=idx: self._open_slot_menu(i))
            self.slot_btns.append(sb)
            slots_row.addWidget(sb, 1)
        lay.addLayout(slots_row)

        clip_row = QHBoxLayout()
        self.clip_max_spin = QSpinBox()
        self.clip_max_spin.setRange(3, 50)
        self.clip_max_spin.setFixedWidth(58)
        self.clip_max_spin.setFixedHeight(26)
        self.clip_max_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clip_max_spin.valueChanged.connect(lambda _=0: self._emit_live())
        self.clip_limit_lbl = _muted(tr("clip_limit"))
        clip_row.addWidget(self.clip_limit_lbl)
        clip_row.addStretch()
        clip_row.addWidget(self.clip_max_spin)
        lay.addLayout(clip_row)

        ocr_row = QHBoxLayout()
        ocr_row.setSpacing(8)
        self.ocr_key_lbl = _muted(tr("ocr_api_key"))
        self.ocr_key_lbl.setFixedWidth(64)
        self.ocr_key_edit = QLineEdit()
        self.ocr_key_edit.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.ocr_key_edit.setPlaceholderText("OCR.space API Key (optional)")
        self.ocr_key_edit.editingFinished.connect(self._emit_live)
        ocr_row.addWidget(self.ocr_key_lbl)
        ocr_row.addWidget(self.ocr_key_edit, 1)
        lay.addLayout(ocr_row)

    def _open_slot_menu(self, slot_idx: int) -> None:
        btn = self.slot_btns[slot_idx]
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #15151A; color: #F4F2EE; border: 1px solid rgba(255,255,255,0.16); border-radius: 8px; padding: 4px; }"
            "QMenu::item { padding: 5px 14px; border-radius: 5px; font-size: 11px; }"
            f"QMenu::item:selected {{ background-color: {self._cfg.appearance.accent_color}; color: #0B0B0E; font-weight: 700; }}"
        )
        for code, title in get_tile_options():
            act = menu.addAction(title)
            act.triggered.connect(lambda _=False, s=slot_idx, c=code: self.set_overview_slot(s, c))
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def set_overview_slot(self, slot_idx: int, kind: str, emit: bool = True) -> None:
        if 0 <= slot_idx < 3:
            self._overview_slot_kinds[slot_idx] = kind
            title_map = dict(get_tile_options())
            short = title_map.get(kind, kind).split(" (")[0]
            self.slot_btns[slot_idx].setText(f"#{slot_idx + 1}: {short}")
            if emit:
                self._emit_live()

    def _slider_row(self, title: str, lo: int, hi: int, slot) -> tuple[QSlider, QLabel, QLabel, QHBoxLayout]:
        row = QHBoxLayout()
        row.setSpacing(10)
        t = _muted(title)
        t.setFixedWidth(104)
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        v = QLabel("")
        v.setFixedWidth(44)
        v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        v.setStyleSheet("font-size: 11px; font-weight: 600;")
        s.valueChanged.connect(slot)
        row.addWidget(t)
        row.addWidget(s, 1)
        row.addWidget(v)
        return s, v, t, row

    def _build_behavior(self, lay: QVBoxLayout) -> None:
        self.y_slider, self.y_val_lbl, self.y_title_lbl, r1 = self._slider_row(
            tr("drop_height"), 24, 520, self._on_y_changed
        )
        self.base_opacity_slider, self.base_opacity_lbl, self.op_title_lbl, r2 = self._slider_row(
            tr("opacity_lbl"), 45, 100, self._on_opacity_changed
        )
        lay.addLayout(r1)
        lay.addLayout(r2)

        fade_row = QHBoxLayout()
        fade_row.setSpacing(10)
        self.idle_fade_chk = self._make_checkbox(tr("idle_fade"))
        self.idle_fade_chk.setFixedWidth(134)
        self.idle_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.idle_opacity_slider.setRange(12, 85)
        self.idle_opacity_slider.valueChanged.connect(lambda _=0: self._emit_live())
        self.idle_delay_spin = QSpinBox()
        self.idle_delay_spin.setRange(2, 120)
        self.idle_delay_spin.setSuffix(" s")
        self.idle_delay_spin.setFixedWidth(58)
        self.idle_delay_spin.setFixedHeight(26)
        self.idle_delay_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.idle_delay_spin.valueChanged.connect(lambda _=0: self._emit_live())
        fade_row.addWidget(self.idle_fade_chk)
        fade_row.addWidget(self.idle_opacity_slider, 1)
        fade_row.addWidget(self.idle_delay_spin)
        lay.addLayout(fade_row)

        flags = QHBoxLayout()
        flags.setSpacing(14)
        self.always_on_top_chk = self._make_checkbox(tr("always_top"))
        self.hidden_chk = self._make_checkbox(tr("hide_tray"))
        flags.addWidget(self.always_on_top_chk)
        flags.addWidget(self.hidden_chk)
        lay.addLayout(flags)

        self.autostart_chk = SmoothCheckBox(tr("autostart_lbl"))
        self.autostart_chk.toggled.connect(self._on_autostart_toggled)
        self._checkboxes.append(self.autostart_chk)
        lay.addWidget(self.autostart_chk)

    def _build_folders(self, lay: QVBoxLayout) -> None:
        self.folders_hint_lbl = _muted(tr("folders_hint"))
        lay.addWidget(self.folders_hint_lbl)
        self.folders_list = QListWidget()
        self.folders_list.setFixedHeight(92)
        lay.addWidget(self.folders_list)

        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        self.folder_name_input = QLineEdit()
        self.folder_name_input.setPlaceholderText(tr("folder_name_ph"))
        self.folder_name_input.setFixedWidth(128)
        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText(tr("folder_path_ph"))
        self.folder_input.returnPressed.connect(self._add_folder_inline)
        self.browse_folder_btn = PillButton("", icon_kind="folder", variant="IconBtn")
        self.browse_folder_btn.setFixedSize(28, 28)
        self.browse_folder_btn.clicked.connect(self._browse_folder)
        add_row.addWidget(self.folder_name_input)
        add_row.addWidget(self.folder_input, 1)
        add_row.addWidget(self.browse_folder_btn)
        lay.addLayout(add_row)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(6)
        self.chk_watch_new_folder = SmoothCheckBox(tr("watch_dl"), checked=True)
        self._checkboxes.append(self.chk_watch_new_folder)

        self.add_folder_btn = PillButton(tr("add_folder"), variant="AccentBtn")
        self.add_folder_btn.setFixedHeight(26)
        self.add_folder_btn.clicked.connect(self._add_folder_inline)

        self.toggle_watch_btn = PillButton(tr("toggle_watch"))
        self.toggle_watch_btn.setFixedHeight(26)
        self.toggle_watch_btn.clicked.connect(self._toggle_selected_folder_watch)

        self.del_folder_btn = PillButton(tr("delete"))
        self.del_folder_btn.setFixedHeight(26)
        self.del_folder_btn.clicked.connect(self._remove_folder)

        ctrl_row.addWidget(self.chk_watch_new_folder)
        ctrl_row.addStretch()
        ctrl_row.addWidget(self.add_folder_btn)
        ctrl_row.addWidget(self.toggle_watch_btn)
        ctrl_row.addWidget(self.del_folder_btn)
        lay.addLayout(ctrl_row)

    def _build_weather(self, lay: QVBoxLayout) -> None:
        k_row = QHBoxLayout()
        k_row.setSpacing(8)
        self.api_lbl = _muted(tr("api_key"))
        self.api_lbl.setFixedWidth(64)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.api_key_edit.setPlaceholderText("OpenWeather API Key")
        k_row.addWidget(self.api_lbl)
        k_row.addWidget(self.api_key_edit, 1)
        lay.addLayout(k_row)

        c_row = QHBoxLayout()
        c_row.setSpacing(8)
        self.city_set_lbl = _muted(tr("city"))
        self.city_set_lbl.setFixedWidth(64)
        self.city_edit = QLineEdit()
        self.city_edit.setPlaceholderText("London")
        self.apply_w_btn = PillButton(tr("apply"), icon_kind="refresh")
        self.apply_w_btn.setObjectName("AccentBtn")
        self.apply_w_btn.setFixedHeight(28)
        self.apply_w_btn.clicked.connect(self._emit_live)
        c_row.addWidget(self.city_set_lbl)
        c_row.addWidget(self.city_edit, 1)
        c_row.addWidget(self.apply_w_btn)
        lay.addLayout(c_row)

        u_row = QHBoxLayout()
        u_row.setSpacing(6)
        self.metric_btn = PillButton(tr("unit_metric"))
        self.imperial_btn = PillButton(tr("unit_imperial"))
        for b in (self.metric_btn, self.imperial_btn):
            b.setFixedHeight(26)
        self.metric_btn.clicked.connect(lambda: self._set_units("metric", emit=True))
        self.imperial_btn.clicked.connect(lambda: self._set_units("imperial", emit=True))
        self.refresh_spin = QSpinBox()
        self.refresh_spin.setRange(5, 120)
        self.refresh_spin.setSuffix(" m")
        self.refresh_spin.setFixedWidth(64)
        self.refresh_spin.setFixedHeight(26)
        self.refresh_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.refresh_spin.valueChanged.connect(lambda _=0: self._emit_live())
        self.refresh_lbl = _muted(tr("refresh_every"))
        u_row.addWidget(self.metric_btn)
        u_row.addWidget(self.imperial_btn)
        u_row.addStretch()
        u_row.addWidget(self.refresh_lbl)
        u_row.addWidget(self.refresh_spin)
        lay.addLayout(u_row)

    # ── Localization ───────────────────────────────────────────────────
    def _select_language(self, lang_code: str) -> None:
        self._cfg.appearance.language = set_language(lang_code)
        for code, b in self._lang_btns.items():
            b.set_active(code == self._cfg.appearance.language)
        self.retranslate_ui()
        self._emit_live()

    def retranslate_ui(self) -> None:
        self.lang_title_lbl.setText(tr("lang_label"))
        self.sec_colors.header.set_title(tr("sec_colors_title"))
        self.sec_mascot.header.set_title(tr("sec_mascot_title"))
        self.sec_compact.header.set_title(tr("sec_compact_title"))
        self.sec_modules.header.set_title(tr("sec_modules_title"))
        self.sec_behavior.header.set_title(tr("sec_behavior_title"))
        self.sec_folders.header.set_title(tr("sec_folders_title"))
        self.sec_weather.header.set_title(tr("sec_weather_title"))

        self.presets_sec_lbl.setText(tr("presets_lbl"))
        self.custom_rgb_sec_lbl.setText(tr("custom_rgb_lbl"))
        self._rgb_target_btns["accent_color"].setText(tr("rgb_accent"))
        self._rgb_target_btns["bg_color"].setText(tr("rgb_bg"))
        self._rgb_target_btns["ambient_glow_color"].setText(tr("rgb_glow"))

        self.mascot_path_edit.setPlaceholderText(tr("mascot_ph"))
        self.browse_png_btn.setText(tr("choose_file"))
        self.clear_png_btn.setText(tr("reset"))
        self.mascot_size_lbl.setText(tr("size_lbl"))

        self.compact_hint_lbl.setText(tr("compact_hint"))
        self.chk_compact_mascot.setText(tr("chk_c_mascot"))
        self.chk_compact_clock.setText(tr("chk_c_clock"))
        self.chk_compact_weather.setText(tr("chk_c_weather"))
        self.chk_compact_music.setText(tr("chk_c_music"))
        self.chk_compact_timer.setText(tr("chk_c_timer"))

        self.chk_clock.setText(tr("chk_clock"))
        self.chk_music.setText(tr("chk_music"))
        self.chk_volume.setText(tr("chk_volume"))
        self.chk_day_progress.setText(tr("chk_day_prog"))
        self.chk_overview_tiles.setText(tr("chk_tiles"))
        self.chk_capslock.setText(tr("chk_caps"))
        self.chk_devices.setText(tr("chk_devices"))
        self.chk_downloads.setText(tr("chk_dl"))
        self.tiles_sec_lbl.setText(tr("tiles_lbl"))
        self.clip_limit_lbl.setText(tr("clip_limit"))
        for i in range(3):
            self.set_overview_slot(i, self._overview_slot_kinds[i], emit=False)

        self.y_title_lbl.setText(tr("drop_height"))
        self.op_title_lbl.setText(tr("opacity_lbl"))
        self.idle_fade_chk.setText(tr("idle_fade"))
        self.always_on_top_chk.setText(tr("always_top"))
        self.hidden_chk.setText(tr("hide_tray"))
        self.autostart_chk.setText(tr("autostart_lbl"))

        self.folders_hint_lbl.setText(tr("folders_hint"))
        self.folder_name_input.setPlaceholderText(tr("folder_name_ph"))
        self.folder_input.setPlaceholderText(tr("folder_path_ph"))
        self.chk_watch_new_folder.setText(tr("watch_dl"))
        self.add_folder_btn.setText(tr("add_folder"))
        self.toggle_watch_btn.setText(tr("toggle_watch"))
        self.del_folder_btn.setText(tr("delete"))

        self.api_lbl.setText(tr("api_key"))
        self.ocr_key_lbl.setText(tr("ocr_api_key"))
        self.city_set_lbl.setText(tr("city"))
        self.apply_w_btn.setText(tr("apply"))
        self.refresh_lbl.setText(tr("refresh_every"))
        self._rebuild_folders_list_widget()
        self._refresh_subtitles()

    # ── RGB & Mascot logic ─────────────────────────────────────────────
    def _set_rgb_target(self, field: str) -> None:
        self._rgb_target = field
        for f, b in self._rgb_target_btns.items():
            b.set_active(f == field)
        self._sync_rgb_controls_from_cfg()

    def _sync_rgb_controls_from_cfg(self) -> None:
        was_loading = self._loading
        self._loading = True
        try:
            hex_val = getattr(self._cfg.appearance, self._rgb_target, "#E2A86B")
            col = QColor(hex_val)
            if not col.isValid():
                col = QColor("#E2A86B")
            for sl, sp, val in (
                (self.r_slider, self.r_spin, col.red()),
                (self.g_slider, self.g_spin, col.green()),
                (self.b_slider, self.b_spin, col.blue()),
            ):
                sl.setValue(val)
                sp.setValue(val)
            self.hex_edit.setText(col.name().upper())
            self.rgb_preview_box.set_color(col.name())
        finally:
            self._loading = was_loading
        self._refresh_color_summary()

    def _refresh_color_summary(self) -> None:
        a = self._cfg.appearance
        self.sec_colors.header.swatches = [a.accent_color, a.bg_color, a.ambient_glow_color]
        self.sec_colors.header.set_subtitle(f"{a.theme_name} · {a.accent_color.upper()}")

    def _on_rgb_channel_changed(self, source_widget, mirror_widget, val: int) -> None:
        mirror_widget.blockSignals(True)
        mirror_widget.setValue(val)
        mirror_widget.blockSignals(False)
        if self._loading:
            return
        col = QColor(self.r_spin.value(), self.g_spin.value(), self.b_spin.value())
        hex_str = col.name().upper()
        self.hex_edit.setText(hex_str)
        self.rgb_preview_box.set_color(hex_str)
        setattr(self._cfg.appearance, self._rgb_target, hex_str)
        self._cfg.appearance.theme_name = "Custom RGB"
        self.apply_appearance(self._cfg.appearance)
        self._refresh_color_summary()
        self._emit_live()

    def _on_hex_entered(self) -> None:
        txt = self.hex_edit.text().strip()
        if not txt.startswith("#"):
            txt = "#" + txt
        col = QColor(txt)
        current = getattr(self._cfg.appearance, self._rgb_target, "")
        if col.isValid() and col.name().upper() != str(current).upper():
            setattr(self._cfg.appearance, self._rgb_target, col.name().upper())
            self._cfg.appearance.theme_name = "Custom RGB"
            self._sync_rgb_controls_from_cfg()
            self.apply_appearance(self._cfg.appearance)
            self._emit_live()

    def _browse_mascot_png(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "PNG / WEBP",
            str(os.path.expanduser("~")),
            "Images (*.png *.webp *.jpg *.jpeg)",
        )
        if file_path:
            self.mascot_path_edit.setText(file_path)
            self._emit_live()

    def _clear_mascot_png(self) -> None:
        self.mascot_path_edit.clear()
        self._emit_live()

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("folders"), os.path.expanduser("~"))
        if folder:
            self.folder_input.setText(folder)
            if not self.folder_name_input.text().strip():
                self.folder_name_input.setText(Path(folder).name or folder)
            self._add_folder_inline()

    def _rebuild_folders_list_widget(self) -> None:
        self.folders_list.clear()
        for entry in self._cfg.downloads.quick_folders[:5]:
            name = str(entry.get("name", "") or Path(str(entry.get("path", ""))).name)
            path = str(entry.get("path", ""))
            watch = bool(entry.get("watch", False))
            badge = "✓" if watch else "—"
            it = QListWidgetItem(f"{name}  ·  {path}   [{badge}]")
            it.setData(Qt.ItemDataRole.UserRole, dict(entry))
            self.folders_list.addItem(it)

    # ── Load & live emit ───────────────────────────────────────────────
    def apply_appearance(self, a: AppearanceConfig) -> None:
        for chk in self._checkboxes:
            chk.set_colors(a.accent_color, a.text_color, a.muted_color)
        for name, btn in self._theme_buttons.items():
            btn.set_active(name == a.theme_name)
        for code, btn in self._lang_btns.items():
            btn.set_active(code == a.language)

    def _refresh_subtitles(self) -> None:
        a = self._cfg.appearance
        items = [
            n for n, on in (
                (tr("chk_c_mascot"), a.compact_show_mascot),
                (tr("chk_c_clock"), a.compact_show_clock),
                (tr("chk_c_weather"), a.compact_show_weather),
                (tr("chk_c_music"), a.compact_show_music),
                (tr("chk_c_timer"), a.compact_show_timer),
            ) if on
        ]
        self.sec_compact.header.set_subtitle(", ".join(items) if items else "Mini")
        self.sec_mascot.header.set_subtitle(
            os.path.basename(a.mascot_path) if a.mascot_path else tr("sec_mascot_sub")
        )
        self.sec_behavior.header.set_subtitle(
            f"Y: {a.vertical_offset_px}px · {round(a.base_opacity * 100)}%"
        )
        self.sec_weather.header.set_subtitle(f"{self._cfg.weather.city} · {self._cfg.weather.refresh_minutes}m")
        n = len(self._cfg.downloads.quick_folders)
        self.sec_folders.header.set_subtitle(f"{n} / 5")
        t_map = dict(get_tile_options())
        s_names = [t_map.get(k, k).split(" (")[0] for k in self._overview_slot_kinds if k != "none"]
        self.sec_modules.header.set_subtitle(
            ", ".join(s_names) if (self._cfg.modules.show_overview_tiles and s_names) else tr("opt_none")
        )

    def load_config(self, config: AppConfig) -> None:
        self._loading = True
        try:
            self._cfg = deepcopy(config)
            set_language(self._cfg.appearance.language)
            a = self._cfg.appearance
            self.apply_appearance(a)
            self._set_rgb_target(self._rgb_target)

            self.mascot_path_edit.setText(a.mascot_path)
            self.mascot_size_spin.setValue(a.mascot_size)

            self.y_slider.setValue(a.vertical_offset_px)
            self.y_val_lbl.setText(f"{a.vertical_offset_px}px")
            self.base_opacity_slider.setValue(round(a.base_opacity * 100))
            self.base_opacity_lbl.setText(f"{round(a.base_opacity * 100)}%")
            self.idle_fade_chk.setChecked(a.idle_fade_enabled)
            self.idle_opacity_slider.setValue(round(a.idle_opacity * 100))
            self.idle_delay_spin.setValue(a.idle_delay_sec)
            self.always_on_top_chk.setChecked(a.always_on_top)
            self.hidden_chk.setChecked(a.hidden)
            self.autostart_chk.setChecked(is_autostart_enabled())

            self.chk_compact_mascot.setChecked(a.compact_show_mascot)
            self.chk_compact_clock.setChecked(a.compact_show_clock)
            self.chk_compact_weather.setChecked(a.compact_show_weather)
            self.chk_compact_music.setChecked(a.compact_show_music)
            self.chk_compact_timer.setChecked(a.compact_show_timer)

            m = self._cfg.modules
            self.chk_clock.setChecked(m.show_clock)
            self.chk_music.setChecked(m.show_music)
            self.chk_volume.setChecked(m.show_volume)
            self.chk_day_progress.setChecked(m.show_day_progress)
            self.chk_overview_tiles.setChecked(m.show_overview_tiles)
            self.chk_capslock.setChecked(m.show_capslock_toast)
            self.chk_devices.setChecked(m.show_device_toast)
            self.chk_downloads.setChecked(m.show_download_toast)
            self.set_overview_slot(0, m.overview_tile_1, emit=False)
            self.set_overview_slot(1, m.overview_tile_2, emit=False)
            self.set_overview_slot(2, m.overview_tile_3, emit=False)
            self.clip_max_spin.setValue(self._cfg.clipboard.max_items)
            self.ocr_key_edit.setText(m.ocr_api_key)

            self._rebuild_folders_list_widget()

            w = self._cfg.weather
            self.api_key_edit.setText(w.api_key)
            self.city_edit.setText(w.city)
            self._set_units(w.units, emit=False)
            self.refresh_spin.setValue(w.refresh_minutes)
            self.retranslate_ui()
        finally:
            self._loading = False
        self._refresh_subtitles()

    def _on_autostart_toggled(self, checked: bool) -> None:
        if self._loading:
            return
        actual = set_autostart_enabled(checked)
        if actual != checked:
            self.autostart_chk.blockSignals(True)
            self.autostart_chk.setChecked(actual)
            self.autostart_chk.blockSignals(False)

    def _on_y_changed(self, val: int) -> None:
        self.y_val_lbl.setText(f"{val}px")
        self._emit_live()

    def _on_opacity_changed(self, val: int) -> None:
        self.base_opacity_lbl.setText(f"{val}%")
        self._emit_live()

    def _set_units(self, units: str, emit: bool = False) -> None:
        self._cfg.weather.units = units
        self.metric_btn.set_active(units != "imperial")
        self.imperial_btn.set_active(units == "imperial")
        if emit:
            self._emit_live()

    def _select_theme(self, name: str) -> None:
        apply_preset(self._cfg.appearance, name)
        self._sync_rgb_controls_from_cfg()
        self.apply_appearance(self._cfg.appearance)
        self._emit_live()

    def _add_folder_inline(self) -> None:
        folder = os.path.expanduser(self.folder_input.text().strip())
        if not folder or len(self._cfg.downloads.quick_folders) >= 5:
            return
        name = self.folder_name_input.text().strip() or Path(folder).name or folder
        watch = self.chk_watch_new_folder.isChecked()
        existing_paths = [str(e.get("path", "")) for e in self._cfg.downloads.quick_folders]
        if folder not in existing_paths:
            self._cfg.downloads.quick_folders.append(
                {"name": name, "path": folder, "watch": watch}
            )
            self._cfg.downloads.quick_folders = self._cfg.downloads.quick_folders[:5]
        self.folder_name_input.clear()
        self.folder_input.clear()
        self._rebuild_folders_list_widget()
        self._emit_live()

    def _toggle_selected_folder_watch(self) -> None:
        row = self.folders_list.currentRow()
        if 0 <= row < len(self._cfg.downloads.quick_folders):
            cur = bool(self._cfg.downloads.quick_folders[row].get("watch", False))
            self._cfg.downloads.quick_folders[row]["watch"] = not cur
            self._rebuild_folders_list_widget()
            self.folders_list.setCurrentRow(row)
            self._emit_live()

    def _remove_folder(self) -> None:
        row = self.folders_list.currentRow()
        if 0 <= row < len(self._cfg.downloads.quick_folders) and len(self._cfg.downloads.quick_folders) > 1:
            self._cfg.downloads.quick_folders.pop(row)
            self._rebuild_folders_list_widget()
            self._emit_live()

    def _emit_live(self) -> None:
        if self._loading:
            return
        a = self._cfg.appearance
        a.mascot_path = self.mascot_path_edit.text().strip()
        a.mascot_size = self.mascot_size_spin.value()
        a.vertical_offset_px = self.y_slider.value()
        a.base_opacity = self.base_opacity_slider.value() / 100.0
        a.idle_fade_enabled = self.idle_fade_chk.isChecked()
        a.idle_opacity = self.idle_opacity_slider.value() / 100.0
        a.idle_delay_sec = self.idle_delay_spin.value()
        a.always_on_top = self.always_on_top_chk.isChecked()
        a.hidden = self.hidden_chk.isChecked()

        a.compact_show_mascot = self.chk_compact_mascot.isChecked()
        a.compact_show_clock = self.chk_compact_clock.isChecked()
        a.compact_show_weather = self.chk_compact_weather.isChecked()
        a.compact_show_music = self.chk_compact_music.isChecked()
        a.compact_show_timer = self.chk_compact_timer.isChecked()

        m = self._cfg.modules
        m.show_clock = self.chk_clock.isChecked()
        m.show_music = self.chk_music.isChecked()
        m.show_volume = self.chk_volume.isChecked()
        m.show_day_progress = self.chk_day_progress.isChecked()
        m.show_overview_tiles = self.chk_overview_tiles.isChecked()
        m.overview_tile_1 = self._overview_slot_kinds[0]
        m.overview_tile_2 = self._overview_slot_kinds[1]
        m.overview_tile_3 = self._overview_slot_kinds[2]
        m.show_capslock_toast = self.chk_capslock.isChecked()
        m.show_device_toast = self.chk_devices.isChecked()
        m.show_download_toast = self.chk_downloads.isChecked()
        m.ocr_api_key = self.ocr_key_edit.text().strip()
        self._cfg.clipboard.max_items = self.clip_max_spin.value()

        watched = [
            str(e.get("path", ""))
            for e in self._cfg.downloads.quick_folders
            if e.get("watch", False) and e.get("path")
        ]
        self._cfg.downloads.watch_folders = watched or [default_downloads_dir()]

        w = self._cfg.weather
        w.api_key = self.api_key_edit.text().strip()
        w.city = self.city_edit.text().strip() or "London"
        w.refresh_minutes = self.refresh_spin.value()

        self._refresh_subtitles()
        self.settings_applied.emit(deepcopy(self._cfg))


SettingsDialog = InlineSettingsPanel
