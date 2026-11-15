"""Spacious 520x360 open-space expanded droplet panel (v4) with lively animations, full Головна dashboard, redesigned Текст і Переклад, and accordion Налаштування."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.config import AppConfig, AppearanceConfig, ModulesConfig
from core.i18n import set_language, tr
from services.media_smtc import MediaInfo
from services.screen_ocr import OcrService
from services.text_tools import (
    LANG_NAMES,
    TRANSLATOR_SOURCE_LANGS,
    TRANSLATOR_TARGET_LANGS,
    TranslatorService,
    fix_keyboard_layout,
    lang_display_name,
    looks_like_wrong_layout,
)
from services.weather import WeatherData
from ui.anim import GlassTile, LoadingDots, PillButton, Theme
from ui.icons import WaveformWidget, render_vector_icon, render_vector_pixmap
from ui.settings_dialog import InlineSettingsPanel
from ui.widgets import (
    CharacterBadgeWidget,
    DotIndicatorBar,
    HumidityBarWidget,
    PressureArcWidget,
    ScreenEyedropperOverlay,
    ScreenOcrOverlay,
    SmoothCheckBox,
    SystemStatsWidget,
    ThinDivider,
    TimerRingWidget,
    WeekDayProgressWidget,
    WindCompassWidget,
)


PAGE_COUNT = 6


def _page_title(idx: int) -> str:
    return tr(f"page_{max(0, min(PAGE_COUNT - 1, idx))}")


class QuickFoldersPopup(QWidget):
    """Animated slide-out mini-menu displaying up to 5 favorite folders on Головна."""

    folder_clicked = Signal(str)
    configure_requested = Signal()
    closed = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._is_open = False
        self.setVisible(False)

        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(0.0)
        self.setGraphicsEffect(self._fx)

        self._geo_anim = QPropertyAnimation(self, b"geometry", self)
        self._op_anim = QPropertyAnimation(self._fx, b"opacity", self)
        self._op_anim.finished.connect(self._on_anim_done)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(8, 8, 8, 8)
        self._lay.setSpacing(4)

    def is_open(self) -> bool:
        return self._is_open

    def rebuild_items(self, folders: list[dict]) -> None:
        while self._lay.count():
            it = self._lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        head = QLabel(tr("quick_folders_head"))
        head.setObjectName("SectionLabel")
        head.setContentsMargins(4, 0, 4, 2)
        self._lay.addWidget(head)

        for entry in folders[:5]:
            raw_path = str(entry.get("path", ""))
            name = str(entry.get("name", "") or Path(raw_path).name or raw_path)
            btn = PillButton(name, icon_kind="folder", icon_size=13)
            btn.set_align_left(True)
            btn.setFixedHeight(26)
            btn.setToolTip(raw_path)
            btn.clicked.connect(lambda _=False, p=raw_path: self._on_pick(p))
            self._lay.addWidget(btn)

        cfg_btn = PillButton(tr("quick_folders_cfg"), icon_kind="sliders", variant="GhostBtn", icon_size=12)
        cfg_btn.setFixedHeight(24)
        cfg_btn.clicked.connect(self._on_cfg)
        self._lay.addWidget(cfg_btn)

    def _on_pick(self, path: str) -> None:
        self.close_menu()
        self.folder_clicked.emit(path)

    def _on_cfg(self) -> None:
        self.close_menu()
        self.configure_requested.emit()

    def toggle_above(self, anchor_btn: QWidget, folders: list[dict]) -> None:
        if self._is_open:
            self.close_menu()
        else:
            self.open_above(anchor_btn, folders)

    def open_above(self, anchor_btn: QWidget, folders: list[dict]) -> None:
        self.rebuild_items(folders)
        self._is_open = True
        count = min(5, max(1, len(folders)))
        h = 34 + count * 30 + 28
        w = max(220, anchor_btn.width() + 20)
        btn_pos = anchor_btn.mapTo(self.parentWidget(), QPoint(0, 0))
        x = max(4, min(self.parentWidget().width() - w - 4, btn_pos.x()))
        end_y = max(4, btn_pos.y() - h - 6)
        end_rect = QRect(x, end_y, w, h)
        start_rect = QRect(x, btn_pos.y() - 18, w, 18)

        self.setGeometry(start_rect)
        self.setVisible(True)
        self.raise_()

        self._geo_anim.stop()
        self._geo_anim.setDuration(240)
        self._geo_anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._geo_anim.setStartValue(start_rect)
        self._geo_anim.setEndValue(end_rect)

        self._op_anim.stop()
        self._op_anim.setDuration(180)
        self._op_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._op_anim.setStartValue(0.0)
        self._op_anim.setEndValue(1.0)

        self._geo_anim.start()
        self._op_anim.start()

    def close_menu(self) -> None:
        if not self._is_open:
            return
        self._is_open = False
        cur = self.geometry()
        end_rect = QRect(cur.x(), cur.bottom() - 14, cur.width(), 14)

        self._geo_anim.stop()
        self._geo_anim.setDuration(165)
        self._geo_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._geo_anim.setStartValue(cur)
        self._geo_anim.setEndValue(end_rect)

        self._op_anim.stop()
        self._op_anim.setDuration(155)
        self._op_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._op_anim.setStartValue(self._fx.opacity())
        self._op_anim.setEndValue(0.0)

        self._geo_anim.start()
        self._op_anim.start()
        self.closed.emit()

    def _on_anim_done(self) -> None:
        if not self._is_open:
            self.setVisible(False)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        bg = QColor(Theme.bg)
        bg.setAlpha(246)
        p.setBrush(bg)
        border = QColor(Theme.accent)
        border.setAlpha(155)
        p.setPen(QPen(border, 1.2))
        p.drawRoundedRect(r, 13.0, 13.0)
        p.end()


class LangSelectPopup(QWidget):
    """Animated expanding dropdown menu for picking translator source/target languages."""

    language_selected = Signal(str, str)  # role ("src"|"tgt"), lang_code
    closed = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._is_open = False
        self._role = ""
        self.setVisible(False)

        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(0.0)
        self.setGraphicsEffect(self._fx)

        self._geo_anim = QPropertyAnimation(self, b"geometry", self)
        self._op_anim = QPropertyAnimation(self._fx, b"opacity", self)
        self._op_anim.finished.connect(self._on_anim_done)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(6, 6, 6, 6)
        self._lay.setSpacing(3)

    def is_open(self) -> bool:
        return self._is_open

    def current_role(self) -> str:
        return self._role

    def open_for(self, anchor_btn: QWidget, codes: tuple[str, ...], current_code: str, role: str) -> None:
        if self._is_open and self._role == role:
            self.close_menu()
            return
        self._role = role
        while self._lay.count():
            it = self._lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        for code in codes:
            btn = PillButton(lang_display_name(code))
            btn.set_align_left(True)
            btn.setFixedHeight(24)
            btn.set_active(code == current_code)
            btn.clicked.connect(lambda _=False, c=code, r=role: self._pick(r, c))
            self._lay.addWidget(btn)

        self._is_open = True
        w = max(136, anchor_btn.width() + 28)
        h = 12 + len(codes) * 27 - 3
        btn_pos = anchor_btn.mapTo(self.parentWidget(), QPoint(0, 0))
        parent_h = self.parentWidget().height()
        parent_w = self.parentWidget().width()
        x = max(4, min(parent_w - w - 4, btn_pos.x()))

        if btn_pos.y() + anchor_btn.height() + h + 6 <= parent_h:
            end_y = btn_pos.y() + anchor_btn.height() + 4
            start_rect = QRect(x, end_y, w, 14)
        else:
            end_y = max(4, btn_pos.y() - h - 4)
            start_rect = QRect(x, btn_pos.y() - 14, w, 14)

        end_rect = QRect(x, end_y, w, h)
        self.setGeometry(start_rect)
        self.setVisible(True)
        self.raise_()

        self._geo_anim.stop()
        self._geo_anim.setDuration(210)
        self._geo_anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._geo_anim.setStartValue(start_rect)
        self._geo_anim.setEndValue(end_rect)

        self._op_anim.stop()
        self._op_anim.setDuration(165)
        self._op_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._op_anim.setStartValue(0.0)
        self._op_anim.setEndValue(1.0)

        self._geo_anim.start()
        self._op_anim.start()

    def _pick(self, role: str, code: str) -> None:
        self.close_menu()
        self.language_selected.emit(role, code)

    def close_menu(self) -> None:
        if not self._is_open:
            return
        self._is_open = False
        self._role = ""
        cur = self.geometry()
        end_rect = QRect(cur.x(), cur.y(), cur.width(), 14)

        self._geo_anim.stop()
        self._geo_anim.setDuration(145)
        self._geo_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._geo_anim.setStartValue(cur)
        self._geo_anim.setEndValue(end_rect)

        self._op_anim.stop()
        self._op_anim.setDuration(135)
        self._op_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._op_anim.setStartValue(self._fx.opacity())
        self._op_anim.setEndValue(0.0)

        self._geo_anim.start()
        self._op_anim.start()
        self.closed.emit()

    def _on_anim_done(self) -> None:
        if not self._is_open:
            self.setVisible(False)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        bg = QColor(Theme.bg)
        bg.setAlpha(248)
        p.setBrush(bg)
        border = QColor(Theme.accent)
        border.setAlpha(155)
        p.setPen(QPen(border, 1.2))
        p.drawRoundedRect(r, 12.0, 12.0)
        p.end()


class SmartTextEdit(QPlainTextEdit):
    """Multiline plain-text editor that also provides QLineEdit-compatible .text() / .setText()."""

    def __init__(self, placeholder: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setPlaceholderText(placeholder)
        self.setStyleSheet(
            "QPlainTextEdit { background: transparent; border: none; padding: 2px; font-size: 12px; }"
        )

    def text(self) -> str:
        return self.toPlainText()

    def setText(self, val: str) -> None:
        self.setPlainText(val)


def _round_pixmap(pm: QPixmap, size: int = 44, radius: int = 10) -> QPixmap:
    scaled = pm.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, scaled)
    painter.end()
    return out


class ExpandedPanel(QWidget):
    """520x360 open-space expanded droplet with 6 pages and fluid transitions."""

    settings_applied = Signal(object)  # AppConfig
    hide_requested = Signal()
    collapse_requested = Signal()
    play_pause_requested = Signal()
    next_track_requested = Signal()
    prev_track_requested = Signal()
    volume_set_requested = Signal(int)
    mute_toggle_requested = Signal()
    clipboard_item_clicked = Signal(str)
    clipboard_item_delete_requested = Signal(str)
    clipboard_clear_requested = Signal()
    ocr_snip_requested = Signal()
    ocr_session_finished = Signal()
    weather_refresh_requested = Signal()
    weather_city_changed = Signal(str)
    timer_finished = Signal()
    alarm_triggered = Signal(str, str)  # time_str, text

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cfg = config
        self._is_playing = False
        self._is_muted = False
        self._has_media = False
        self._last_weather: WeatherData | None = None
        self._weather_kind = "cloud_sun"
        self._has_album_art = False
        self._all_clip_items: list[str] = []
        self._todo_checkboxes: list[SmoothCheckBox] = []
        self._fired_alarms_today: set[str] = set()
        self._src_lang = "auto"
        self._tgt_lang = "en"
        self._last_detected_src = ""
        self._tr_direction = "auto"

        # Focus timer & Stopwatch state
        self._timer_total_sec = 25 * 60
        self._timer_rem_sec = 25 * 60
        self._timer_running = False
        self._stopwatch_tenths = 0
        self._stopwatch_running = False

        self._focus_qtimer = QTimer(self)
        self._focus_qtimer.setInterval(1000)
        self._focus_qtimer.timeout.connect(self._tick_focus_timer)

        self._stopwatch_qtimer = QTimer(self)
        self._stopwatch_qtimer.setInterval(100)
        self._stopwatch_qtimer.timeout.connect(self._tick_stopwatch)

        self._tr_debounce = QTimer(self)
        self._tr_debounce.setSingleShot(True)
        self._tr_debounce.setInterval(420)
        self._tr_debounce.timeout.connect(lambda: self._run_translate(self._tr_direction))

        self._eyedropper = ScreenEyedropperOverlay()
        self._eyedropper.color_picked.connect(self._on_eyedropper_picked)

        self._ocr_overlay = ScreenOcrOverlay()
        self._ocr_overlay.region_captured.connect(self._on_ocr_region_captured)
        self._ocr_overlay.cancelled.connect(self._on_ocr_cancelled)

        self._ocr_service = OcrService(self)
        self._ocr_service.ocr_ready.connect(self._on_ocr_ready)
        self._ocr_service.ocr_error.connect(self._on_ocr_error)

        self._translator = TranslatorService(self)
        self._translator.translation_ready.connect(self._on_translation_ready)
        self._translator.translation_error.connect(self._on_translation_error)

        set_language(config.appearance.language)
        self._build_ui()
        self.apply_appearance(config.appearance)
        self.apply_modules(config.modules)
        self._rebuild_todo_ui()
        self._rebuild_alarms_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 12, 18, 12)
        root.setSpacing(6)

        # ── Top Navigation Bar: [▬ • • • • •] [⟩ Cycle] [Головна] ... [PNG] [18:30] [👁] [›] ──
        header = QHBoxLayout()
        header.setSpacing(7)

        self.dot_bar = DotIndicatorBar(count=PAGE_COUNT)
        self.dot_bar.page_selected.connect(self.switch_page)
        header.addWidget(self.dot_bar)

        self.cycle_tab_btn = PillButton("", icon_kind="cycle_tab", variant="IconBtn", icon_size=15)
        self.cycle_tab_btn.setFixedSize(24, 24)
        self.cycle_tab_btn.setToolTip(tr("tip_cycle_tab"))
        self.cycle_tab_btn.clicked.connect(self.cycle_next_page)
        header.addWidget(self.cycle_tab_btn)

        self.page_title_lbl = QLabel(_page_title(0))
        self.page_title_lbl.setStyleSheet("font-size: 13px; font-weight: 700;")
        header.addWidget(self.page_title_lbl)

        header.addStretch()

        self.mascot_badge = CharacterBadgeWidget()
        header.addWidget(self.mascot_badge)

        self.by_nord_lbl = QLabel("by nord")
        self.by_nord_lbl.setObjectName("MutedLabel")
        self.by_nord_lbl.setStyleSheet("font-size: 10px; font-weight: 600;")
        header.addWidget(self.by_nord_lbl)

        self.time_lbl = QLabel("00:00")
        self.time_lbl.setStyleSheet("font-size: 13px; font-weight: 700;")
        header.addWidget(self.time_lbl)

        self.hide_btn = PillButton("", icon_kind="hide", variant="IconBtn", icon_size=15)
        self.hide_btn.setToolTip(tr("tip_hide"))
        self.hide_btn.setFixedSize(24, 24)
        self.hide_btn.clicked.connect(self.hide_requested.emit)

        self.collapse_btn = PillButton("", icon_kind="collapse", variant="IconBtn", icon_size=15)
        self.collapse_btn.setToolTip(tr("tip_collapse"))
        self.collapse_btn.setFixedSize(24, 24)
        self.collapse_btn.clicked.connect(self.collapse_requested.emit)

        header.addWidget(self.hide_btn)
        header.addWidget(self.collapse_btn)
        root.addLayout(header)
        root.addWidget(ThinDivider())

        # ── Pages Stack (6 Pages) with smooth crossfade + slide ────────
        self.inner_stack = QStackedWidget()
        self._page_opacity = QGraphicsOpacityEffect(self.inner_stack)
        self._page_opacity.setOpacity(1.0)
        self.inner_stack.setGraphicsEffect(self._page_opacity)

        self._fade_anim = QPropertyAnimation(self._page_opacity, b"opacity", self)
        self._fade_anim.setDuration(190)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._slide_anim = QPropertyAnimation(self.inner_stack, b"pos", self)
        self._slide_anim.setDuration(220)
        self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.overview_page = self._build_overview_page()
        self.weather_page = self._build_weather_page()
        self.focus_page = self._build_focus_page()
        self.text_tools_page = self._build_text_tools_page()
        self.clipboard_page = self._build_clipboard_page()
        self.settings_page = InlineSettingsPanel(self._cfg)
        self.settings_page.settings_applied.connect(self._on_inline_settings_saved)

        self.inner_stack.addWidget(self.overview_page)
        self.inner_stack.addWidget(self.weather_page)
        self.inner_stack.addWidget(self.focus_page)
        self.inner_stack.addWidget(self.text_tools_page)
        self.inner_stack.addWidget(self.clipboard_page)
        self.inner_stack.addWidget(self.settings_page)
        root.addWidget(self.inner_stack, 1)

    # ── Page 0: Головна (Zero empty bottom space: Music + Eyedropper + Volume + Week/Day + Live System Stats & Quick Actions) ──

    def _build_overview_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 2, 2, 0)
        lay.setSpacing(6)

        # Row 1: Music Player + Screen Eyedropper inside subtle glass tiles
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.music_section = GlassTile(radius=12.0)
        m_lay = QHBoxLayout(self.music_section)
        m_lay.setContentsMargins(8, 6, 8, 6)
        m_lay.setSpacing(10)

        self.album_lbl = QLabel()
        self.album_lbl.setFixedSize(42, 42)
        self.album_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.album_lbl.setStyleSheet(
            "background: rgba(255,255,255,0.06); border-radius: 10px;"
        )
        m_lay.addWidget(self.album_lbl)

        info_and_ctrl_col = QVBoxLayout()
        info_and_ctrl_col.setSpacing(1)

        title_and_btns_row = QHBoxLayout()
        title_and_btns_row.setSpacing(4)

        self.track_title_lbl = QLabel(tr("no_media"))
        self.track_title_lbl.setStyleSheet("font-size: 12px; font-weight: 700;")
        title_and_btns_row.addWidget(self.track_title_lbl)

        self.waveform = WaveformWidget()
        title_and_btns_row.addWidget(self.waveform)

        self.prev_btn = PillButton("", icon_kind="prev", variant="IconBtn", icon_size=12)
        self.prev_btn.setFixedSize(22, 22)
        self.prev_btn.clicked.connect(self.prev_track_requested.emit)

        self.play_btn = PillButton("", icon_kind="play", variant="IconBtn", icon_size=13)
        self.play_btn.setFixedSize(24, 24)
        self.play_btn.clicked.connect(self.play_pause_requested.emit)

        self.next_btn = PillButton("", icon_kind="next", variant="IconBtn", icon_size=12)
        self.next_btn.setFixedSize(22, 22)
        self.next_btn.clicked.connect(self.next_track_requested.emit)

        title_and_btns_row.addWidget(self.prev_btn)
        title_and_btns_row.addWidget(self.play_btn)
        title_and_btns_row.addWidget(self.next_btn)
        title_and_btns_row.addStretch()

        self.track_artist_lbl = QLabel(tr("turn_on_track"))
        self.track_artist_lbl.setObjectName("MutedLabel")

        info_and_ctrl_col.addLayout(title_and_btns_row)
        info_and_ctrl_col.addWidget(self.track_artist_lbl)
        m_lay.addLayout(info_and_ctrl_col, 1)

        top_row.addWidget(self.music_section, 1)

        # Eyedropper tile on the right
        self.picker_tile = GlassTile(radius=12.0)
        picker_box = QVBoxLayout(self.picker_tile)
        picker_box.setContentsMargins(8, 5, 8, 5)
        picker_box.setSpacing(3)

        p_top = QHBoxLayout()
        p_top.setSpacing(6)
        self.pipette_btn = PillButton(tr("pipette"), icon_kind="pipette", icon_size=13)
        self.pipette_btn.setFixedHeight(24)
        self.pipette_btn.setToolTip(tr("pipette_tip"))
        self.pipette_btn.clicked.connect(self._eyedropper.start_picking)

        self.picked_swatch = QLabel()
        self.picked_swatch.setFixedSize(20, 20)
        self.picked_swatch.setStyleSheet(
            "background-color: #E2A86B; border-radius: 6px; border: 1px solid rgba(255,255,255,0.35);"
        )
        p_top.addWidget(self.pipette_btn)
        p_top.addWidget(self.picked_swatch)
        picker_box.addLayout(p_top)

        self.picked_info_btn = PillButton("#E2A86B · 226,168,107", icon_kind="copy", variant="IconBtn", icon_size=11)
        self.picked_info_btn.setFixedHeight(18)
        self.picked_info_btn.setToolTip(tr("copy_color_tip"))
        self.picked_info_btn.clicked.connect(self._copy_picked_color)
        picker_box.addWidget(self.picked_info_btn)

        top_row.addWidget(self.picker_tile)
        lay.addLayout(top_row)

        # Row 2: System Volume Mixer
        self.vol_divider = QWidget()
        self.vol_divider.setFixedHeight(0)
        self.volume_section = QWidget()
        v_lay = QHBoxLayout(self.volume_section)
        v_lay.setContentsMargins(4, 0, 4, 0)
        v_lay.setSpacing(8)

        self.mute_btn = PillButton("", icon_kind="speaker", variant="IconBtn", icon_size=15)
        self.mute_btn.setFixedSize(22, 22)
        self.mute_btn.clicked.connect(self.mute_toggle_requested.emit)
        v_lay.addWidget(self.mute_btn)

        self.vol_title_lbl = QLabel(tr("sys_volume"))
        self.vol_title_lbl.setObjectName("MutedLabel")
        v_lay.addWidget(self.vol_title_lbl)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.volume_slider.valueChanged.connect(self._on_volume_slider_moved)
        v_lay.addWidget(self.volume_slider, 1)

        self.volume_pct_lbl = QLabel("50%")
        self.volume_pct_lbl.setFixedWidth(36)
        self.volume_pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.volume_pct_lbl.setStyleSheet("font-size: 11px; font-weight: 600;")
        v_lay.addWidget(self.volume_pct_lbl)
        lay.addWidget(self.volume_section)

        self.day_divider = ThinDivider()
        lay.addWidget(self.day_divider)

        # Row 3: Week Strip Calendar + Live Day Progress Bar
        self.week_day_widget = WeekDayProgressWidget()
        lay.addWidget(self.week_day_widget)

        # Row 4: Configurable 3-slot Overview Tiles + Bottom Row (Теки with slide-out menu + Калькулятор)
        self.sys_stats_widget = SystemStatsWidget()
        lay.addWidget(self.sys_stats_widget)

        qa_row = QHBoxLayout()
        qa_row.setSpacing(8)

        self.folders_toggle_btn = PillButton(tr("folders"), icon_kind="folder", icon_size=13)
        self.folders_toggle_btn.setFixedHeight(28)
        self.folders_toggle_btn.setToolTip(tr("folders_tip"))
        self.folders_toggle_btn.clicked.connect(self._toggle_folders_popup)

        self.calc_btn = PillButton(tr("calc"), icon_kind="calc", icon_size=13)
        self.calc_btn.setFixedHeight(28)
        self.calc_btn.clicked.connect(self._qa_calc)

        qa_row.addWidget(self.folders_toggle_btn, 1)
        qa_row.addWidget(self.calc_btn, 1)
        lay.addLayout(qa_row)

        self.folders_popup = QuickFoldersPopup(page)
        self.folders_popup.folder_clicked.connect(self._open_quick_folder)
        self.folders_popup.configure_requested.connect(self._jump_to_folder_settings)
        self.folders_popup.closed.connect(lambda: self.folders_toggle_btn.set_active(False))

        return page

    # ── Quick Folders & Calculator handlers ────────────────────────────

    def _toggle_folders_popup(self) -> None:
        folders = self._cfg.downloads.quick_folders[:5]
        self.folders_popup.toggle_above(self.folders_toggle_btn, folders)
        self.folders_toggle_btn.set_active(self.folders_popup.is_open())

    def _open_quick_folder(self, path: str) -> None:
        expanded = os.path.expanduser(path)
        if os.path.exists(expanded):
            os.startfile(expanded)

    def _jump_to_folder_settings(self) -> None:
        self.switch_page(5)
        self.settings_page.sec_folders.set_expanded(True)

    def _qa_calc(self) -> None:
        subprocess.Popen(["calc.exe"])

    # ── Page 1: Погода ─────────────────────────────────────────────────

    def _build_weather_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(8)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        self.city_lbl = QLabel(tr("city"))
        self.city_lbl.setObjectName("MutedLabel")
        self.weather_city_input = QLineEdit(self._cfg.weather.city)
        self.weather_city_input.setFixedWidth(150)
        self.weather_city_input.returnPressed.connect(self._on_weather_city_submit)

        self.weather_refresh_btn = PillButton("", icon_kind="refresh", variant="IconBtn", icon_size=14)
        self.weather_refresh_btn.setFixedSize(24, 24)
        self.weather_refresh_btn.clicked.connect(self._on_weather_city_submit)

        self.weather_updated_lbl = QLabel(tr("waiting_update"))
        self.weather_updated_lbl.setObjectName("MutedLabel")

        top_bar.addWidget(self.city_lbl)
        top_bar.addWidget(self.weather_city_input)
        top_bar.addWidget(self.weather_refresh_btn)
        top_bar.addWidget(self.weather_updated_lbl)
        top_bar.addStretch()
        lay.addLayout(top_bar)
        lay.addWidget(ThinDivider())

        row1 = QHBoxLayout()
        row1.setSpacing(10)

        b1 = QVBoxLayout()
        b1.setContentsMargins(4, 2, 4, 2)
        b1.setSpacing(2)
        self.w_city_title = QLabel(self._cfg.weather.city.upper())
        self.w_city_title.setObjectName("SectionLabel")
        b1.addWidget(self.w_city_title)

        temp_row = QHBoxLayout()
        temp_row.setSpacing(6)
        self.weather_icon_lbl = QLabel()
        self.weather_icon_lbl.setFixedSize(24, 24)
        self.w_temp_big = QLabel("--°")
        self.w_temp_big.setObjectName("BigMetric")
        temp_row.addWidget(self.weather_icon_lbl)
        temp_row.addWidget(self.w_temp_big)
        temp_row.addStretch()
        b1.addLayout(temp_row)

        self.w_desc_lbl = QLabel(tr("loading"))
        self.w_desc_lbl.setStyleSheet("font-size: 12px; font-weight: 600;")
        self.w_feels_lbl = QLabel(f"{tr('feels_like')} --° · ↑--° ↓--°")
        self.w_feels_lbl.setObjectName("MutedLabel")
        b1.addWidget(self.w_desc_lbl)
        b1.addWidget(self.w_feels_lbl)
        b1.addStretch()

        self.wind_widget = WindCompassWidget()
        self.humidity_widget = HumidityBarWidget()

        row1.addLayout(b1, 1)
        row1.addWidget(ThinDivider(vertical=True))
        row1.addWidget(self.wind_widget, 1)
        row1.addWidget(ThinDivider(vertical=True))
        row1.addWidget(self.humidity_widget, 1)
        lay.addLayout(row1, 1)

        lay.addWidget(ThinDivider())

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.pressure_widget = PressureArcWidget()

        b5 = QVBoxLayout()
        b5.setContentsMargins(4, 2, 4, 2)
        b5.setSpacing(3)
        self.rain_title_lbl = QLabel(tr("rain_title"))
        self.rain_title_lbl.setObjectName("SectionLabel")
        self.w_rain_big = QLabel(f"0.0 {tr('mm')}")
        self.w_rain_big.setStyleSheet("font-size: 20px; font-weight: 600;")
        self.w_rain_sub = QLabel(tr("rain_none"))
        self.w_rain_sub.setObjectName("MutedLabel")
        b5.addWidget(self.rain_title_lbl)
        b5.addWidget(self.w_rain_big)
        b5.addWidget(self.w_rain_sub)
        b5.addStretch()

        b6 = QVBoxLayout()
        b6.setContentsMargins(4, 2, 4, 2)
        b6.setSpacing(3)
        self.vis_title_lbl = QLabel(tr("vis_title"))
        self.vis_title_lbl.setObjectName("SectionLabel")
        self.w_vis_big = QLabel(f"10.0 {tr('km')}")
        self.w_vis_big.setStyleSheet("font-size: 20px; font-weight: 600;")
        self.w_vis_sub = QLabel(f"{tr('clouds')}: 0%")
        self.w_vis_sub.setObjectName("MutedLabel")
        b6.addWidget(self.vis_title_lbl)
        b6.addWidget(self.w_vis_big)
        b6.addWidget(self.w_vis_sub)
        b6.addStretch()

        row2.addWidget(self.pressure_widget, 1)
        row2.addWidget(ThinDivider(vertical=True))
        row2.addLayout(b5, 1)
        row2.addWidget(ThinDivider(vertical=True))
        row2.addLayout(b6, 1)
        lay.addLayout(row2, 1)

        return page

    # ── Page 2: Фокус і Час (Timer + Stopwatch + Alarm Reminder + To-Do) ──

    def _build_focus_page(self) -> QWidget:
        page = QWidget()
        lay = QHBoxLayout(page)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(12)

        left_col = QVBoxLayout()
        left_col.setSpacing(6)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(4)
        self._time_mode_btns: list[PillButton] = []
        for idx, key in enumerate(("tab_timer", "tab_stopwatch", "tab_alarm")):
            mb = PillButton(tr(key))
            mb.setFixedHeight(26)
            mb.clicked.connect(lambda _=False, i=idx: self._switch_time_submode(i))
            self._time_mode_btns.append(mb)
            mode_row.addWidget(mb)
        left_col.addLayout(mode_row)

        self.time_sub_stack = QStackedWidget()

        # Subpage A: Timer
        t_page = QWidget()
        tl = QVBoxLayout(t_page)
        tl.setContentsMargins(0, 2, 0, 0)
        tl.setSpacing(6)
        ring_row = QHBoxLayout()
        ring_row.addStretch()
        self.timer_ring = TimerRingWidget()
        ring_row.addWidget(self.timer_ring)
        ring_row.addStretch()
        tl.addLayout(ring_row)

        presets_row = QHBoxLayout()
        presets_row.setSpacing(4)
        self._timer_preset_btns: list[tuple[int, PillButton]] = []
        for mins in (5, 15, 25, 45):
            b = PillButton(f"{mins}{tr('min_short')}")
            b.setFixedHeight(24)
            b.clicked.connect(lambda _=False, m=mins: self._set_focus_minutes(m))
            self._timer_preset_btns.append((mins, b))
            presets_row.addWidget(b)
        tl.addLayout(presets_row)

        ctrl_row = QHBoxLayout()
        self.timer_start_btn = PillButton(tr("start"), variant="AccentBtn")
        self.timer_start_btn.setFixedHeight(28)
        self.timer_start_btn.clicked.connect(self._toggle_focus_timer)
        self.timer_reset_btn = PillButton(tr("reset"))
        self.timer_reset_btn.setFixedHeight(28)
        self.timer_reset_btn.clicked.connect(self._reset_focus_timer)
        ctrl_row.addWidget(self.timer_start_btn, 1)
        ctrl_row.addWidget(self.timer_reset_btn)
        tl.addLayout(ctrl_row)
        tl.addStretch()

        # Subpage B: Stopwatch
        sw_page = QWidget()
        swl = QVBoxLayout(sw_page)
        swl.setContentsMargins(0, 12, 0, 0)
        swl.setSpacing(10)
        self.stopwatch_lbl = QLabel("00:00.0")
        self.stopwatch_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stopwatch_lbl.setStyleSheet("font-size: 28px; font-weight: 700;")
        swl.addWidget(self.stopwatch_lbl)

        sw_ctrl = QHBoxLayout()
        self.sw_start_btn = PillButton(tr("start"), variant="AccentBtn")
        self.sw_start_btn.setFixedHeight(28)
        self.sw_start_btn.clicked.connect(self._toggle_stopwatch)
        self.sw_reset_btn = PillButton(tr("reset"))
        self.sw_reset_btn.setFixedHeight(28)
        self.sw_reset_btn.clicked.connect(self._reset_stopwatch)
        sw_ctrl.addWidget(self.sw_start_btn, 1)
        sw_ctrl.addWidget(self.sw_reset_btn)
        swl.addLayout(sw_ctrl)
        swl.addStretch()

        # Subpage C: Alarm Reminder
        al_page = QWidget()
        allay = QVBoxLayout(al_page)
        allay.setContentsMargins(0, 4, 0, 0)
        allay.setSpacing(5)
        al_in_row = QHBoxLayout()
        al_in_row.setSpacing(4)
        self.alarm_time_edit = QLineEdit()
        self.alarm_time_edit.setPlaceholderText("19:30")
        self.alarm_time_edit.setFixedWidth(54)
        self.alarm_note_edit = QLineEdit()
        self.alarm_note_edit.setPlaceholderText(tr("alarm_note_ph"))
        self.alarm_note_edit.returnPressed.connect(self._add_alarm)
        al_add_btn = PillButton("+", variant="AccentBtn")
        al_add_btn.setFixedSize(26, 26)
        al_add_btn.clicked.connect(self._add_alarm)
        al_in_row.addWidget(self.alarm_time_edit)
        al_in_row.addWidget(self.alarm_note_edit, 1)
        al_in_row.addWidget(al_add_btn)
        allay.addLayout(al_in_row)

        self.alarms_list = QListWidget()
        self.alarms_list.setFixedHeight(110)
        self.alarms_list.itemClicked.connect(self._remove_alarm_item)
        allay.addWidget(self.alarms_list)
        allay.addStretch()

        self.time_sub_stack.addWidget(t_page)
        self.time_sub_stack.addWidget(sw_page)
        self.time_sub_stack.addWidget(al_page)
        left_col.addWidget(self.time_sub_stack, 1)
        self._switch_time_submode(0)

        lay.addLayout(left_col, 1)
        lay.addWidget(ThinDivider(vertical=True))

        # Right column: To-Do List
        right_col = QVBoxLayout()
        right_col.setSpacing(5)
        self.todo_title_lbl = QLabel(tr("todo_title"))
        self.todo_title_lbl.setObjectName("SectionLabel")
        right_col.addWidget(self.todo_title_lbl)

        self.todo_container = QWidget()
        self.todo_layout = QVBoxLayout(self.todo_container)
        self.todo_layout.setContentsMargins(0, 0, 0, 0)
        self.todo_layout.setSpacing(4)
        right_col.addWidget(self.todo_container, 1)

        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        self.todo_input = QLineEdit()
        self.todo_input.setPlaceholderText(tr("todo_ph"))
        self.todo_input.returnPressed.connect(self._add_todo_item)
        self.todo_add_btn = PillButton(tr("add"), variant="AccentBtn")
        self.todo_add_btn.setFixedHeight(26)
        self.todo_add_btn.clicked.connect(self._add_todo_item)
        add_row.addWidget(self.todo_input, 1)
        add_row.addWidget(self.todo_add_btn)
        right_col.addLayout(add_row)

        lay.addLayout(right_col, 1)
        return page

    # ── Page 3: Текст і Переклад (Redesigned two-card studio + smart translator + layout fixer) ──

    def _build_text_tools_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(6)

        # 1. Top Input Glass Tile
        self.input_tile = GlassTile(radius=12.0)
        in_lay = QVBoxLayout(self.input_tile)
        in_lay.setContentsMargins(10, 6, 10, 6)
        in_lay.setSpacing(4)

        in_head = QHBoxLayout()
        in_head.setSpacing(6)
        self.in_title_lbl = QLabel(tr("input_text"))
        self.in_title_lbl.setObjectName("SectionLabel")
        self.layout_hint_btn = PillButton(
            tr("fix_layout"),
            icon_kind="keyboard",
            variant="GhostBtn",
            icon_size=12,
        )
        self.layout_hint_btn.setFixedHeight(20)
        self.layout_hint_btn.setVisible(False)
        self.layout_hint_btn.clicked.connect(self._on_fix_layout_clicked)

        self.ocr_snip_btn = PillButton(
            tr("ocr_snip"), icon_kind="scan_text", variant="IconBtn", icon_size=12
        )
        self.ocr_snip_btn.setFixedHeight(20)
        self.ocr_snip_btn.setToolTip(tr("ocr_snip_tip"))
        self.ocr_snip_btn.clicked.connect(self.ocr_snip_requested.emit)

        self.paste_btn = PillButton(tr("from_clip"), icon_kind="paste", variant="IconBtn", icon_size=12)
        self.paste_btn.setFixedHeight(20)
        self.paste_btn.clicked.connect(self._paste_into_text_tool)

        self.clip_fix_btn = PillButton(tr("clip_layout"), icon_kind="keyboard", variant="IconBtn", icon_size=12)
        self.clip_fix_btn.setFixedHeight(20)
        self.clip_fix_btn.setToolTip(tr("clip_layout_tip"))
        self.clip_fix_btn.clicked.connect(self._on_fix_clipboard_layout)

        self.clear_in_btn = PillButton("", icon_kind="close", variant="IconBtn", icon_size=12)
        self.clear_in_btn.setFixedSize(20, 20)
        self.clear_in_btn.setToolTip(tr("clear_tip"))
        self.clear_in_btn.clicked.connect(self._clear_text_tool)

        in_head.addWidget(self.in_title_lbl)
        in_head.addWidget(self.layout_hint_btn)
        in_head.addStretch()
        in_head.addWidget(self.ocr_snip_btn)
        in_head.addWidget(self.paste_btn)
        in_head.addWidget(self.clip_fix_btn)
        in_head.addWidget(self.clear_in_btn)
        in_lay.addLayout(in_head)

        self.text_tool_input = SmartTextEdit(tr("input_ph"))
        self.text_tool_input.setFixedHeight(68)
        self.text_tool_input.textChanged.connect(self._on_text_input_changed)
        in_lay.addWidget(self.text_tool_input)
        lay.addWidget(self.input_tile)

        # 2. Middle Action Bar: Expanding Language Dropdowns + Swap + Layout Fixer + Translate
        mid_row = QHBoxLayout()
        mid_row.setSpacing(5)

        self.src_lang_btn = PillButton(lang_display_name(self._src_lang), icon_kind="chevron_down", icon_size=11)
        self.src_lang_btn.setFixedHeight(26)
        self.src_lang_btn.setToolTip(tr("tr_src_tip"))
        self.src_lang_btn.clicked.connect(lambda: self._open_lang_popup("src"))

        self._lang_arrow_lbl = QLabel("→")
        self._lang_arrow_lbl.setObjectName("MutedLabel")

        self.tgt_lang_btn = PillButton(lang_display_name(self._tgt_lang), icon_kind="chevron_down", icon_size=11)
        self.tgt_lang_btn.setFixedHeight(26)
        self.tgt_lang_btn.setToolTip(tr("tr_tgt_tip"))
        self.tgt_lang_btn.clicked.connect(lambda: self._open_lang_popup("tgt"))

        mid_row.addWidget(self.src_lang_btn)
        mid_row.addWidget(self._lang_arrow_lbl)
        mid_row.addWidget(self.tgt_lang_btn)

        self.swap_btn = PillButton("", icon_kind="swap", icon_size=13)
        self.swap_btn.setFixedSize(28, 26)
        self.swap_btn.setToolTip(tr("swap_tip"))
        self.swap_btn.clicked.connect(self._swap_text_tool_io)
        mid_row.addWidget(self.swap_btn)

        mid_row.addStretch()

        self.fix_btn = PillButton(tr("fix_layout"), icon_kind="keyboard", icon_size=13)
        self.fix_btn.setFixedHeight(26)
        self.fix_btn.setToolTip(tr("fix_layout_tip"))
        self.fix_btn.clicked.connect(self._on_fix_layout_clicked)

        self.tr_btn = PillButton(tr("translate"), icon_kind="translate", variant="AccentBtn", icon_size=13)
        self.tr_btn.setFixedHeight(26)
        self.tr_btn.clicked.connect(lambda: self._run_translate())

        mid_row.addWidget(self.fix_btn)
        mid_row.addWidget(self.tr_btn)
        lay.addLayout(mid_row)

        # 3. Bottom Output Glass Tile
        self.output_tile = GlassTile(radius=12.0)
        out_lay = QVBoxLayout(self.output_tile)
        out_lay.setContentsMargins(10, 6, 10, 6)
        out_lay.setSpacing(4)

        res_head = QHBoxLayout()
        res_head.setSpacing(6)
        self.res_title_lbl = QLabel(tr("result"))
        self.res_title_lbl.setObjectName("SectionLabel")
        self.loading_dots = LoadingDots()
        self.text_tool_status = QLabel("")
        self.text_tool_status.setObjectName("AccentLabel")
        self.copy_res_btn = PillButton(tr("copy"), icon_kind="copy", icon_size=12)
        self.copy_res_btn.setFixedHeight(22)
        self.copy_res_btn.clicked.connect(self._copy_text_tool_result)

        res_head.addWidget(self.res_title_lbl)
        res_head.addWidget(self.loading_dots)
        res_head.addWidget(self.text_tool_status)
        res_head.addStretch()
        res_head.addWidget(self.copy_res_btn)
        out_lay.addLayout(res_head)

        self.text_tool_output = SmartTextEdit(tr("output_ph"))
        self.text_tool_output.setReadOnly(True)
        self.text_tool_output.setFixedHeight(74)
        out_lay.addWidget(self.text_tool_output)
        lay.addWidget(self.output_tile, 1)

        self.lang_popup = LangSelectPopup(page)
        self.lang_popup.language_selected.connect(self._on_lang_selected)
        self.lang_popup.closed.connect(self._sync_lang_btn_states)

        return page

    # ── Page 4: Буфер обміну ───────────────────────────────────────────

    def _build_clipboard_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)

        c_head = QHBoxLayout()
        c_head.setSpacing(8)
        self.clip_search_input = QLineEdit()
        self.clip_search_input.setPlaceholderText(tr("clip_search_ph"))
        self.clip_search_input.textChanged.connect(self._filter_clipboard_view)

        self.clip_status_lbl = QLabel("")
        self.clip_status_lbl.setObjectName("AccentLabel")

        self.clip_clear_btn = PillButton(tr("clear"), icon_kind="trash", icon_size=12)
        self.clip_clear_btn.setFixedHeight(26)
        self.clip_clear_btn.clicked.connect(self.clipboard_clear_requested.emit)

        c_head.addWidget(self.clip_search_input, 1)
        c_head.addWidget(self.clip_status_lbl)
        c_head.addWidget(self.clip_clear_btn)
        lay.addLayout(c_head)

        self.clip_list = QListWidget()
        self.clip_list.itemClicked.connect(self._on_clip_clicked)
        lay.addWidget(self.clip_list, 1)
        return page

    # ── Navigation & Page Transitions ──────────────────────────────────

    def play_open_animations(self) -> None:
        """Trigger lively intro animations when the droplet expands."""
        self.week_day_widget.play_intro()
        self.sys_stats_widget.play_intro()

    def cycle_next_page(self) -> None:
        next_idx = (self.inner_stack.currentIndex() + 1) % PAGE_COUNT
        self.switch_page(next_idx)

    def switch_page(self, index: int) -> None:
        index = max(0, min(PAGE_COUNT - 1, index))
        prev_idx = self.inner_stack.currentIndex()
        if hasattr(self, "folders_popup") and self.folders_popup.is_open():
            self.folders_popup.close_menu()
        if hasattr(self, "lang_popup") and self.lang_popup.is_open():
            self.lang_popup.close_menu()
        if index == 5:
            self.settings_page.load_config(self._cfg)
        self.inner_stack.setCurrentIndex(index)
        self.dot_bar.set_current(index)
        self.page_title_lbl.setText(_page_title(index))

        if index == 0:
            self.week_day_widget.play_intro()
            self.sys_stats_widget.play_intro()

        self._fade_anim.stop()
        self._fade_anim.setStartValue(0.25)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

        direction = 1 if index >= prev_idx else -1
        base_pos = self.inner_stack.pos()
        self._slide_anim.stop()
        self._slide_anim.setStartValue(base_pos + QPoint(direction * 14, 0))
        self._slide_anim.setEndValue(base_pos)
        self._slide_anim.start()

    def show_dashboard(self) -> None:
        self.switch_page(0)

    def show_settings(self) -> None:
        self.switch_page(5)

    def _on_inline_settings_saved(self, new_cfg: AppConfig) -> None:
        new_cfg.focus.todo_items = list(self._cfg.focus.todo_items)
        new_cfg.focus.alarms = list(self._cfg.focus.alarms)
        self._cfg = new_cfg
        self.weather_city_input.setText(new_cfg.weather.city)
        self.apply_appearance(new_cfg.appearance)
        self.apply_modules(new_cfg.modules)
        self.settings_applied.emit(new_cfg)

    def apply_appearance(self, a: AppearanceConfig) -> None:
        fg = a.text_color
        ac = a.accent_color
        mu = a.muted_color

        set_language(a.language)
        Theme.set(ac, fg, mu, a.bg_color)
        self.dot_bar.set_accent(ac)
        self.mascot_badge.configure(a.mascot_path, a.mascot_size, ac)

        self.play_btn.set_icon_kind("pause" if self._is_playing else "play")
        self.mute_btn.set_icon_kind("speaker_mute" if self._is_muted else "speaker")

        self.weather_icon_lbl.setPixmap(
            render_vector_pixmap(self._weather_kind, 22, fg, ac)
        )
        if not self._has_album_art:
            self.album_lbl.setPixmap(render_vector_pixmap("music_note", 20, fg, ac))
        self.waveform.set_accent(ac)
        self.week_day_widget.set_colors(ac, fg, mu)
        self.sys_stats_widget.set_colors(ac, fg, mu)
        self.wind_widget.set_colors(ac, fg, mu)
        self.humidity_widget.set_colors(ac, fg, mu)
        self.pressure_widget.set_colors(ac, fg, mu)
        self.timer_ring.set_colors(ac, fg)
        self.settings_page.apply_appearance(a)
        for chk in self._todo_checkboxes:
            chk.set_colors(ac, fg, mu)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Refresh all localized strings across ExpandedPanel and its subwidgets."""
        self.page_title_lbl.setText(_page_title(self.inner_stack.currentIndex()))
        self.cycle_tab_btn.setToolTip(tr("tip_cycle_tab"))
        self.hide_btn.setToolTip(tr("tip_hide"))
        self.collapse_btn.setToolTip(tr("tip_collapse"))

        if not self._has_media:
            self.track_title_lbl.setText(tr("no_media"))
            self.track_artist_lbl.setText(tr("turn_on_track"))

        self.pipette_btn.setText(tr("pipette"))
        self.pipette_btn.setToolTip(tr("pipette_tip"))
        self.picked_info_btn.setToolTip(tr("copy_color_tip"))
        self.vol_title_lbl.setText(tr("sys_volume"))
        self.folders_toggle_btn.setText(tr("folders"))
        self.folders_toggle_btn.setToolTip(tr("folders_tip"))
        self.calc_btn.setText(tr("calc"))

        self.city_lbl.setText(tr("city"))
        self.rain_title_lbl.setText(tr("rain_title"))
        self.vis_title_lbl.setText(tr("vis_title"))
        if self._last_weather is not None:
            self.update_weather(self._last_weather)
        else:
            self.weather_updated_lbl.setText(tr("waiting_update"))
            self.w_desc_lbl.setText(tr("loading"))
            self.w_feels_lbl.setText(f"{tr('feels_like')} --° · ↑--° ↓--°")
            self.w_rain_big.setText(f"0.0 {tr('mm')}")
            self.w_rain_sub.setText(tr("rain_none"))
            self.w_vis_big.setText(f"10.0 {tr('km')}")
            self.w_vis_sub.setText(f"{tr('clouds')}: 0%")
            self.wind_widget.set_data(0.0, 0.0, tr("dir_N"), tr("wind_ms"))
            self.humidity_widget.set_data(55, tr("hum_comfort"))
            self.sys_stats_widget.set_weather_summary("--°", tr("waiting_data"), 15.0)
            self.weather_refresh_requested.emit()

        for key, b in zip(("tab_timer", "tab_stopwatch", "tab_alarm"), self._time_mode_btns):
            b.setText(tr(key))
        for mins, b in self._timer_preset_btns:
            b.setText(f"{mins}{tr('min_short')}")
        self.timer_start_btn.setText(tr("pause") if self._timer_running else tr("start"))
        self.timer_reset_btn.setText(tr("reset"))
        self.sw_start_btn.setText(tr("pause") if self._stopwatch_running else tr("start"))
        self.sw_reset_btn.setText(tr("reset"))
        self.alarm_note_edit.setPlaceholderText(tr("alarm_note_ph"))
        self.todo_title_lbl.setText(tr("todo_title"))
        self.todo_input.setPlaceholderText(tr("todo_ph"))
        self.todo_add_btn.setText(tr("add"))
        self._rebuild_alarms_ui()

        self.in_title_lbl.setText(tr("input_text"))
        self.ocr_snip_btn.setText(tr("ocr_snip"))
        self.ocr_snip_btn.setToolTip(tr("ocr_snip_tip"))
        self.paste_btn.setText(tr("from_clip"))
        self.clip_fix_btn.setText(tr("clip_layout"))
        self.clip_fix_btn.setToolTip(tr("clip_layout_tip"))
        self.clear_in_btn.setToolTip(tr("clear_tip"))
        self.text_tool_input.setPlaceholderText(tr("input_ph"))
        self.text_tool_output.setPlaceholderText(tr("output_ph"))
        self.src_lang_btn.setText(lang_display_name(self._src_lang))
        self.src_lang_btn.setToolTip(tr("tr_src_tip"))
        self.tgt_lang_btn.setText(lang_display_name(self._tgt_lang))
        self.tgt_lang_btn.setToolTip(tr("tr_tgt_tip"))
        self.swap_btn.setToolTip(tr("swap_tip"))
        self.fix_btn.setText(tr("fix_layout"))
        self.fix_btn.setToolTip(tr("fix_layout_tip"))
        self.tr_btn.setText(tr("translate"))
        self.res_title_lbl.setText(tr("result"))
        self.copy_res_btn.setText(tr("copy"))

        self.clip_search_input.setPlaceholderText(tr("clip_search_ph"))
        self.clip_clear_btn.setText(tr("clear"))
        self._filter_clipboard_view(self.clip_search_input.text())

        self.week_day_widget.update()
        self.sys_stats_widget.update()
        self.wind_widget.update()
        self.humidity_widget.update()
        self.pressure_widget.update()
        self._sync_tasks_summary_to_tiles()
        self.settings_page.retranslate_ui()

    def apply_modules(self, modules: ModulesConfig) -> None:
        self.time_lbl.setVisible(modules.show_clock)
        self.music_section.setVisible(modules.show_music)
        self.volume_section.setVisible(modules.show_volume)
        self.week_day_widget.setVisible(modules.show_day_progress)
        self.day_divider.setVisible(modules.show_day_progress)
        slots = [modules.overview_tile_1, modules.overview_tile_2, modules.overview_tile_3]
        self.sys_stats_widget.set_slot_kinds(slots)
        has_any_slot = any(s != "none" for s in slots)
        self.sys_stats_widget.setVisible(modules.show_overview_tiles and has_any_slot)
        self._sync_tasks_summary_to_tiles()

    def _sync_tasks_summary_to_tiles(self) -> None:
        items = self._cfg.focus.todo_items
        total = len(items)
        done = sum(1 for e in items if e.get("done", False))
        if self._timer_running:
            right_str = self.active_timer_str
            sub_str = f"{tr('timer_word')} · {done}/{total}"
            pct = (self._timer_rem_sec / max(1, self._timer_total_sec)) * 100.0
        else:
            right_str = f"{done}/{total}"
            sub_str = tr("tasks_done") if total else tr("tasks_empty")
            pct = (done / total * 100.0) if total else 0.0
        self.sys_stats_widget.set_tasks_summary(right_str, sub_str, pct)

    def update_clock(self) -> None:
        now = datetime.now()
        cur_hm = now.strftime("%H:%M")
        self.time_lbl.setText(cur_hm)
        self.week_day_widget.update()
        self._check_alarms(cur_hm)

    # ── Eyedropper & Text Tools ────────────────────────────────────────

    def _on_eyedropper_picked(self, hex_str: str, r: int, g: int, b: int) -> None:
        self.picked_swatch.setStyleSheet(
            f"background-color: {hex_str}; border-radius: 6px; border: 1px solid rgba(255,255,255,0.4);"
        )
        self.picked_info_btn.setText(f"{hex_str} · {r},{g},{b}")
        self.picker_tile.flash()
        self.clipboard_item_clicked.emit(hex_str)

    def _copy_picked_color(self) -> None:
        txt = self.picked_info_btn.text().split("·")[0].strip()
        if txt:
            self.picker_tile.flash()
            self.clipboard_item_clicked.emit(txt)

    def _on_text_input_changed(self) -> None:
        raw = self.text_tool_input.text().strip()
        if not raw:
            self.layout_hint_btn.setVisible(False)
            self._tr_debounce.stop()
            return
        hint = looks_like_wrong_layout(raw)
        if hint:
            preview = hint if len(hint) <= 18 else hint[:17] + "…"
            self.layout_hint_btn.setText(f"{tr('fix_hint_prefix')} «{preview}»")
            self.layout_hint_btn.setVisible(True)
        else:
            self.layout_hint_btn.setVisible(False)
            self._tr_debounce.start()

    def _open_lang_popup(self, role: str) -> None:
        if role == "src":
            self.lang_popup.open_for(self.src_lang_btn, TRANSLATOR_SOURCE_LANGS, self._src_lang, "src")
        else:
            self.lang_popup.open_for(self.tgt_lang_btn, TRANSLATOR_TARGET_LANGS, self._tgt_lang, "tgt")
        self._sync_lang_btn_states()

    def _sync_lang_btn_states(self) -> None:
        open_role = self.lang_popup.current_role() if self.lang_popup.is_open() else ""
        self.src_lang_btn.set_active(open_role == "src")
        self.tgt_lang_btn.set_active(open_role == "tgt")

    def _on_lang_selected(self, role: str, code: str) -> None:
        if role == "src":
            self._src_lang = code
            self.src_lang_btn.setText(lang_display_name(code))
        else:
            self._tgt_lang = code
            self.tgt_lang_btn.setText(lang_display_name(code))
        self._tr_direction = f"{self._src_lang}_{self._tgt_lang}"
        if self.text_tool_input.text().strip():
            self._run_translate()

    def begin_ocr_overlay(self) -> None:
        self._ocr_overlay.start_capture()

    def _on_ocr_cancelled(self) -> None:
        self.ocr_session_finished.emit()

    def _on_ocr_region_captured(self, image, action: str) -> None:
        self.ocr_session_finished.emit()
        self._tr_debounce.stop()
        self.loading_dots.start()
        self.text_tool_status.setText(tr("status_recognizing"))
        self._ocr_service.recognize_image(
            image,
            action=action,
            lang_hint=self._src_lang,
            api_key=self._cfg.modules.ocr_api_key,
        )

    def _on_ocr_ready(self, req_id: int, text: str, action: str) -> None:
        if req_id != self._ocr_service.latest_id:
            return
        self.loading_dots.stop()
        cleaned = (text or "").strip()
        if not cleaned:
            self.text_tool_status.setText(tr("ocr_empty"))
            return
        self.text_tool_input.blockSignals(True)
        self.text_tool_input.setText(cleaned)
        self.text_tool_input.blockSignals(False)
        self.layout_hint_btn.setVisible(False)
        self.input_tile.flash()

        if action == "copy":
            self.clipboard_item_clicked.emit(cleaned)
            self.text_tool_status.setText(tr("ocr_copied"))
        else:
            self._run_translate()

    def _on_ocr_error(self, req_id: int, err: str) -> None:
        if req_id != self._ocr_service.latest_id:
            return
        self.loading_dots.stop()
        self.text_tool_status.setText(err)

    def _paste_into_text_tool(self) -> None:
        if self._all_clip_items:
            self.text_tool_input.setText(self._all_clip_items[0])

    def _clear_text_tool(self) -> None:
        self._tr_debounce.stop()
        self.text_tool_input.clear()
        self.text_tool_output.clear()
        self.text_tool_status.setText("")
        self.layout_hint_btn.setVisible(False)

    def _swap_text_tool_io(self) -> None:
        if self._src_lang != "auto":
            self._src_lang, self._tgt_lang = self._tgt_lang, self._src_lang
            self.src_lang_btn.setText(lang_display_name(self._src_lang))
            self.tgt_lang_btn.setText(lang_display_name(self._tgt_lang))
        elif self._last_detected_src in TRANSLATOR_TARGET_LANGS and self._last_detected_src != self._tgt_lang:
            self._tgt_lang = self._last_detected_src
            self.tgt_lang_btn.setText(lang_display_name(self._tgt_lang))

        out = self.text_tool_output.text().strip()
        if out:
            self._tr_debounce.stop()
            self.text_tool_input.setText(out)
            self._run_translate()

    def _on_fix_layout_clicked(self) -> None:
        self._tr_debounce.stop()
        raw = self.text_tool_input.text()
        fixed = fix_keyboard_layout(raw)
        self.text_tool_output.setText(fixed)
        self.layout_hint_btn.setVisible(False)
        if fixed:
            self.output_tile.flash()
            self.clipboard_item_clicked.emit(fixed)
            self.text_tool_status.setText(tr("status_layout_fixed"))

    def _on_fix_clipboard_layout(self) -> None:
        if self._all_clip_items:
            self._tr_debounce.stop()
            raw = self._all_clip_items[0]
            self.text_tool_input.blockSignals(True)
            self.text_tool_input.setText(raw)
            self.text_tool_input.blockSignals(False)
            fixed = fix_keyboard_layout(raw)
            self.text_tool_output.setText(fixed)
            self.output_tile.flash()
            self.clipboard_item_clicked.emit(fixed)
            self.text_tool_status.setText(tr("status_clip_fixed"))

    def _run_translate(self, direction: str | None = None) -> None:
        self._tr_debounce.stop()
        raw = self.text_tool_input.text().strip()
        if not raw and self._all_clip_items:
            raw = self._all_clip_items[0]
            self.text_tool_input.blockSignals(True)
            self.text_tool_input.setText(raw)
            self.text_tool_input.blockSignals(False)
        if raw:
            self.loading_dots.start()
            self.text_tool_status.setText(tr("status_translating"))
            self._translator.translate(
                raw,
                direction=direction or self._tr_direction,
                src_lang=self._src_lang,
                tgt_lang=self._tgt_lang,
            )

    def _on_translation_ready(self, req_id: int, result: str, src: str, tgt: str) -> None:
        if req_id != self._translator.latest_id:
            return
        self._last_detected_src = src
        self.loading_dots.stop()
        self.text_tool_output.setText(result)
        self.output_tile.flash()
        src_name = lang_display_name(src)
        tgt_name = lang_display_name(tgt)
        self.text_tool_status.setText(f"{src_name} → {tgt_name}")

    def _on_translation_error(self, req_id: int, err: str) -> None:
        if req_id != self._translator.latest_id:
            return
        self.loading_dots.stop()
        self.text_tool_status.setText(err)

    def _copy_text_tool_result(self) -> None:
        res = self.text_tool_output.text().strip()
        if res:
            self.output_tile.flash()
            self.clipboard_item_clicked.emit(res)
            self.text_tool_status.setText(tr("status_copied"))

    # ── Audio, Weather, Media ──────────────────────────────────────────

    def update_volume_ui(self, vol_pct: int, is_muted: bool) -> None:
        self._is_muted = is_muted
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(vol_pct)
        self.volume_slider.blockSignals(False)
        self.volume_pct_lbl.setText("Mute" if is_muted else f"{vol_pct}%")
        self.mute_btn.set_icon_kind("speaker_mute" if is_muted else "speaker")

    def _on_volume_slider_moved(self, val: int) -> None:
        self.volume_pct_lbl.setText(f"{val}%")
        self.volume_set_requested.emit(val)

    def _on_weather_city_submit(self) -> None:
        city = self.weather_city_input.text().strip()
        if city:
            self._cfg.weather.city = city
            self.weather_city_changed.emit(city)
        else:
            self.weather_refresh_requested.emit()

    def update_weather(self, data: WeatherData) -> None:
        self._last_weather = data
        self._weather_kind = data.vector_kind
        a = self._cfg.appearance
        self.weather_icon_lbl.setPixmap(
            render_vector_pixmap(self._weather_kind, 22, a.text_color, a.accent_color)
        )
        self.w_city_title.setText((data.city or self._cfg.weather.city).upper())
        self.w_temp_big.setText(f"{round(data.temp)}°")
        self.w_desc_lbl.setText(data.description)
        self.w_feels_lbl.setText(
            f"{tr('feels_like')} {round(data.feels_like)}° · ↑{round(data.temp_max)}° ↓{round(data.temp_min)}°"
        )
        self.weather_updated_lbl.setText(f"{tr('updated_at')} {data.updated_at}")

        self.wind_widget.set_data(
            data.wind_speed, data.wind_deg, data.wind_dir_label, data.wind_unit
        )
        self.humidity_widget.set_data(data.humidity, data.humidity_comfort)
        self.pressure_widget.set_data(data.pressure_mmhg)

        self.w_rain_big.setText(f"{data.rain_mm:.1f} {tr('mm')}")
        rain_prob = min(100, int(data.clouds_pct * 0.8) if data.rain_mm == 0 else 95)
        self.w_rain_sub.setText(f"{tr('rain_prob')} {rain_prob}%")

        self.w_vis_big.setText(f"{data.visibility_km:.1f} {tr('km')}")
        self.w_vis_sub.setText(f"{tr('clouds_sky')}: {data.clouds_pct}%")
        self.sys_stats_widget.set_weather_summary(
            f"{round(data.temp)}°",
            f"{data.city} · {data.description}",
            data.temp,
        )

    def update_weather_error(self, message: str) -> None:
        self._weather_kind = "cloud"
        a = self._cfg.appearance
        self.weather_icon_lbl.setPixmap(
            render_vector_pixmap("cloud", 22, a.muted_color, a.accent_color)
        )
        self.w_desc_lbl.setText(message)
        self.weather_updated_lbl.setText(message)

    def update_media(self, info: MediaInfo) -> None:
        a = self._cfg.appearance
        self._has_media = info.has_media
        self._is_playing = info.has_media and info.is_playing
        self.waveform.set_playing(self._is_playing)
        self.play_btn.set_icon_kind("pause" if self._is_playing else "play")

        if not info.has_media:
            self._has_album_art = False
            self.track_title_lbl.setText(tr("no_media"))
            self.track_artist_lbl.setText(tr("turn_on_track"))
            self.album_lbl.setPixmap(
                render_vector_pixmap("music_note", 20, a.text_color, a.accent_color)
            )
            return

        self.track_title_lbl.setText(self._elide(info.title, 19))
        self.track_title_lbl.setToolTip(info.title)
        self.track_artist_lbl.setText(self._elide(info.artist, 28))

        if info.thumbnail_bytes:
            pm = QPixmap()
            if pm.loadFromData(info.thumbnail_bytes):
                self._has_album_art = True
                self.album_lbl.setPixmap(_round_pixmap(pm, 42, 10))
                return
        self._has_album_art = False
        self.album_lbl.setPixmap(
            render_vector_pixmap("music_note", 20, a.text_color, a.accent_color)
        )

    # ── Focus Timer, Stopwatch, Alarms & To-Do ─────────────────────────

    def _switch_time_submode(self, idx: int) -> None:
        self.time_sub_stack.setCurrentIndex(idx)
        for i, b in enumerate(self._time_mode_btns):
            b.set_active(i == idx)

    @property
    def active_timer_str(self) -> str:
        if not self._timer_running:
            return ""
        m, s = divmod(self._timer_rem_sec, 60)
        return f"{m:02d}:{s:02d}"

    def _set_focus_minutes(self, mins: int) -> None:
        self._focus_qtimer.stop()
        self._timer_running = False
        self.timer_start_btn.setText(tr("start"))
        self._timer_total_sec = mins * 60
        self._timer_rem_sec = mins * 60
        self.timer_ring.set_time(self._timer_rem_sec, self._timer_total_sec)

    def _toggle_focus_timer(self) -> None:
        if self._timer_running:
            self._focus_qtimer.stop()
            self._timer_running = False
            self.timer_start_btn.setText(tr("resume"))
        else:
            if self._timer_rem_sec <= 0:
                self._timer_rem_sec = self._timer_total_sec
            self._timer_running = True
            self.timer_start_btn.setText(tr("pause"))
            self._focus_qtimer.start()

    def _reset_focus_timer(self) -> None:
        self._focus_qtimer.stop()
        self._timer_running = False
        self.timer_start_btn.setText(tr("start"))
        self._timer_rem_sec = self._timer_total_sec
        self.timer_ring.set_time(self._timer_rem_sec, self._timer_total_sec)

    def _tick_focus_timer(self) -> None:
        if self._timer_rem_sec > 0:
            self._timer_rem_sec -= 1
            self.timer_ring.set_time(self._timer_rem_sec, self._timer_total_sec)
        if self._timer_rem_sec <= 0:
            self._focus_qtimer.stop()
            self._timer_running = False
            self.timer_start_btn.setText(tr("start"))
            self.timer_finished.emit()

    def _toggle_stopwatch(self) -> None:
        if self._stopwatch_running:
            self._stopwatch_qtimer.stop()
            self._stopwatch_running = False
            self.sw_start_btn.setText(tr("resume"))
        else:
            self._stopwatch_running = True
            self.sw_start_btn.setText(tr("pause"))
            self._stopwatch_qtimer.start()

    def _reset_stopwatch(self) -> None:
        self._stopwatch_qtimer.stop()
        self._stopwatch_running = False
        self._stopwatch_tenths = 0
        self.sw_start_btn.setText(tr("start"))
        self.stopwatch_lbl.setText("00:00.0")

    def _tick_stopwatch(self) -> None:
        self._stopwatch_tenths += 1
        total_secs, tenths = divmod(self._stopwatch_tenths, 10)
        mins, secs = divmod(total_secs, 60)
        self.stopwatch_lbl.setText(f"{mins:02d}:{secs:02d}.{tenths}")

    def _add_alarm(self) -> None:
        t_str = self.alarm_time_edit.text().strip()
        note = self.alarm_note_edit.text().strip() or tr("alarm_default_note")
        if len(t_str) == 5 and ":" in t_str:
            self._cfg.focus.alarms.append({"time": t_str, "note": note})
            self.alarm_time_edit.clear()
            self.alarm_note_edit.clear()
            self._rebuild_alarms_ui()
            self.settings_applied.emit(self._cfg)

    def _remove_alarm_item(self, item: QListWidgetItem) -> None:
        row = self.alarms_list.row(item)
        if 0 <= row < len(self._cfg.focus.alarms):
            self._cfg.focus.alarms.pop(row)
            self._rebuild_alarms_ui()
            self.settings_applied.emit(self._cfg)

    def _rebuild_alarms_ui(self) -> None:
        self.alarms_list.clear()
        for entry in self._cfg.focus.alarms:
            it = QListWidgetItem(f"{entry.get('time', '')}  —  {entry.get('note', '')}  ({tr('click_delete')})")
            self.alarms_list.addItem(it)

    def _check_alarms(self, cur_hm: str) -> None:
        for entry in self._cfg.focus.alarms:
            t_str = str(entry.get("time", ""))
            note = str(entry.get("note", tr("alarm_default_note")))
            key = f"{datetime.now().strftime('%Y-%m-%d')}_{t_str}_{note}"
            if t_str == cur_hm and key not in self._fired_alarms_today:
                self._fired_alarms_today.add(key)
                self.alarm_triggered.emit(t_str, note)

    def _rebuild_todo_ui(self) -> None:
        self._todo_checkboxes.clear()
        while self.todo_layout.count():
            item = self.todo_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        a = self._cfg.appearance
        for idx, entry in enumerate(self._cfg.focus.todo_items[:6]):
            row_w = QWidget()
            r_lay = QHBoxLayout(row_w)
            r_lay.setContentsMargins(0, 0, 0, 0)
            r_lay.setSpacing(6)

            chk = SmoothCheckBox(
                text=str(entry.get("text", "")),
                checked=bool(entry.get("done", False)),
                strikethrough_when_checked=True,
            )
            chk.set_colors(a.accent_color, a.text_color, a.muted_color)
            chk.toggled.connect(lambda val, i=idx: self._on_todo_toggled(i, val))
            self._todo_checkboxes.append(chk)

            del_btn = PillButton("", icon_kind="close", variant="IconBtn", icon_size=11)
            del_btn.setFixedSize(20, 20)
            del_btn.clicked.connect(lambda _=False, i=idx: self._remove_todo_item(i))

            r_lay.addWidget(chk, 1)
            r_lay.addWidget(del_btn)
            self.todo_layout.addWidget(row_w)
        self.todo_layout.addStretch()
        self._sync_tasks_summary_to_tiles()

    def _add_todo_item(self) -> None:
        text = self.todo_input.text().strip()
        if not text:
            return
        self._cfg.focus.todo_items.insert(0, {"text": text, "done": False})
        self._cfg.focus.todo_items = self._cfg.focus.todo_items[:6]
        self.todo_input.clear()
        self._rebuild_todo_ui()
        self.settings_applied.emit(self._cfg)

    def _on_todo_toggled(self, index: int, done: bool) -> None:
        if 0 <= index < len(self._cfg.focus.todo_items):
            self._cfg.focus.todo_items[index]["done"] = done
            self._sync_tasks_summary_to_tiles()
            self.settings_applied.emit(self._cfg)

    def _remove_todo_item(self, index: int) -> None:
        if 0 <= index < len(self._cfg.focus.todo_items):
            self._cfg.focus.todo_items.pop(index)
            self._rebuild_todo_ui()
            self.settings_applied.emit(self._cfg)

    # ── Clipboard ──────────────────────────────────────────────────────

    def update_clipboard(self, items: list[str]) -> None:
        self._all_clip_items = list(items)
        self._filter_clipboard_view(self.clip_search_input.text())

    def _filter_clipboard_view(self, query: str) -> None:
        q = query.strip().lower()
        self.clip_list.clear()
        filtered = [t for t in self._all_clip_items if not q or q in t.lower()]
        if not filtered:
            empty = QListWidgetItem(tr("clip_empty"))
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.clip_list.addItem(empty)
            return
        for text in filtered:
            preview = " ".join(text.split())
            if len(preview) > 58:
                preview = preview[:55] + "..."
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, text)
            item.setToolTip(text[:500])
            item.setSizeHint(QSize(0, 30))

            row_w = QWidget()
            row_w.setStyleSheet("background: transparent;")
            r_lay = QHBoxLayout(row_w)
            r_lay.setContentsMargins(6, 2, 4, 2)
            r_lay.setSpacing(6)

            lbl = QLabel(preview)
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            lbl.setStyleSheet("background: transparent; font-size: 12px;")

            del_btn = PillButton("", icon_kind="close", variant="IconBtn", icon_size=11)
            del_btn.setFixedSize(20, 20)
            del_btn.setToolTip(tr("delete"))
            del_btn.clicked.connect(
                lambda _=False, raw=text: self.clipboard_item_delete_requested.emit(raw)
            )

            r_lay.addWidget(lbl, 1)
            r_lay.addWidget(del_btn)

            self.clip_list.addItem(item)
            self.clip_list.setItemWidget(item, row_w)

    def show_copied_feedback(self) -> None:
        self.clip_status_lbl.setText(tr("copied"))

    def clear_copied_feedback(self) -> None:
        self.clip_status_lbl.setText("")

    def _on_clip_clicked(self, item: QListWidgetItem) -> None:
        raw = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(raw, str):
            self.clipboard_item_clicked.emit(raw)
            self.show_copied_feedback()

    @staticmethod
    def _elide(text: str, limit: int) -> str:
        return text if len(text) <= limit else text[: limit - 1] + "…"
