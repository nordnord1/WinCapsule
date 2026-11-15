"""Custom QPainter visual widgets: SmoothCheckBox, CharacterBadgeWidget, WeekDayProgressWidget, Eyedropper, Weather gauges."""

from __future__ import annotations

from datetime import datetime, timedelta
import math
import os
import time
from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QRect, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QHBoxLayout, QWidget

from core.i18n import tr
from ui.anim import PillButton, Theme
from ui.icons import load_mascot_pixmap

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None


def _anim(parent, duration: int, curve, slot) -> QVariantAnimation:
    a = QVariantAnimation(parent)
    a.setDuration(duration)
    a.setEasingCurve(curve)
    a.valueChanged.connect(slot)
    return a


def _go(anim: QVariantAnimation, start: float, end: float) -> None:
    anim.stop()
    anim.setStartValue(float(start))
    anim.setEndValue(float(end))
    anim.start()


class SmoothCheckBox(QWidget):
    """Checkbox with an animated, self-drawing vector checkmark and springy box."""

    toggled = Signal(bool)

    def __init__(
        self,
        text: str = "",
        checked: bool = False,
        strikethrough_when_checked: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._checked = checked
        self._strike = strikethrough_when_checked
        self._hovered = False
        self._hover_t = 0.0
        self._check_t = 1.0 if checked else 0.0
        self._accent = QColor("#E2A86B")
        self._text_color = QColor("#F4F2EE")
        self._muted_color = QColor("#8C877E")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(24)
        self._check_anim = _anim(self, 340, QEasingCurve.Type.OutBack, self._set_check)
        self._hover_anim = _anim(self, 180, QEasingCurve.Type.OutCubic, self._set_hover)

    def _set_check(self, v) -> None:
        self._check_t = float(v)
        self.update()

    def _set_hover(self, v) -> None:
        self._hover_t = float(v)
        self.update()

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        self._checked = bool(checked)
        self._check_anim.stop()
        self._check_t = 1.0 if self._checked else 0.0
        self.update()

    def text(self) -> str:
        return self._text

    def setText(self, text: str) -> None:
        self._text = text
        self.update()

    def set_colors(self, accent: str, text_col: str, muted_col: str) -> None:
        self._accent = QColor(accent)
        self._text_color = QColor(text_col)
        self._muted_color = QColor(muted_col)
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self._check_anim.setEasingCurve(
                QEasingCurve.Type.OutBack if self._checked else QEasingCurve.Type.OutCubic
            )
            _go(self._check_anim, self._check_t, 1.0 if self._checked else 0.0)
            self.toggled.emit(self._checked)
            event.accept()
            return
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:
        self._hovered = True
        _go(self._hover_anim, self._hover_t, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        _go(self._hover_anim, self._hover_t, 0.0)
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        t = max(0.0, self._check_t)
        h = self._hover_t
        box_size = 16.0
        by = (self.height() - box_size) / 2.0
        box_rect = QRectF(2.0, by, box_size, box_size)

        # outline (fades out as the fill grows)
        border_c = QColor(self._accent if h > 0.5 else QColor(255, 255, 255))
        border_c.setAlpha(int(55 + 150 * h) if t < 0.99 else 0)
        p.setPen(QPen(border_c, 1.3))
        p.setBrush(QColor(255, 255, 255, int(6 + 10 * h)))
        p.drawRoundedRect(box_rect, 5.0, 5.0)

        # springy accent fill
        if t > 0.01:
            s = box_size * min(1.12, t)
            fill = QRectF(
                box_rect.center().x() - s / 2.0, box_rect.center().y() - s / 2.0, s, s
            )
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._accent.lighter(100 + int(12 * h)))
            p.drawRoundedRect(fill, 5.0, 5.0)

            # self-drawing check stroke
            draw_t = max(0.0, min(1.0, (t - 0.25) / 0.75))
            if draw_t > 0:
                pts = [
                    QPointF(box_rect.left() + 4.0, box_rect.top() + 8.4),
                    QPointF(box_rect.left() + 7.0, box_rect.top() + 11.4),
                    QPointF(box_rect.left() + 12.3, box_rect.top() + 5.0),
                ]
                l1 = math.dist((pts[0].x(), pts[0].y()), (pts[1].x(), pts[1].y()))
                l2 = math.dist((pts[1].x(), pts[1].y()), (pts[2].x(), pts[2].y()))
                total = (l1 + l2) * draw_t
                path = QPainterPath(pts[0])
                if total <= l1:
                    k = total / l1
                    path.lineTo(pts[0] + (pts[1] - pts[0]) * k)
                else:
                    path.lineTo(pts[1])
                    k = (total - l1) / l2
                    path.lineTo(pts[1] + (pts[2] - pts[1]) * k)
                p.setPen(QPen(QColor("#0B0B0E"), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)

        if self._text:
            font = QFont("Segoe UI", 9)
            if self._strike and self._checked:
                font.setStrikeOut(True)
                p.setPen(self._muted_color)
            else:
                c = QColor(self._text_color)
                c.setAlpha(int(215 + 40 * h))
                p.setPen(c)
            p.setFont(font)
            text_rect = QRectF(26.0 + 2.0 * h, 0.0, self.width() - 28.0, float(self.height()))
            p.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                self._text,
            )
        p.end()


class CharacterBadgeWidget(QWidget):
    """Static PNG/WEBP character avatar rendered in the header."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path = ""
        self._size = 24
        self._accent = "#E2A86B"
        self._pm = load_mascot_pixmap("", 24, self._accent)
        self.setFixedSize(26, 26)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def configure(self, path: str, size: int, accent: str) -> None:
        size = max(16, min(40, int(size)))
        if (path, size, accent) != (self._path, self._size, self._accent):
            self._path = path
            self._size = size
            self._accent = accent
            self._pm = load_mascot_pixmap(path, size, accent)
            self.setFixedSize(size + 2, size + 2)
            self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        x = (self.width() - self._size) / 2.0
        y = (self.height() - self._size) / 2.0
        p.drawPixmap(int(x), int(y), self._pm)
        p.end()


class DotIndicatorBar(QWidget):
    """Pagination indicator ('• • ▬ • • •') matching the reference header."""

    page_selected = Signal(int)

    def __init__(self, count: int = 6, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._count = count
        self._current = 0
        self._pos = 0.0
        self._hover_idx = -1
        self._accent = QColor("#E2A86B")
        self._muted = QColor(255, 255, 255, 65)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setFixedSize(98, 16)
        self._pos_anim = _anim(self, 380, QEasingCurve.Type.OutBack, self._set_pos)

    def _set_pos(self, v) -> None:
        self._pos = float(v)
        self.update()

    def set_current(self, index: int) -> None:
        index = max(0, min(self._count - 1, index))
        if index == self._current and self._pos_anim.state() != QVariantAnimation.State.Running:
            self._pos = float(index)
            self.update()
            return
        self._current = index
        _go(self._pos_anim, self._pos, float(index))

    def set_accent(self, hex_color: str) -> None:
        self._accent = QColor(hex_color)
        self.update()

    def _idx_at(self, x: float) -> int:
        slot_w = self.width() / max(1, self._count)
        return max(0, min(self._count - 1, int(x // slot_w)))

    def mouseMoveEvent(self, event) -> None:
        idx = self._idx_at(event.position().x())
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover_idx = -1
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self._idx_at(event.position().x())
            self.set_current(idx)
            self.page_selected.emit(idx)
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)

        x = 2.0
        cy = self.height() / 2.0
        for i in range(self._count):
            k = max(0.0, 1.0 - abs(i - self._pos))  # 1 at the active slot, smooth falloff
            w = 5.2 + (18.0 - 5.2) * k
            col = QColor(self._muted)
            if i == self._hover_idx and k < 0.5:
                col.setAlpha(150)
            mixed = QColor(
                round(col.red() + (self._accent.red() - col.red()) * k),
                round(col.green() + (self._accent.green() - col.green()) * k),
                round(col.blue() + (self._accent.blue() - col.blue()) * k),
                round(col.alpha() + (255 - col.alpha()) * k),
            )
            p.setBrush(mixed)
            p.drawRoundedRect(QRectF(x, cy - 2.6, w, 5.2), 2.6, 2.6)
            x += w + 5.5
        p.end()


class ThinDivider(QWidget):
    """Hair-thin gradient line separator to replace boxy card borders."""

    def __init__(self, vertical: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vertical = vertical
        if vertical:
            self.setFixedWidth(1)
        else:
            self.setFixedHeight(1)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        if self._vertical:
            grad = QLinearGradient(0, 0, 0, self.height())
        else:
            grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        grad.setColorAt(0.2, QColor(255, 255, 255, 24))
        grad.setColorAt(0.8, QColor(255, 255, 255, 24))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillRect(self.rect(), grad)
        p.end()


class WeekDayProgressWidget(QWidget):
    """Mini week strip (Пн..Нд) + live Day Progress Bar with intro animation and hover lift."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = QColor("#E2A86B")
        self._text = QColor("#F4F2EE")
        self._muted = QColor("#8C877E")
        self._intro_t = 1.0
        self._hover_idx = -1
        self._hover_t = [0.0] * 7
        self.setMouseTracking(True)
        self.setFixedHeight(76)
        self._intro_anim = _anim(self, 900, QEasingCurve.Type.OutCubic, self._set_intro)
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(16)
        self._hover_timer.timeout.connect(self._tick_hover)

    def set_colors(self, accent: str, text_col: str, muted_col: str) -> None:
        self._accent = QColor(accent)
        self._text = QColor(text_col)
        self._muted = QColor(muted_col)
        self.update()

    def play_intro(self) -> None:
        _go(self._intro_anim, 0.0, 1.0)

    def _set_intro(self, v) -> None:
        self._intro_t = float(v)
        self.update()

    def mouseMoveEvent(self, e) -> None:
        idx = -1
        if e.position().y() <= 40:
            idx = max(0, min(6, int(e.position().x() // (self.width() / 7.0))))
        if idx != self._hover_idx:
            self._hover_idx = idx
            self._hover_timer.start()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover_idx = -1
        self._hover_timer.start()
        super().leaveEvent(e)

    def _tick_hover(self) -> None:
        done = True
        for i in range(7):
            target = 1.0 if i == self._hover_idx else 0.0
            cur = self._hover_t[i]
            nxt = cur + (target - cur) * 0.25
            if abs(nxt - target) < 0.01:
                nxt = target
            else:
                done = False
            self._hover_t[i] = nxt
        self.update()
        if done:
            self._hover_timer.stop()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        now = datetime.now()
        today_idx = now.weekday()
        monday = now - timedelta(days=today_idx)
        day_names = tr("days_short").split(",")
        it = self._intro_t

        slot_w = w / 7.0
        for i in range(7):
            d = monday + timedelta(days=i)
            # staggered intro: each day pops slightly later
            k = max(0.0, min(1.0, it * 1.6 - i * 0.09))
            hv = self._hover_t[i]
            lift = 2.5 * hv + (1.0 - k) * 8.0
            rect = QRectF(i * slot_w + 3.0, 2.0 - lift + 2.5, slot_w - 6.0, 36.0)
            p.setOpacity(k)
            if i == today_idx:
                bg = QColor(self._accent)
                bg.setAlpha(int(40 + 25 * hv))
                p.setPen(QPen(self._accent, 1.2))
                p.setBrush(bg)
                p.drawRoundedRect(rect, 10.0, 10.0)
                p.setPen(self._accent)
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 255, 255, int(8 + 14 * hv)))
                p.drawRoundedRect(rect, 10.0, 10.0)
                p.setPen(self._muted)

            p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            p.drawText(QRectF(rect.left(), rect.top() + 3.0, rect.width(), 12.0), Qt.AlignmentFlag.AlignCenter, day_names[i])
            p.setPen(self._text if i == today_idx or hv > 0.5 else self._muted)
            p.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
            p.drawText(QRectF(rect.left(), rect.top() + 15.0, rect.width(), 18.0), Qt.AlignmentFlag.AlignCenter, str(d.day))
        p.setOpacity(1.0)

        secs_passed = now.hour * 3600 + now.minute * 60 + now.second
        pct = (secs_passed / 86400.0) * 100.0
        rem_secs = max(0, 86400 - secs_passed)
        rem_h = rem_secs // 3600
        rem_m = (rem_secs % 3600) // 60
        shown_pct = pct * it

        p.setPen(self._muted)
        p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        p.drawText(QRectF(4.0, 46.0, 220.0, 14.0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{tr('day_progress')}  ·  {shown_pct:.1f}%")
        p.drawText(QRectF(w - 220.0, 46.0, 216.0, 14.0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{tr('left_today')}: {rem_h} {tr('hours_short')} {rem_m:02d} {tr('mins_short')}")

        bar_y = 64.0
        bar_rect = QRectF(4.0, bar_y, w - 8.0, 6.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 24))
        p.drawRoundedRect(bar_rect, 3.0, 3.0)

        fill_w = max(6.0, (w - 8.0) * (shown_pct / 100.0))
        grad = QLinearGradient(4.0, bar_y, 4.0 + fill_w, bar_y)
        grad.setColorAt(0.0, self._accent.darker(130))
        grad.setColorAt(1.0, self._accent)
        p.setBrush(grad)
        p.drawRoundedRect(QRectF(4.0, bar_y, fill_w, 6.0), 3.0, 3.0)
        # glowing head
        head = QColor(self._accent)
        head.setAlpha(90)
        p.setBrush(head)
        p.drawEllipse(QPointF(4.0 + fill_w - 2.0, bar_y + 3.0), 5.0, 5.0)
        p.setBrush(QColor(255, 255, 255, 230))
        p.drawEllipse(QPointF(4.0 + fill_w - 2.0, bar_y + 3.0), 2.0, 2.0)
        p.end()


OVERVIEW_TILE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("cpu", "CPU (Процесор)"),
    ("ram", "RAM (Пам'ять)"),
    ("disk_c", "Диск C:"),
    ("disk_d", "Диск D:"),
    ("net", "Мережа ↓↑"),
    ("weather", "Погода"),
    ("tasks", "Фокус / Задачі"),
    ("none", "Вимкнено"),
)


def get_tile_options() -> list[tuple[str, str]]:
    """Return localized (code, display_label) list for the 3 overview slots."""
    return [(code, tr(f"opt_{code}")) for code, _ in OVERVIEW_TILE_OPTIONS]


def _fmt_rate(bps: float) -> str:
    if bps < 1024:
        return f"{bps:.0f} {tr('unit_bps')}"
    kb = bps / 1024.0
    if kb < 1024:
        return f"{kb:.0f} {tr('unit_kbps')}"
    return f"{kb / 1024.0:.1f} {tr('unit_mbps')}"


class SystemStatsWidget(QWidget):
    """Configurable 1..3-slot overview tiles (CPU, RAM, Disk C:, Disk D:, Net ↓↑, Weather, Tasks — no Battery)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = QColor("#E2A86B")
        self._text = QColor("#F4F2EE")
        self._muted = QColor("#8C877E")
        self._slot_kinds: list[str] = ["cpu", "ram", "disk_c"]
        self._targets = [0.0, 0.0, 0.0]
        self._values = [0.0, 0.0, 0.0]
        self._labels = ["CPU", "RAM", "ДИСК C:"]
        self._right_texts = ["0%", "0%", "0%"]
        self._subs = ["", "", ""]
        self._hover_idx = -1
        self._hover_t = [0.0, 0.0, 0.0]

        # External data for "weather" and "tasks" tile kinds
        self._weather_right = "--°"
        self._weather_sub = tr("waiting_data")
        self._weather_pct = 50.0
        self._tasks_right = "0/0"
        self._tasks_sub = tr("tasks_done_sub")
        self._tasks_pct = 0.0

        # Net speed state
        self._last_net_t = 0.0
        self._last_rx = 0
        self._last_tx = 0
        self._net_rx_bps = 0.0
        self._net_tx_bps = 0.0

        self.setMouseTracking(True)
        self.setFixedHeight(54)

        self._poll = QTimer(self)
        self._poll.setInterval(1500)
        self._poll.timeout.connect(self.refresh)
        self._poll.start()

        self._glide = QTimer(self)
        self._glide.setInterval(16)
        self._glide.timeout.connect(self._tick)
        if psutil is not None:
            try:
                psutil.cpu_percent(None)
                counters = psutil.net_io_counters()
                self._last_rx = counters.bytes_recv
                self._last_tx = counters.bytes_sent
                self._last_net_t = time.monotonic()
            except Exception:
                pass
        self.refresh()

    def set_colors(self, accent: str, text_col: str, muted_col: str) -> None:
        self._accent = QColor(accent)
        self._text = QColor(text_col)
        self._muted = QColor(muted_col)
        self.update()

    def set_slot_kinds(self, kinds: list[str]) -> None:
        cleaned = [k if any(k == opt[0] for opt in OVERVIEW_TILE_OPTIONS) else "cpu" for k in kinds[:3]]
        while len(cleaned) < 3:
            cleaned.append("none")
        self._slot_kinds = cleaned
        self.refresh(force=True)

    def set_weather_summary(self, temp_str: str, sub_str: str, temp_val: float = 15.0) -> None:
        self._weather_right = temp_str
        self._weather_sub = sub_str
        self._weather_pct = max(8.0, min(100.0, (temp_val + 20.0) * 1.8))
        if "weather" in self._slot_kinds:
            self.refresh(force=True)

    def set_tasks_summary(self, right_str: str, sub_str: str, pct: float) -> None:
        self._tasks_right = right_str
        self._tasks_sub = sub_str
        self._tasks_pct = max(0.0, min(100.0, pct))
        if "tasks" in self._slot_kinds:
            self.refresh(force=True)

    def play_intro(self) -> None:
        self._values = [0.0, 0.0, 0.0]
        self._glide.start()

    def _active_indices(self) -> list[int]:
        return [i for i, k in enumerate(self._slot_kinds) if k != "none"]

    def _compute_slot(self, idx: int, kind: str) -> None:
        if kind == "cpu":
            cpu = float(psutil.cpu_percent(None)) if psutil else 0.0
            cores = psutil.cpu_count(logical=True) if psutil else 0
            self._labels[idx] = tr("slot_cpu")
            self._targets[idx] = cpu
            self._right_texts[idx] = f"{cpu:.0f}%"
            self._subs[idx] = f"{cores} {tr('threads')}"
        elif kind == "ram":
            if psutil:
                vm = psutil.virtual_memory()
                self._labels[idx] = tr("slot_ram")
                self._targets[idx] = float(vm.percent)
                self._right_texts[idx] = f"{vm.percent:.0f}%"
                self._subs[idx] = f"{vm.used / 1024**3:.1f} / {vm.total / 1024**3:.0f} GB"
        elif kind in ("disk_c", "disk_d"):
            drive = "C:\\" if kind == "disk_c" else "D:\\"
            self._labels[idx] = tr("slot_disk_c") if kind == "disk_c" else tr("slot_disk_d")
            if psutil and os.path.exists(drive):
                du = psutil.disk_usage(drive)
                self._targets[idx] = float(du.percent)
                self._right_texts[idx] = f"{du.percent:.0f}%"
                self._subs[idx] = f"{tr('free')} {du.free / 1024**3:.0f} GB"
            else:
                self._targets[idx] = 0.0
                self._right_texts[idx] = "—"
                self._subs[idx] = tr("disk_missing")
        elif kind == "net":
            self._labels[idx] = tr("slot_net")
            self._right_texts[idx] = f"↓ {_fmt_rate(self._net_rx_bps)}"
            self._subs[idx] = f"↑ {_fmt_rate(self._net_tx_bps)}"
            # Scale bar logarithmically up to 10 MB/s
            mbps = (self._net_rx_bps + self._net_tx_bps) / (1024.0 * 1024.0)
            self._targets[idx] = max(6.0, min(100.0, math.log10(1.0 + mbps * 9.0) * 50.0))
        elif kind == "weather":
            self._labels[idx] = tr("slot_weather")
            self._right_texts[idx] = self._weather_right
            self._subs[idx] = self._weather_sub
            self._targets[idx] = self._weather_pct
        elif kind == "tasks":
            self._labels[idx] = tr("slot_tasks")
            self._right_texts[idx] = self._tasks_right
            self._subs[idx] = self._tasks_sub
            self._targets[idx] = self._tasks_pct

    def refresh(self, force: bool = False) -> None:
        if not force and not self.isVisible() and self._values != [0.0, 0.0, 0.0]:
            return
        try:
            if psutil is not None and "net" in self._slot_kinds:
                now_t = time.monotonic()
                counters = psutil.net_io_counters()
                dt = max(0.2, now_t - self._last_net_t) if self._last_net_t > 0 else 1.0
                self._net_rx_bps = max(0.0, (counters.bytes_recv - self._last_rx) / dt)
                self._net_tx_bps = max(0.0, (counters.bytes_sent - self._last_tx) / dt)
                self._last_rx = counters.bytes_recv
                self._last_tx = counters.bytes_sent
                self._last_net_t = now_t

            for i, kind in enumerate(self._slot_kinds):
                if kind != "none":
                    self._compute_slot(i, kind)
        except Exception:
            return
        self._glide.start()

    def _tick(self) -> None:
        done = True
        for i in range(3):
            v, t = self._values[i], self._targets[i]
            nv = v + (t - v) * 0.14
            if abs(nv - t) < 0.05:
                nv = t
            else:
                done = False
            self._values[i] = nv
            ht = 1.0 if i == self._hover_idx else 0.0
            hh = self._hover_t[i] + (ht - self._hover_t[i]) * 0.25
            if abs(hh - ht) < 0.01:
                hh = ht
            else:
                done = False
            self._hover_t[i] = hh
        self.update()
        if done:
            self._glide.stop()

    def mouseMoveEvent(self, e) -> None:
        active = self._active_indices()
        if not active:
            return
        col_idx = max(0, min(len(active) - 1, int(e.position().x() // (self.width() / len(active)))))
        slot_idx = active[col_idx]
        if slot_idx != self._hover_idx:
            self._hover_idx = slot_idx
            self._glide.start()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover_idx = -1
        self._glide.start()
        super().leaveEvent(e)

    def paintEvent(self, event) -> None:
        active = self._active_indices()
        if not active:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = float(self.width())
        n = len(active)
        gap = 6.0
        tile_w = (w - gap * (n - 1)) / float(n)
        for pos_i, slot_i in enumerate(active):
            x = pos_i * (tile_w + gap)
            hv = self._hover_t[slot_i]
            r = QRectF(x + 0.5, 0.5, tile_w - 1.0, self.height() - 1.0)
            p.setPen(QPen(QColor(255, 255, 255, int(14 + 30 * hv)), 1.0))
            p.setBrush(QColor(255, 255, 255, int(9 + 8 * hv)))
            p.drawRoundedRect(r, 12.0, 12.0)

            val = self._values[slot_i]
            kind = self._slot_kinds[slot_i]
            right_txt = (
                f"{val:.0f}%"
                if kind in ("cpu", "ram", "disk_c", "disk_d") and self._right_texts[slot_i] != "—"
                else self._right_texts[slot_i]
            )
            p.setPen(self._muted)
            p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            p.drawText(QRectF(x + 10.0, 6.0, tile_w - 20.0, 12.0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._labels[slot_i])
            p.setPen(self._text)
            p.setFont(QFont("Segoe UI", 10 if kind == "net" else 11, QFont.Weight.DemiBold))
            p.drawText(QRectF(x + 10.0, 6.0, tile_w - 20.0, 12.0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, right_txt)

            p.setPen(self._muted)
            p.setFont(QFont("Segoe UI", 7))
            sub_elided = p.fontMetrics().elidedText(self._subs[slot_i], Qt.TextElideMode.ElideRight, int(tile_w - 20.0))
            p.drawText(QRectF(x + 10.0, 21.0, tile_w - 20.0, 12.0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, sub_elided)

            bar = QRectF(x + 10.0, 39.0, tile_w - 20.0, 5.0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 22))
            p.drawRoundedRect(bar, 2.5, 2.5)
            col = QColor(self._accent)
            if kind in ("cpu", "ram", "disk_c", "disk_d") and val >= 85:
                col = QColor("#F43F5E")
            fill = QRectF(bar.left(), bar.top(), max(5.0, bar.width() * min(100.0, val) / 100.0), 5.0)
            grad = QLinearGradient(fill.left(), 0, fill.right(), 0)
            grad.setColorAt(0.0, col.darker(135))
            grad.setColorAt(1.0, col)
            p.setBrush(grad)
            p.drawRoundedRect(fill, 2.5, 2.5)
        p.end()


class ScreenEyedropperOverlay(QWidget):
    """Full-screen transparent eyedropper that samples any pixel under the cursor."""

    color_picked = Signal(str, int, int, int)  # hex_str, r, g, b

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self._cur_color = QColor("#E2A86B")

        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._sample_cursor)

    def start_picking(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.virtualGeometry())
        self._sample_cursor()
        self.show()
        self.activateWindow()
        self._timer.start()

    def _sample_cursor(self) -> None:
        pos = QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        if screen:
            pm = screen.grabWindow(0, pos.x(), pos.y(), 1, 1)
            img = pm.toImage()
            if not img.isNull():
                self._cur_color = img.pixelColor(0, 0)
        self.update()

    def mousePressEvent(self, event) -> None:
        self._timer.stop()
        if event.button() == Qt.MouseButton.LeftButton:
            c = self._cur_color
            self.hide()
            self.color_picked.emit(c.name().upper(), c.red(), c.green(), c.blue())
            event.accept()
            return
        self.hide()
        event.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._timer.stop()
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Subtle 1/255 alpha fill so Windows routes all mouse events to this overlay
        p.fillRect(self.rect(), QColor(0, 0, 0, 2))

        local_pos = self.mapFromGlobal(QCursor.pos())
        bx = float(local_pos.x() + 18)
        by = float(local_pos.y() + 18)
        badge = QRectF(bx, by, 128.0, 36.0)

        p.setPen(QPen(QColor(255, 255, 255, 65), 1.2))
        p.setBrush(QColor(11, 11, 14, 235))
        p.drawRoundedRect(badge, 10.0, 10.0)

        p.setPen(QPen(QColor(255, 255, 255, 160), 1.2))
        p.setBrush(self._cur_color)
        p.drawEllipse(QPointF(bx + 18.0, by + 18.0), 10.0, 10.0)

        p.setPen(QColor("#F4F2EE"))
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        c = self._cur_color
        p.drawText(
            QRectF(bx + 34.0, by + 4.0, 88.0, 15.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            c.name().upper(),
        )
        p.setPen(QColor("#8C877E"))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(
            QRectF(bx + 34.0, by + 18.0, 88.0, 14.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{c.red()}, {c.green()}, {c.blue()}",
        )
        p.end()


class ScreenOcrOverlay(QWidget):
    """Full-screen region selector for Screen OCR with instant Copy / Translate action bar."""

    region_captured = Signal(object, str)  # QImage, action ("copy" | "translate")
    cancelled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._bg_pixmap = QPixmap()
        self._dragging = False
        self._has_selection = False
        self._start_pt = QPoint()
        self._end_pt = QPoint()
        self._sel_rect = QRect()

        self._action_bar = QWidget(self)
        self._action_bar.setStyleSheet(
            f"QWidget {{ background-color: rgba(11, 11, 14, 240); "
            f"border: 1px solid {Theme.accent}; border-radius: 11px; }}"
        )
        ab_lay = QHBoxLayout(self._action_bar)
        ab_lay.setContentsMargins(6, 4, 6, 4)
        ab_lay.setSpacing(6)

        self.copy_btn = PillButton(tr("copy"), icon_kind="copy", icon_size=12)
        self.copy_btn.setFixedHeight(26)
        self.copy_btn.clicked.connect(lambda: self._emit_region("copy"))

        self.translate_btn = PillButton(
            tr("translate"), icon_kind="translate", variant="AccentBtn", icon_size=12
        )
        self.translate_btn.setFixedHeight(26)
        self.translate_btn.clicked.connect(lambda: self._emit_region("translate"))

        self.cancel_btn = PillButton("", icon_kind="close", variant="IconBtn", icon_size=11)
        self.cancel_btn.setFixedSize(24, 24)
        self.cancel_btn.clicked.connect(self._cancel)

        ab_lay.addWidget(self.copy_btn)
        ab_lay.addWidget(self.translate_btn)
        ab_lay.addWidget(self.cancel_btn)
        self._action_bar.hide()

    def start_capture(self) -> None:
        self.copy_btn.setText(tr("copy"))
        self.translate_btn.setText(tr("translate"))
        self._action_bar.setStyleSheet(
            f"QWidget {{ background-color: rgba(11, 11, 14, 240); "
            f"border: 1px solid {Theme.accent}; border-radius: 11px; }}"
        )
        screen = QGuiApplication.primaryScreen()
        if screen:
            vg = screen.virtualGeometry()
            self._bg_pixmap = screen.grabWindow(0, vg.x(), vg.y(), vg.width(), vg.height())
            self.setGeometry(vg)
        else:
            self._bg_pixmap = QPixmap()
            self.resize(1280, 720)

        self._dragging = False
        self._has_selection = False
        self._sel_rect = QRect()
        self._action_bar.hide()
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self.update()

    def _current_rect(self) -> QRect:
        return QRect(self._start_pt, self._end_pt).normalized().intersected(self.rect())

    def _position_action_bar(self) -> None:
        self._action_bar.adjustSize()
        bw = self._action_bar.sizeHint().width()
        bh = self._action_bar.sizeHint().height()
        r = self._sel_rect
        x = max(8, min(self.width() - bw - 8, r.right() - bw + 1))
        y = r.bottom() + 8
        if y + bh + 8 > self.height():
            y = max(8, r.top() - bh - 8)
        self._action_bar.setGeometry(x, y, bw, bh)
        self._action_bar.show()
        self._action_bar.raise_()

    def _crop_selection_image(self) -> QImage:
        r = self._sel_rect
        if r.width() < 2 or r.height() < 2:
            return QImage()
        if not self._bg_pixmap.isNull():
            dpr = self._bg_pixmap.devicePixelRatio() or 1.0
            phys = QRect(
                round(r.x() * dpr),
                round(r.y() * dpr),
                max(1, round(r.width() * dpr)),
                max(1, round(r.height() * dpr)),
            )
            return self._bg_pixmap.copy(phys).toImage()
        img = QImage(r.width(), r.height(), QImage.Format.Format_RGBA8888)
        img.fill(QColor(255, 255, 255))
        return img

    def _emit_region(self, action: str) -> None:
        if not self._has_selection:
            return
        img = self._crop_selection_image()
        self._action_bar.hide()
        self.hide()
        if not img.isNull():
            self.region_captured.emit(img, action)
        else:
            self.cancelled.emit()

    def _cancel(self) -> None:
        self._action_bar.hide()
        self.hide()
        self.cancelled.emit()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._cancel()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._action_bar.hide()
            self._dragging = True
            self._has_selection = False
            self._start_pt = event.position().toPoint()
            self._end_pt = self._start_pt
            self._sel_rect = QRect()
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self._end_pt = event.position().toPoint()
            self._sel_rect = self._current_rect()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self._end_pt = event.position().toPoint()
            self._sel_rect = self._current_rect()
            if self._sel_rect.width() >= 12 and self._sel_rect.height() >= 8:
                self._has_selection = True
                self._position_action_bar()
            else:
                self._has_selection = False
                self._sel_rect = QRect()
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
            event.accept()
            return
        if self._has_selection and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._emit_region("translate")
            event.accept()
            return
        if (
            self._has_selection
            and (event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            and event.key() == Qt.Key.Key_C
        ):
            self._emit_region("copy")
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._bg_pixmap.isNull():
            p.drawPixmap(self.rect(), self._bg_pixmap)

        outer = QPainterPath()
        outer.addRect(QRectF(self.rect()))
        r = self._sel_rect
        if r.width() > 1 and r.height() > 1:
            inner = QPainterPath()
            inner.addRect(QRectF(r))
            outer = outer.subtracted(inner)
        p.fillPath(outer, QColor(8, 8, 12, 135))

        if r.width() > 1 and r.height() > 1:
            accent = QColor(Theme.accent)
            p.setPen(QPen(accent, 2.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5))

            dim_txt = f"{r.width()} × {r.height()}"
            badge_y = max(6.0, float(r.top()) - 24.0)
            badge = QRectF(float(r.left()), badge_y, 76.0, 18.0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(11, 11, 14, 215))
            p.drawRoundedRect(badge, 5.0, 5.0)
            p.setPen(QColor("#F4F2EE"))
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
            p.drawText(badge, Qt.AlignmentFlag.AlignCenter, dim_txt)
        else:
            hint = tr("ocr_hint")
            pill_w = min(float(self.width() - 32), 420.0)
            pill = QRectF((self.width() - pill_w) / 2.0, 20.0, pill_w, 30.0)
            p.setPen(QPen(QColor(Theme.accent), 1.0))
            p.setBrush(QColor(11, 11, 14, 225))
            p.drawRoundedRect(pill, 12.0, 12.0)
            p.setPen(QColor("#F4F2EE"))
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, hint)
        p.end()


class WindCompassWidget(QWidget):
    """Open-space circular wind compass with directional arrow + speed readout."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._speed = 0.0
        self._deg = 0.0
        self._dir_label = tr("dir_N")
        self._unit = tr("wind_ms")
        self._accent = QColor("#E2A86B")
        self._text = QColor("#F4F2EE")
        self._muted = QColor("#8C877E")
        self.setMinimumSize(145, 96)

    def set_data(self, speed: float, deg: float, dir_label: str, unit: str | None = None) -> None:
        self._speed = speed
        self._deg = deg
        self._dir_label = dir_label
        self._unit = unit or tr("wind_ms")
        self.update()

    def set_colors(self, accent: str, text_col: str, muted_col: str) -> None:
        self._accent = QColor(accent)
        self._text = QColor(text_col)
        self._muted = QColor(muted_col)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.setPen(self._muted)
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.drawText(QRectF(4, 2, 130, 14), Qt.AlignmentFlag.AlignLeft, tr("wind"))

        cx, cy, r = 34.0, 56.0, 24.0
        p.setPen(QPen(QColor(255, 255, 255, 35), 1.3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r, r)

        for i in range(8):
            ang = i * math.pi / 4.0
            r1 = r - 3.5 if i % 2 == 0 else r - 2.0
            p.drawLine(
                QPointF(cx + math.cos(ang) * r1, cy + math.sin(ang) * r1),
                QPointF(cx + math.cos(ang) * r, cy + math.sin(ang) * r),
            )

        rad = math.radians(self._deg - 90.0)
        tip = QPointF(cx + math.cos(rad) * (r - 5.0), cy + math.sin(rad) * (r - 5.0))
        tail = QPointF(cx - math.cos(rad) * (r - 7.0), cy - math.sin(rad) * (r - 7.0))
        p.setPen(QPen(self._accent, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(tail, tip)
        p.setBrush(self._accent)
        p.drawEllipse(tip, 2.5, 2.5)

        p.setPen(self._text)
        p.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        p.drawText(
            QRectF(68, 34, 85, 22),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{self._speed:.1f} {self._unit}",
        )
        p.setPen(self._muted)
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(
            QRectF(68, 56, 85, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{tr('wind_dir')}: {self._dir_label}",
        )
        p.end()


class HumidityBarWidget(QWidget):
    """Open-space humidity readout with smooth horizontal progress bar and comfort level."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._humidity = 55
        self._comfort = tr("hum_comfort")
        self._accent = QColor("#E2A86B")
        self._text = QColor("#F4F2EE")
        self._muted = QColor("#8C877E")
        self.setMinimumSize(145, 96)

    def set_data(self, humidity: int, comfort: str) -> None:
        self._humidity = max(0, min(100, humidity))
        self._comfort = comfort
        self.update()

    def set_colors(self, accent: str, text_col: str, muted_col: str) -> None:
        self._accent = QColor(accent)
        self._text = QColor(text_col)
        self._muted = QColor(muted_col)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.setPen(self._muted)
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.drawText(QRectF(4, 2, 130, 14), Qt.AlignmentFlag.AlignLeft, tr("humidity"))

        p.setPen(self._text)
        p.setFont(QFont("Segoe UI", 18, QFont.Weight.DemiBold))
        p.drawText(QRectF(4, 20, 120, 28), Qt.AlignmentFlag.AlignLeft, f"{self._humidity}%")

        bar_w = float(self.width() - 16)
        bar_rect = QRectF(4.0, 56.0, bar_w, 5.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 28))
        p.drawRoundedRect(bar_rect, 2.5, 2.5)

        fill_w = max(6.0, bar_w * (self._humidity / 100.0))
        p.setBrush(self._accent)
        p.drawRoundedRect(QRectF(4.0, 56.0, fill_w, 5.0), 2.5, 2.5)

        p.setPen(self._muted)
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(QRectF(4, 66, 130, 18), Qt.AlignmentFlag.AlignLeft, self._comfort)
        p.end()


class PressureArcWidget(QWidget):
    """Open-space semi-circular pressure gauge in mmHg."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mmhg = 760
        self._accent = QColor("#E2A86B")
        self._text = QColor("#F4F2EE")
        self._muted = QColor("#8C877E")
        self.setMinimumSize(145, 96)

    def set_data(self, mmhg: int) -> None:
        self._mmhg = mmhg
        self.update()

    def set_colors(self, accent: str, text_col: str, muted_col: str) -> None:
        self._accent = QColor(accent)
        self._text = QColor(text_col)
        self._muted = QColor(muted_col)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.setPen(self._muted)
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.drawText(QRectF(4, 2, 130, 14), Qt.AlignmentFlag.AlignLeft, tr("pressure"))

        arc_rect = QRectF(18.0, 24.0, 68.0, 60.0)
        p.setPen(QPen(QColor(255, 255, 255, 30), 4.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(arc_rect, -15 * 16, 210 * 16)

        ratio = max(0.05, min(1.0, (self._mmhg - 720.0) / 60.0))
        span = int(-210 * 16 * ratio)
        p.setPen(QPen(self._accent, 4.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(arc_rect, 195 * 16, span)

        p.setPen(self._text)
        p.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        p.drawText(arc_rect, Qt.AlignmentFlag.AlignCenter, str(self._mmhg))

        p.setPen(self._muted)
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(
            QRectF(12.0, 68.0, 80.0, 16.0),
            Qt.AlignmentFlag.AlignCenter,
            tr("mmhg"),
        )
        p.end()


class TimerRingWidget(QWidget):
    """Circular countdown progress ring for the Focus/Pomodoro timer."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._remaining = 25 * 60
        self._total = 25 * 60
        self._accent = QColor("#E2A86B")
        self._text = QColor("#F4F2EE")
        self.setFixedSize(94, 94)

    def set_time(self, remaining_sec: int, total_sec: int) -> None:
        self._remaining = max(0, remaining_sec)
        self._total = max(1, total_sec)
        self.update()

    def set_colors(self, accent: str, text_col: str) -> None:
        self._accent = QColor(accent)
        self._text = QColor(text_col)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(6.0, 6.0, self.width() - 12.0, self.height() - 12.0)
        p.setPen(QPen(QColor(255, 255, 255, 24), 4.0))
        p.drawEllipse(rect)

        ratio = self._remaining / float(self._total)
        p.setPen(QPen(self._accent, 4.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(rect, 90 * 16, int(-360 * 16 * ratio))

        mins, secs = divmod(self._remaining, 60)
        p.setPen(self._text)
        p.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{mins:02d}:{secs:02d}")
        p.end()
