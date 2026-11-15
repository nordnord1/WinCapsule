"""Fluid right-edge droplet widget (v3) with auto-fitting closed pill, PNG mascot, and 160ms snappy morphing."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import math
import os
import subprocess
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
    QRegion,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.config import AppConfig, resource_path
from core.i18n import set_language, tr
from core.themes import build_pill_qss
from services.media_smtc import MediaInfo
from services.weather import WeatherData
from ui.expanded_panel import ExpandedPanel
from ui.icons import load_mascot_pixmap, render_vector_icon, render_vector_pixmap


class PillWindow(QWidget):
    """
    Organic liquid droplet on the right screen edge.
    Closed pill width shrinks/expands dynamically around enabled slots with zero empty gap.
    """

    settings_applied = Signal(object)  # AppConfig
    hide_requested = Signal()
    device_change_detected = Signal()

    MODE_COMPACT = "compact"
    MODE_TOAST = "toast"
    MODE_EXPANDED = "expanded"

    CANVAS_W = 532
    CANVAS_H = 386
    FILLET = 12.0

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cfg = config
        self._mode = self.MODE_COMPACT
        self._hovered = False
        self._hover_t = 0.0
        self._last_download_path = ""
        self._active_download_text = ""
        self._toast_has_actions = False
        self._media_info = MediaInfo()
        self._weather_data: WeatherData | None = None
        self._wave_phase = 0.0
        self._cached_mascot_key: tuple[str, int, str] | None = None
        self._cached_mascot_pm = None

        set_language(config.appearance.language)
        self._setup_window_flags()
        self._register_device_notifications()
        self._build_children()
        self._drop_rect = self._target_drop_rect()
        self._setup_animations_and_timers()
        self.apply_config(config)

    def _setup_window_flags(self) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        if self._cfg.appearance.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

    def _register_device_notifications(self) -> None:
        try:
            class _DEV_BROADCAST_DEVICEINTERFACE(ctypes.Structure):
                _fields_ = [
                    ("dbcc_size", wintypes.DWORD),
                    ("dbcc_devicetype", wintypes.DWORD),
                    ("dbcc_reserved", wintypes.DWORD),
                    ("dbcc_classguid", ctypes.c_byte * 16),
                    ("dbcc_name", ctypes.c_wchar * 2),
                ]

            flt = _DEV_BROADCAST_DEVICEINTERFACE()
            flt.dbcc_size = ctypes.sizeof(_DEV_BROADCAST_DEVICEINTERFACE)
            flt.dbcc_devicetype = 5  # DBT_DEVTYP_DEVICEINTERFACE
            ctypes.windll.user32.RegisterDeviceNotificationW(
                int(self.winId()),
                ctypes.byref(flt),
                0x00000004,  # DEVICE_NOTIFY_WINDOW_HANDLE | DEVICE_NOTIFY_ALL_INTERFACE_CLASSES
            )
        except Exception:
            pass

    def nativeEvent(self, eventType, message):
        try:
            if bytes(eventType) == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0219:  # WM_DEVICECHANGE
                    self.device_change_detected.emit()
        except Exception:
            pass
        return super().nativeEvent(eventType, message)

    def _build_children(self) -> None:
        # ── Toast Overlay (parent=self) ────────────────────────────────
        self.toast_widget = QWidget(self)
        self.toast_widget.setVisible(False)
        self.toast_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        t_lay = QHBoxLayout(self.toast_widget)
        t_lay.setContentsMargins(16, 6, 12, 6)
        t_lay.setSpacing(10)

        self.toast_icon_lbl = QLabel()
        self.toast_icon_lbl.setFixedSize(20, 20)
        self.toast_icon_lbl.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        t_lay.addWidget(self.toast_icon_lbl)

        t_text_col = QVBoxLayout()
        t_text_col.setSpacing(0)
        self.toast_title_lbl = QLabel("")
        self.toast_title_lbl.setStyleSheet("font-size: 12px; font-weight: 700;")
        self.toast_title_lbl.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self.toast_sub_lbl = QLabel("")
        self.toast_sub_lbl.setObjectName("MutedLabel")
        self.toast_sub_lbl.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        t_text_col.addWidget(self.toast_title_lbl)
        t_text_col.addWidget(self.toast_sub_lbl)
        t_lay.addLayout(t_text_col, 1)

        self.toast_open_btn = QPushButton(tr("open"))
        self.toast_open_btn.setObjectName("AccentBtn")
        self.toast_open_btn.setFixedHeight(24)
        self.toast_open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toast_open_btn.clicked.connect(self._open_last_download)

        self.toast_folder_btn = QPushButton(tr("folder_btn"))
        self.toast_folder_btn.setFixedHeight(24)
        self.toast_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toast_folder_btn.clicked.connect(self._open_last_download_folder)

        self.toast_close_btn = QPushButton()
        self.toast_close_btn.setObjectName("IconBtn")
        self.toast_close_btn.setFixedSize(22, 22)
        self.toast_close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toast_close_btn.clicked.connect(self.collapse)

        t_lay.addWidget(self.toast_open_btn)
        t_lay.addWidget(self.toast_folder_btn)
        t_lay.addWidget(self.toast_close_btn)

        # ── Expanded Panel (520x360, parent=self) ──────────────────────
        self.expanded_panel = ExpandedPanel(self._cfg, self)
        self.expanded_panel.setVisible(False)
        self.expanded_panel.settings_applied.connect(self.settings_applied.emit)
        self.expanded_panel.hide_requested.connect(self.hide_requested.emit)
        self.expanded_panel.collapse_requested.connect(self.collapse)
        self.expanded_panel.timer_finished.connect(self.show_timer_toast)
        self.expanded_panel.alarm_triggered.connect(self.show_alarm_toast)
        self.expanded_panel.ocr_snip_requested.connect(self.start_screen_ocr)
        self.expanded_panel.ocr_session_finished.connect(self._finish_screen_ocr)

    def _setup_animations_and_timers(self) -> None:
        self._morph_anim = QVariantAnimation(self)
        self._morph_anim.setDuration(220)
        self._morph_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._morph_anim.valueChanged.connect(self._on_morph_step)
        self._morph_anim.finished.connect(self._on_morph_finished)

        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(190)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_anim.valueChanged.connect(self._on_hover_step)

        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._opacity_anim.setDuration(180)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.OutQuad)

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(50)
        self._anim_timer.timeout.connect(self._tick_compact_canvas)
        self._anim_timer.start()

        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._on_toast_timeout)

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._apply_idle_opacity)

        self._dl_clear_timer = QTimer(self)
        self._dl_clear_timer.setSingleShot(True)
        self._dl_clear_timer.timeout.connect(self._clear_active_download)

    # ── Public API ─────────────────────────────────────────────────────

    def apply_config(self, config: AppConfig) -> None:
        prev_top = self._cfg.appearance.always_on_top
        self._cfg = config
        if prev_top != config.appearance.always_on_top:
            was_visible = self.isVisible()
            self._setup_window_flags()
            if was_visible and not config.appearance.hidden:
                self.show()

        a = config.appearance
        set_language(a.language)
        self.setStyleSheet(build_pill_qss(a))
        self.toast_open_btn.setText(tr("open"))
        self.toast_folder_btn.setText(tr("folder_btn"))
        self.expanded_panel.apply_appearance(a)
        self.expanded_panel.apply_modules(config.modules)

        self.toast_close_btn.setIcon(
            render_vector_icon("collapse", 13, a.text_color, a.accent_color)
        )
        self.toast_close_btn.setIconSize(QSize(13, 13))

        self._position_canvas()

        if config.appearance.hidden:
            self.hide()
        else:
            self.show()
            self._restore_active_opacity()
            self._morph_to(self._target_drop_rect(), animate=False)
            self._reset_idle_timer()

        self.update()

    def open_inline_settings(self) -> None:
        if self._cfg.appearance.hidden:
            self._cfg.appearance.hidden = False
            self.show()
        self.expanded_panel.show_settings()
        if self._mode != self.MODE_EXPANDED:
            self._enter_expanded_mode(reset_page=False)

    def start_screen_ocr(self) -> None:
        """Temporarily hide PillWindow so underlying text is clean, then open ScreenOcrOverlay."""
        self.setVisible(False)
        QTimer.singleShot(120, self.expanded_panel.begin_ocr_overlay)

    def _finish_screen_ocr(self) -> None:
        if not self._cfg.appearance.hidden:
            self.setVisible(True)
            self.raise_()
            self._restore_active_opacity()
            self._reset_idle_timer()

    def show_capslock_toast(self, is_on: bool) -> None:
        if not self._cfg.modules.show_capslock_toast or self._cfg.appearance.hidden:
            return
        if self._mode == self.MODE_EXPANDED:
            return
        a = self._cfg.appearance
        self.toast_icon_lbl.setPixmap(
            render_vector_pixmap(
                "capslock",
                18,
                a.text_color,
                a.accent_color if is_on else a.muted_color,
            )
        )
        self.toast_title_lbl.setText("CAPS LOCK ON" if is_on else "CAPS LOCK OFF")
        self.toast_sub_lbl.setText(tr("toast_caps_on") if is_on else tr("toast_caps_off"))
        self._toast_has_actions = False
        self.toast_open_btn.setVisible(False)
        self.toast_folder_btn.setVisible(False)
        self._enter_toast_mode(duration_ms=2200)

    def show_device_toast(self, icon_kind: str, device_name: str) -> None:
        if not self._cfg.modules.show_device_toast or self._cfg.appearance.hidden:
            return
        if self._mode == self.MODE_EXPANDED:
            return
        a = self._cfg.appearance
        self.toast_icon_lbl.setPixmap(
            render_vector_pixmap(icon_kind, 18, a.text_color, a.accent_color)
        )
        self.toast_title_lbl.setText(tr("toast_device_connected"))
        clean_name = device_name if len(device_name) <= 34 else device_name[:33] + "…"
        self.toast_sub_lbl.setText(clean_name)
        self._toast_has_actions = False
        self.toast_open_btn.setVisible(False)
        self.toast_folder_btn.setVisible(False)
        self._enter_toast_mode(duration_ms=2600)

    def show_timer_toast(self) -> None:
        QApplication.beep()
        if self._cfg.appearance.hidden:
            self._cfg.appearance.hidden = False
            self.show()
        if self._mode == self.MODE_EXPANDED:
            return
        a = self._cfg.appearance
        self.toast_icon_lbl.setPixmap(
            render_vector_pixmap("sun", 18, a.text_color, a.accent_color)
        )
        self.toast_title_lbl.setText(tr("toast_timer_done"))
        self.toast_sub_lbl.setText(tr("toast_timer_sub"))
        self._toast_has_actions = False
        self.toast_open_btn.setVisible(False)
        self.toast_folder_btn.setVisible(False)
        self._enter_toast_mode(duration_ms=4500)

    def show_alarm_toast(self, time_str: str, note: str) -> None:
        QApplication.beep()
        if self._cfg.appearance.hidden:
            self._cfg.appearance.hidden = False
            self.show()
        if self._mode == self.MODE_EXPANDED:
            return
        a = self._cfg.appearance
        self.toast_icon_lbl.setPixmap(
            render_vector_pixmap("sun", 18, a.text_color, a.accent_color)
        )
        self.toast_title_lbl.setText(f"{tr('toast_alarm')} {time_str}")
        self.toast_sub_lbl.setText(note)
        self._toast_has_actions = False
        self.toast_open_btn.setVisible(False)
        self.toast_folder_btn.setVisible(False)
        self._enter_toast_mode(duration_ms=5500)

    def show_download_progress(self, file_name: str, size_str: str) -> None:
        if not self._cfg.modules.show_download_toast:
            return
        if self._cfg.appearance.hidden:
            self._cfg.appearance.hidden = False
            self.show()
        short_name = file_name if len(file_name) <= 14 else file_name[:12] + "…"
        self._active_download_text = f"{short_name} · {size_str}"
        self._dl_clear_timer.start(15000)
        self._restore_active_opacity()
        self._reset_idle_timer()
        if self._mode == self.MODE_COMPACT:
            target = self._target_drop_rect()
            if abs(target.width() - self._drop_rect.width()) > 2.0:
                self._morph_to(target, animate=True)
            else:
                self.update()

    def clear_download_progress(self) -> None:
        self._dl_clear_timer.stop()
        self._clear_active_download()

    def _clear_active_download(self) -> None:
        if not self._active_download_text:
            return
        self._active_download_text = ""
        if self._mode == self.MODE_COMPACT:
            self._morph_to(self._target_drop_rect(), animate=True)

    def show_download_toast(self, full_path: str, file_name: str, size_str: str) -> None:
        if not self._cfg.modules.show_download_toast:
            return
        self._dl_clear_timer.stop()
        self._active_download_text = ""
        if self._cfg.appearance.hidden:
            self._cfg.appearance.hidden = False
            self.show()
        a = self._cfg.appearance
        self._last_download_path = full_path
        short_name = file_name if len(file_name) <= 24 else file_name[:22] + "…"
        self.toast_icon_lbl.setPixmap(
            render_vector_pixmap("download", 18, a.text_color, a.accent_color)
        )
        self.toast_title_lbl.setText(short_name)
        self.toast_sub_lbl.setText(f"{tr('toast_dl_done')} · {size_str}")
        self._toast_has_actions = True
        self.toast_open_btn.setVisible(True)
        self.toast_folder_btn.setVisible(True)
        self._enter_toast_mode(duration_ms=5200)

    def update_weather(self, data: WeatherData) -> None:
        self._weather_data = data
        self.expanded_panel.update_weather(data)
        if self._mode == self.MODE_COMPACT:
            self._morph_to(self._target_drop_rect(), animate=True)

    def update_weather_error(self, message: str) -> None:
        self.expanded_panel.update_weather_error(message)

    def update_media(self, info: MediaInfo) -> None:
        self._media_info = info
        self.expanded_panel.update_media(info)
        if self._mode == self.MODE_COMPACT:
            self._morph_to(self._target_drop_rect(), animate=True)

    def toggle_expand(self) -> None:
        if self._mode == self.MODE_EXPANDED:
            self.collapse()
        else:
            self.expand()

    def expand(self) -> None:
        self._enter_expanded_mode(reset_page=False)

    def _enter_expanded_mode(self, reset_page: bool = False) -> None:
        self._toast_timer.stop()
        self._idle_timer.stop()
        self.toast_widget.setVisible(False)
        if reset_page:
            self.expanded_panel.show_dashboard()
        self._mode = self.MODE_EXPANDED
        self.expanded_panel.clear_copied_feedback()
        self._restore_active_opacity()

        target = self._target_drop_rect()
        # Position and show expanded_panel immediately so there's zero blank delay;
        # the expanding QRegion mask reveals it smoothly at 60+ FPS!
        self.expanded_panel.setGeometry(target.toRect())
        self.expanded_panel.setVisible(True)
        self.expanded_panel.play_open_animations()
        self._morph_anim.setDuration(235)
        self._morph_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._morph_to(target, animate=True)
        self.activateWindow()

    def collapse(self) -> None:
        self._toast_timer.stop()
        self.toast_widget.setVisible(False)
        self._mode = self.MODE_COMPACT
        self._morph_anim.setDuration(205)
        self._morph_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._morph_to(self._target_drop_rect(), animate=True)
        self._reset_idle_timer()

    # ── Dynamic Closed Pill Segments (Zero Empty Gap!) ─────────────────

    def _compute_compact_segments(self) -> list[tuple[str, str, float]]:
        """
        Return a list of (segment_kind, text_payload, width_px) for enabled closed-pill items.
        Automatically omits disabled or inactive items so there is never any empty space!
        """
        a = self._cfg.appearance
        fm = QFontMetrics(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        segments: list[tuple[str, str, float]] = []

        if a.compact_show_mascot:
            ms = float(max(18, min(30, a.mascot_size)))
            segments.append(("mascot", "", ms))

        if self._active_download_text:
            tw = 18.0 + float(fm.horizontalAdvance(self._active_download_text))
            segments.append(("download", self._active_download_text, tw))

        if (
            a.compact_show_music
            and self._media_info.has_media
            and self._media_info.is_playing
        ):
            title = self._media_info.title
            if len(title) > 14:
                title = title[:13] + "…"
            tw = float(fm.horizontalAdvance(title)) + 18.0
            segments.append(("music", title, tw))

        timer_str = self.expanded_panel.active_timer_str if hasattr(self, "expanded_panel") else ""
        if a.compact_show_timer and timer_str:
            tw = float(fm.horizontalAdvance(timer_str)) + 4.0
            segments.append(("timer", timer_str, tw))

        if a.compact_show_clock:
            t_str = datetime.now().strftime("%H:%M")
            tw = float(fm.horizontalAdvance(t_str)) + 2.0
            segments.append(("clock", t_str, tw))

        if a.compact_show_weather:
            temp_str = (
                f"{round(self._weather_data.temp)}°"
                if self._weather_data is not None
                else "--°"
            )
            tw = 18.0 + float(fm.horizontalAdvance(temp_str))
            segments.append(("weather", temp_str, tw))

        return segments

    def _position_canvas(self) -> None:
        screen = QApplication.primaryScreen()
        geo = screen.geometry() if screen else QRect(0, 0, 1920, 1080)
        x = geo.x() + geo.width() - self.CANVAS_W
        y = geo.y() + self._cfg.appearance.vertical_offset_px - int(self.FILLET)
        self.setGeometry(x, y, self.CANVAS_W, self.CANVAS_H)

    def _target_drop_rect(self) -> QRectF:
        cw = float(self.CANVAS_W)
        f = self.FILLET
        if self._mode == self.MODE_EXPANDED:
            w, h = 520.0, 360.0
            return QRectF(cw - w, f, w, h)
        if self._mode == self.MODE_TOAST:
            has_btns = getattr(self, "_toast_has_actions", False)
            w = 320.0 if has_btns else 220.0
            h = 46.0
            return QRectF(cw - w, f, w, h)

        segments = self._compute_compact_segments()
        if not segments:
            # Tiny mini-droplet when all closed items are unchecked
            w, h = 30.0, 22.0
            return QRectF(cw - w, f, w, h)

        gap = 10.0
        left_pad = 16.0
        right_pad = 14.0
        total_w = left_pad + sum(s[2] for s in segments) + gap * (len(segments) - 1) + right_pad
        w = max(56.0, min(380.0, total_w))
        h = 36.0
        return QRectF(cw - w, f, w, h)

    def _morph_to(self, target: QRectF, animate: bool = True) -> None:
        self._morph_anim.stop()
        if not animate or not self.isVisible():
            self._drop_rect = QRectF(target)
            self._sync_children_and_mask(settled=True)
            self.update()
            return
        self._morph_anim.setStartValue(self._drop_rect)
        self._morph_anim.setEndValue(target)
        self._morph_anim.start()

    def _on_morph_step(self, value) -> None:
        if isinstance(value, QRectF):
            self._drop_rect = value
            self._sync_children_and_mask(settled=False)
            self.update()

    def _on_morph_finished(self) -> None:
        self._drop_rect = self._target_drop_rect()
        self._sync_children_and_mask(settled=True)
        self.update()

    def _sync_children_and_mask(self, settled: bool) -> None:
        r = self._drop_rect.toRect()
        f = int(self.FILLET)
        mask_rect = QRect(
            max(0, r.x() - 2),
            max(0, r.y() - f),
            self.CANVAS_W - max(0, r.x() - 2),
            min(self.CANVAS_H, r.height() + 2 * f + 2),
        )
        self.setMask(QRegion(mask_rect))

        if settled:
            if self._mode == self.MODE_EXPANDED:
                self.expanded_panel.setGeometry(r)
                self.expanded_panel.setVisible(True)
            elif self._mode == self.MODE_TOAST:
                self.expanded_panel.setVisible(False)
                self.toast_widget.setGeometry(r)
                self.toast_widget.setVisible(True)
            else:
                self.expanded_panel.setVisible(False)
                self.toast_widget.setVisible(False)

    def _enter_toast_mode(self, duration_ms: int) -> None:
        self._idle_timer.stop()
        self.expanded_panel.setVisible(False)
        self._mode = self.MODE_TOAST
        self._restore_active_opacity()
        target = self._target_drop_rect()
        self.toast_widget.setGeometry(target.toRect())
        self.toast_widget.setVisible(True)
        self._morph_to(target, animate=True)
        self._toast_timer.start(duration_ms)

    def _on_toast_timeout(self) -> None:
        if self._hovered:
            self._toast_timer.start(1200)
            return
        self.collapse()

    def _tick_compact_canvas(self) -> None:
        self._wave_phase += 0.45
        if self._mode == self.MODE_COMPACT and self.isVisible():
            self.update()

    def _update_clock(self) -> None:
        self.expanded_panel.update_clock()
        if self._mode == self.MODE_COMPACT:
            target = self._target_drop_rect()
            if abs(target.width() - self._drop_rect.width()) > 2.0:
                self._morph_to(target, animate=True)
            else:
                self.update()

    def _reset_idle_timer(self) -> None:
        self._idle_timer.stop()
        if (
            self._cfg.appearance.idle_fade_enabled
            and self._mode == self.MODE_COMPACT
            and not self._hovered
        ):
            self._idle_timer.start(self._cfg.appearance.idle_delay_sec * 1000)

    def _apply_idle_opacity(self) -> None:
        if self._mode == self.MODE_COMPACT and not self._hovered:
            self._animate_opacity(self._cfg.appearance.idle_opacity)

    def _restore_active_opacity(self) -> None:
        self._animate_opacity(self._cfg.appearance.base_opacity)

    def _animate_opacity(self, target: float) -> None:
        self._opacity_anim.stop()
        self._opacity_anim.setStartValue(self.windowOpacity())
        self._opacity_anim.setEndValue(target)
        self._opacity_anim.start()

    def _open_last_download(self) -> None:
        if self._last_download_path and os.path.exists(self._last_download_path):
            os.startfile(self._last_download_path)
        self.collapse()

    def _open_last_download_folder(self) -> None:
        if self._last_download_path:
            p = Path(self._last_download_path)
            if p.exists():
                norm = os.path.normpath(str(p)).replace('"', "")
                # Pass raw string on Windows so list2cmdline does NOT wrap /select,path in quotes
                # (quoted "/select,..." makes explorer.exe fall back to opening Documents).
                subprocess.Popen(f'explorer.exe /select,"{norm}"')
            elif p.parent.exists():
                os.startfile(str(p.parent))
        self.collapse()

    # ── Organic Droplet Path & Ambient Gradient Painting ───────────────

    def _build_droplet_path(self, rect: QRectF) -> tuple[QPainterPath, QPainterPath]:
        f = self.FILLET
        x0 = rect.left()
        x1 = float(self.CANVAS_W)
        top_y = rect.top()
        bot_y = rect.bottom()
        body_h = max(14.0, rect.height())
        r = min(body_h / 2.0, 22.0)

        fill_path = QPainterPath()
        fill_path.moveTo(x1, top_y - f)
        fill_path.quadTo(x1, top_y, x1 - f, top_y)
        fill_path.lineTo(x0 + r, top_y)
        fill_path.quadTo(x0, top_y, x0, top_y + r)
        fill_path.lineTo(x0, bot_y - r)
        fill_path.quadTo(x0, bot_y, x0 + r, bot_y)
        fill_path.lineTo(x1 - f, bot_y)
        fill_path.quadTo(x1, bot_y, x1, bot_y + f)
        fill_path.closeSubpath()

        rim_path = QPainterPath()
        rim_path.moveTo(x1, top_y - f)
        rim_path.quadTo(x1, top_y, x1 - f, top_y)
        rim_path.lineTo(x0 + r, top_y)
        rim_path.quadTo(x0, top_y, x0, top_y + r)
        rim_path.lineTo(x0, bot_y - r)
        rim_path.quadTo(x0, bot_y, x0 + r, bot_y)
        rim_path.lineTo(x1 - f, bot_y)
        rim_path.quadTo(x1, bot_y, x1, bot_y + f)

        return fill_path, rim_path

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        r = self._drop_rect
        a = self._cfg.appearance
        fill_path, rim_path = self._build_droplet_path(r)

        # 1. Base fill
        base_bg = QColor(a.bg_color)
        painter.fillPath(fill_path, base_bg)

        # 2. Subtle radial ambient glow in bottom-right
        glow_center = QPointF(r.right() - r.width() * 0.22, r.bottom() + r.height() * 0.12)
        glow_radius = max(r.width() * 0.72, r.height() * 0.85)
        ambient = QRadialGradient(glow_center, glow_radius)
        glow_col = QColor(a.ambient_glow_color)
        base_alpha = 72 if self._mode == self.MODE_COMPACT else 48
        glow_col.setAlpha(int(base_alpha + 32 * self._hover_t))
        glow_end = QColor(a.ambient_glow_color)
        glow_end.setAlpha(0)
        ambient.setColorAt(0.0, glow_col)
        ambient.setColorAt(1.0, glow_end)
        painter.fillPath(fill_path, ambient)

        # 3. Specular rim border (glows with accent tint on hover)
        ac_col = QColor(a.accent_color)
        rim_color = QColor(
            round(255 + (ac_col.red() - 255) * 0.5 * self._hover_t),
            round(255 + (ac_col.green() - 255) * 0.5 * self._hover_t),
            round(255 + (ac_col.blue() - 255) * 0.5 * self._hover_t),
            int(24 + 56 * self._hover_t),
        )
        painter.setPen(QPen(rim_color, 1.0 + 0.35 * self._hover_t))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(rim_path)

        # 4. Compact mode content (tightly packed with zero empty space)
        if self._mode == self.MODE_COMPACT and r.height() <= 45:
            segments = self._compute_compact_segments()
            if segments:
                self._paint_compact_segments(painter, r, segments)
            else:
                self._paint_compact_mini_drop(painter, r)

        painter.end()

    def _paint_compact_segments(
        self, p: QPainter, r: QRectF, segments: list[tuple[str, str, float]]
    ) -> None:
        a = self._cfg.appearance
        cy = r.center().y()
        x_cur = r.left() + 16.0
        gap = 10.0
        font = QFont("Segoe UI", 10, QFont.Weight.DemiBold)

        for kind, text_val, seg_w in segments:
            if kind == "download":
                pm = render_vector_pixmap("download", 14, a.accent_color, a.accent_color)
                p.drawPixmap(int(x_cur), int(cy - 7.0), pm)
                p.setPen(QColor(a.accent_color))
                p.setFont(font)
                p.drawText(
                    QRectF(x_cur + 18.0, r.top(), seg_w - 18.0, r.height()),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    text_val,
                )

            elif kind == "mascot":
                ms = int(seg_w)
                key = (a.mascot_path, ms, a.accent_color)
                if key != self._cached_mascot_key or self._cached_mascot_pm is None:
                    self._cached_mascot_key = key
                    self._cached_mascot_pm = load_mascot_pixmap(
                        a.mascot_path, ms, a.accent_color
                    )
                p.drawPixmap(int(x_cur), int(cy - ms / 2.0), self._cached_mascot_pm)

            elif kind == "music":
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(a.accent_color))
                for i, off in enumerate((0.0, 1.4, 2.7)):
                    ratio = 0.35 + 0.60 * (0.5 + 0.5 * math.sin(self._wave_phase + off))
                    bh = max(3.0, 11.0 * ratio)
                    p.drawRoundedRect(
                        QRectF(x_cur + i * 4.0, cy - bh / 2.0, 2.0, bh), 1.0, 1.0
                    )
                p.setPen(QColor(a.accent_color))
                p.setFont(font)
                p.drawText(
                    QRectF(x_cur + 15.0, r.top(), seg_w - 15.0, r.height()),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    text_val,
                )

            elif kind == "timer":
                p.setPen(QColor(a.accent_color))
                p.setFont(font)
                p.drawText(
                    QRectF(x_cur, r.top(), seg_w, r.height()),
                    Qt.AlignmentFlag.AlignCenter,
                    text_val,
                )

            elif kind == "clock":
                p.setPen(QColor(a.text_color))
                p.setFont(font)
                p.drawText(
                    QRectF(x_cur, r.top(), seg_w, r.height()),
                    Qt.AlignmentFlag.AlignCenter,
                    text_val,
                )

            elif kind == "weather":
                w_kind = (
                    self._weather_data.vector_kind
                    if self._weather_data is not None
                    else "cloud_sun"
                )
                pm = render_vector_pixmap(w_kind, 15, a.text_color, a.accent_color)
                p.drawPixmap(int(x_cur), int(cy - 7.5), pm)
                p.setPen(QColor(a.text_color))
                p.setFont(font)
                p.drawText(
                    QRectF(x_cur + 18.0, r.top(), seg_w - 18.0, r.height()),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    text_val,
                )

            x_cur += seg_w + gap

    def _paint_compact_mini_drop(self, p: QPainter, r: QRectF) -> None:
        a = self._cfg.appearance
        accent = QColor(a.accent_color)
        accent.setAlpha(215 if self._hovered else 140)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        dot_h = 8.0 if self._hovered else 6.0
        p.drawRoundedRect(
            QRectF(r.center().x() + 1.0, r.center().y() - dot_h / 2.0, 2.4, dot_h),
            1.2,
            1.2,
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            if self._mode in (self.MODE_COMPACT, self.MODE_TOAST):
                if self._drop_rect.adjusted(-4, -self.FILLET, 4, self.FILLET).contains(pos):
                    self.expand()
                    event.accept()
                    return
            elif self._mode == self.MODE_EXPANDED:
                if pos.x() >= self.CANVAS_W - 8:
                    self.collapse()
                    event.accept()
                    return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self._mode == self.MODE_EXPANDED:
            self.collapse()
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_hover_step(self, value) -> None:
        self._hover_t = float(value)
        if self._mode == self.MODE_COMPACT and self._morph_anim.state() != QVariantAnimation.State.Running:
            base = self._target_drop_rect()
            extra_w = 6.0 * self._hover_t
            extra_h = 2.0 * self._hover_t
            self._drop_rect = QRectF(
                base.left() - extra_w,
                base.top() - extra_h / 2.0,
                base.width() + extra_w,
                base.height() + extra_h,
            )
            self._sync_children_and_mask(settled=False)
        self.update()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._idle_timer.stop()
        self._restore_active_opacity()
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_t)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._reset_idle_timer()
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_t)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        self.update()
        super().leaveEvent(event)
