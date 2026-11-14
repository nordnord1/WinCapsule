"""Animated building blocks (v4): springy buttons, glass tiles, accordion sections, loading dots."""

from __future__ import annotations

import math
import weakref

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.icons import render_vector_pixmap

QWIDGETSIZE_MAX = 16777215


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
        round(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def _with_alpha(c: QColor, alpha: float) -> QColor:
    out = QColor(c)
    out.setAlpha(max(0, min(255, int(alpha))))
    return out


class Theme:
    """Global live theme shared by all animated widgets."""

    accent = QColor("#E2A86B")
    text = QColor("#F4F2EE")
    muted = QColor("#8C877E")
    bg = QColor("#0B0B0E")
    _listeners: "weakref.WeakSet[QWidget]" = weakref.WeakSet()

    @classmethod
    def set(cls, accent: str, text: str, muted: str, bg: str = "#0B0B0E") -> None:
        cls.accent = QColor(accent)
        cls.text = QColor(text)
        cls.muted = QColor(muted)
        cls.bg = QColor(bg)
        _pix_cache.clear()
        for w in list(cls._listeners):
            try:
                if hasattr(w, "on_theme_changed"):
                    w.on_theme_changed()
                w.update()
            except RuntimeError:
                pass

    @classmethod
    def register(cls, w: QWidget) -> None:
        cls._listeners.add(w)


_pix_cache: dict[tuple, object] = {}


def themed_pixmap(kind: str, size: int, color: QColor, accent: QColor):
    key = (kind, size, color.name(QColor.NameFormat.HexArgb), accent.name())
    pm = _pix_cache.get(key)
    if pm is None:
        pm = render_vector_pixmap(kind, size, color.name(), accent.name())
        _pix_cache[key] = pm
    return pm


def make_anim(parent, duration: int, curve=QEasingCurve.Type.OutCubic, on_value=None) -> QVariantAnimation:
    anim = QVariantAnimation(parent)
    anim.setDuration(duration)
    anim.setEasingCurve(curve)
    if on_value is not None:
        anim.valueChanged.connect(on_value)
    return anim


def animate_to(anim: QVariantAnimation, start: float, end: float) -> None:
    anim.stop()
    anim.setStartValue(float(start))
    anim.setEndValue(float(end))
    anim.start()


# ───────────────────────────────────────────────────────────────────────
class PillButton(QPushButton):
    """
    QPushButton with self-painted, animated states:
    hover glow (180ms), springy press squish, animated 'active' highlight.
    Variants via objectName: default, 'IconBtn', 'AccentBtn', 'GhostBtn'.
    """

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
        icon_kind: str | None = None,
        variant: str | None = None,
        icon_size: int = 14,
    ) -> None:
        super().__init__(text, parent)
        if variant:
            self.setObjectName(variant)
        self._icon_kind = icon_kind
        self._icon_px = icon_size
        self._hover_t = 0.0
        self._press_t = 0.0
        self._active_t = 0.0
        self._align_left = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        self._hover_anim = make_anim(self, 190, QEasingCurve.Type.OutCubic, self._set_hover)
        self._press_anim = make_anim(self, 260, QEasingCurve.Type.OutBack, self._set_press)
        self._active_anim = make_anim(self, 240, QEasingCurve.Type.OutCubic, self._set_active)
        Theme.register(self)

    # API ---------------------------------------------------------------
    def set_icon_kind(self, kind: str | None) -> None:
        self._icon_kind = kind
        self.update()

    def set_align_left(self, on: bool) -> None:
        self._align_left = on
        self.update()

    def set_active(self, on: bool) -> None:
        self.setProperty("active", "true" if on else "false")
        animate_to(self._active_anim, self._active_t, 1.0 if on else 0.0)

    def is_active(self) -> bool:
        return self.property("active") == "true"

    # anim setters -------------------------------------------------------
    def _set_hover(self, v) -> None:
        self._hover_t = float(v)
        self.update()

    def _set_press(self, v) -> None:
        self._press_t = float(v)
        self.update()

    def _set_active(self, v) -> None:
        self._active_t = float(v)
        self.update()

    # events -------------------------------------------------------------
    def enterEvent(self, e) -> None:
        animate_to(self._hover_anim, self._hover_t, 1.0)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        animate_to(self._hover_anim, self._hover_t, 0.0)
        super().leaveEvent(e)

    def mousePressEvent(self, e) -> None:
        self._press_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._press_anim.setDuration(90)
        animate_to(self._press_anim, self._press_t, 1.0)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        self._press_anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._press_anim.setDuration(320)
        animate_to(self._press_anim, self._press_t, 0.0)
        super().mouseReleaseEvent(e)

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        txt = self.text()
        has_icon = bool(self._icon_kind) or not self.icon().isNull()
        if has_icon and not txt:
            side = max(24, self._icon_px + 10)
            return QSize(side, side)
        w = 20
        if has_icon:
            w += self._icon_px + (6 if txt else 0)
        if txt:
            w += fm.horizontalAdvance(txt)
        h = max(24, fm.height() + 10)
        return QSize(max(26, w), h)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    # painting -----------------------------------------------------------
    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if not self.isEnabled():
            p.setOpacity(0.4)

        variant = self.objectName()
        h, pr = self._hover_t, self._press_t
        running = self._active_anim.state() == QVariantAnimation.State.Running
        act = self._active_t if running else (1.0 if self.is_active() else 0.0)

        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        scale = 1.0 - 0.07 * pr
        c = rect.center()
        p.translate(c)
        p.scale(scale, scale)
        p.translate(-c)

        accent, text = Theme.accent, Theme.text
        radius = min(10.0, rect.height() / 2.0)
        fg = QColor(text)

        if variant == "AccentBtn":
            base = _mix(accent, QColor(255, 255, 255), 0.16 * h)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(base)
            p.drawRoundedRect(rect, radius, radius)
            # inner sheen
            p.setBrush(QColor(255, 255, 255, int(18 + 22 * h)))
            p.drawRoundedRect(QRectF(rect.left(), rect.top(), rect.width(), rect.height() * 0.48), radius, radius)
            fg = QColor("#0B0B0E")
        elif variant == "IconBtn":
            radius = min(rect.height(), rect.width()) / 2.0 if not self.text() else radius
            bg_a = 22 * h + 26 * act + 18 * pr
            if bg_a > 0.5:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(_mix(QColor(255, 255, 255, int(bg_a)), _with_alpha(accent, bg_a * 1.2), act))
                p.drawRoundedRect(rect, radius, radius)
            fg = _mix(_with_alpha(text, 215), text, h)
            if act > 0:
                fg = _mix(fg, accent, act)
        elif variant == "GhostBtn":
            bg_a = 14 * h + 30 * act
            p.setPen(QPen(_with_alpha(accent, 60 + 140 * max(h, act)), 1.0))
            p.setBrush(_with_alpha(accent, bg_a))
            p.drawRoundedRect(rect, radius, radius)
            fg = _mix(text, accent, 0.55 + 0.45 * h)
        else:
            bg = QColor(255, 255, 255, int(12 + 12 * h + 10 * act))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(rect, radius, radius)
            if act > 0:
                p.setBrush(_with_alpha(accent, 34 * act))
                p.drawRoundedRect(rect, radius, radius)
            border = _mix(QColor(255, 255, 255, 20), _with_alpha(accent, 230), max(h * 0.85, act))
            p.setPen(QPen(border, 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, radius, radius)

        # content
        font = self.font()
        p.setFont(font)
        fm = p.fontMetrics()
        txt = self.text()
        ip = self._icon_px
        pm = None
        if self._icon_kind:
            icon_fg = fg if variant != "AccentBtn" else QColor("#0B0B0E")
            icon_ac = accent if variant != "AccentBtn" else QColor("#0B0B0E")
            pm = themed_pixmap(self._icon_kind, ip, icon_fg, icon_ac)
        elif not self.icon().isNull():
            pm = self.icon().pixmap(self.iconSize())
            ip = self.iconSize().width()

        tw = fm.horizontalAdvance(txt) if txt else 0
        gap = 6 if (pm is not None and txt) else 0
        total = (ip if pm is not None else 0) + gap + tw
        if self._align_left:
            x = rect.left() + 9.0
        else:
            x = rect.center().x() - total / 2.0
        cy = rect.center().y()
        if pm is not None:
            p.drawPixmap(QPointF(x, cy - ip / 2.0), pm)
            x += ip + gap
        if txt:
            p.setPen(fg)
            p.drawText(
                QRectF(x, rect.top(), rect.right() - x + 2, rect.height()),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                txt,
            )
        p.end()


# ───────────────────────────────────────────────────────────────────────
class GlassTile(QWidget):
    """Soft rounded glass card that brightens smoothly on hover."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None, radius: float = 14.0, clickable: bool = False) -> None:
        super().__init__(parent)
        self._radius = radius
        self._hover_t = 0.0
        self._flash_t = 0.0
        self._clickable = clickable
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover_anim = make_anim(self, 240, QEasingCurve.Type.OutCubic, self._set_hover)
        self._flash_anim = make_anim(self, 520, QEasingCurve.Type.OutCubic, self._set_flash)
        Theme.register(self)

    def _set_hover(self, v) -> None:
        self._hover_t = float(v)
        self.update()

    def _set_flash(self, v) -> None:
        self._flash_t = float(v)
        self.update()

    def flash(self) -> None:
        """Short accent pulse (used as feedback after an action)."""
        animate_to(self._flash_anim, 1.0, 0.0)

    def enterEvent(self, e) -> None:
        animate_to(self._hover_anim, self._hover_t, 1.0)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        animate_to(self._hover_anim, self._hover_t, 0.0)
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        if self._clickable and e.button() == Qt.MouseButton.LeftButton:
            self.flash()
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        h = self._hover_t
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, int(9 + 7 * h)))
        p.drawRoundedRect(r, self._radius, self._radius)
        if self._flash_t > 0.01:
            p.setBrush(_with_alpha(Theme.accent, 50 * self._flash_t))
            p.drawRoundedRect(r, self._radius, self._radius)
        border = _mix(QColor(255, 255, 255, 14), _with_alpha(Theme.accent, 110), h * 0.6 + self._flash_t * 0.4)
        p.setPen(QPen(border, 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, self._radius, self._radius)
        p.end()


# ───────────────────────────────────────────────────────────────────────
class _SectionHeader(QWidget):
    clicked = Signal()

    def __init__(self, title: str, subtitle: str, icon_kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title
        self._subtitle = subtitle
        self._icon = icon_kind
        self._hover_t = 0.0
        self.open_t = 0.0
        self.swatches: list[str] = []
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover_anim = make_anim(self, 200, QEasingCurve.Type.OutCubic, self._set_hover)

    def set_title(self, text: str) -> None:
        self._title = text
        self.update()

    def set_subtitle(self, text: str) -> None:
        self._subtitle = text
        self.update()

    def _set_hover(self, v) -> None:
        self._hover_t = float(v)
        self.update()

    def enterEvent(self, e) -> None:
        animate_to(self._hover_anim, self._hover_t, 1.0)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        animate_to(self._hover_anim, self._hover_t, 0.0)
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = float(self.width()), float(self.height())
        t, hv = self.open_t, self._hover_t

        # icon bubble
        bubble = QRectF(10.0, (h - 26.0) / 2.0, 26.0, 26.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_with_alpha(Theme.accent, 26 + 30 * max(t, hv)))
        p.drawRoundedRect(bubble, 8.0, 8.0)
        pm = themed_pixmap(self._icon, 15, Theme.text, Theme.accent)
        p.drawPixmap(QPointF(bubble.center().x() - 7.5, bubble.center().y() - 7.5), pm)

        # title + subtitle
        f = QFont("Segoe UI", 9, QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(_mix(Theme.text, Theme.accent, t * 0.35))
        p.drawText(QRectF(46.0, 4.0, w - 140.0, 18.0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._title)
        if self._subtitle:
            p.setFont(QFont("Segoe UI", 8))
            p.setPen(Theme.muted)
            p.drawText(QRectF(46.0, 20.0, w - 140.0, 15.0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, p.fontMetrics().elidedText(self._subtitle, Qt.TextElideMode.ElideRight, int(w - 140)))

        # summary swatches
        x = w - 40.0
        for col in reversed(self.swatches):
            x -= 16.0
            p.setPen(QPen(QColor(255, 255, 255, 70), 1.0))
            p.setBrush(QColor(col))
            p.drawEllipse(QPointF(x + 6.0, h / 2.0), 6.0, 6.0)

        # rotating chevron
        p.save()
        p.translate(w - 22.0, h / 2.0)
        p.rotate(180.0 * t)
        p.setPen(QPen(_mix(Theme.muted, Theme.accent, max(t, hv)), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawLine(QPointF(-4.5, -2.0), QPointF(0.0, 2.5))
        p.drawLine(QPointF(0.0, 2.5), QPointF(4.5, -2.0))
        p.restore()
        p.end()


class CollapsibleSection(QWidget):
    """Accordion card: click the header and the body slides out (height + fade)."""

    expanded_changed = Signal(bool)

    def __init__(self, title: str, subtitle: str = "", icon_kind: str = "sliders", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._t = 0.0
        self._expanded = False
        self._target_h = 0
        self._hover_t = 0.0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.header = _SectionHeader(title, subtitle, icon_kind)
        self.header.clicked.connect(self.toggle)
        lay.addWidget(self.header)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(14, 2, 14, 12)
        self.body_layout.setSpacing(8)
        self.body.setMaximumHeight(0)
        self._body_fx = QGraphicsOpacityEffect(self.body)
        self._body_fx.setOpacity(0.0)
        self.body.setGraphicsEffect(self._body_fx)
        self.body.setVisible(False)
        lay.addWidget(self.body)

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._anim = make_anim(self, 300, QEasingCurve.Type.OutCubic, self._on_step)
        self._anim.finished.connect(self._on_finished)
        Theme.register(self)

    def is_expanded(self) -> bool:
        return self._expanded

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def set_expanded(self, on: bool, animate: bool = True) -> None:
        if on == self._expanded and (animate or abs(self._t - (1.0 if on else 0.0)) < 1e-3):
            return
        self._expanded = on
        self.body.setVisible(True)
        self._target_h = max(1, self.body.sizeHint().height())
        if not animate:
            self._anim.stop()
            self._on_step(1.0 if on else 0.0)
            self._on_finished()
        else:
            self._anim.setEasingCurve(QEasingCurve.Type.OutCubic if on else QEasingCurve.Type.InOutCubic)
            self._anim.setDuration(320 if on else 240)
            animate_to(self._anim, self._t, 1.0 if on else 0.0)
        self.expanded_changed.emit(on)

    def _on_step(self, v) -> None:
        self._t = float(v)
        self.body.setMaximumHeight(int(self._target_h * self._t))
        self._body_fx.setOpacity(max(0.0, min(1.0, (self._t - 0.15) / 0.85)))
        self.header.open_t = self._t
        self.header.update()
        self.update()

    def _on_finished(self) -> None:
        if self._expanded:
            self.body.setMaximumHeight(QWIDGETSIZE_MAX)
        else:
            self.body.setMaximumHeight(0)
            self.body.setVisible(False)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        t = self._t
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, int(8 + 8 * t)))
        p.drawRoundedRect(r, 13.0, 13.0)
        p.setPen(QPen(_mix(QColor(255, 255, 255, 14), _with_alpha(Theme.accent, 120), t), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 13.0, 13.0)
        p.end()


# ───────────────────────────────────────────────────────────────────────
class LoadingDots(QWidget):
    """Three bouncing dots shown while a background request is running."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._phase = 0.0
        self.setFixedSize(26, 12)
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)
        self.setVisible(False)

    def start(self) -> None:
        self.setVisible(True)
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.setVisible(False)

    def _tick(self) -> None:
        self._phase += 0.22
        self.update()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            k = 0.5 + 0.5 * math.sin(self._phase - i * 0.9)
            p.setBrush(_with_alpha(Theme.accent, 90 + 165 * k))
            p.drawEllipse(QPointF(5.0 + i * 8.0, 6.0 - 2.5 * k), 2.4, 2.4)
        p.end()


# ───────────────────────────────────────────────────────────────────────
def slide_fade_in(widget: QWidget, dx: int = 0, dy: int = 10, duration: int = 280, delay: int = 0) -> None:
    """Fade + slide a child widget into its current position (one-shot)."""

    def _run() -> None:
        end = widget.pos()
        fx = widget.graphicsEffect()
        if not isinstance(fx, QGraphicsOpacityEffect):
            fx = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(fx)
        fx.setOpacity(0.0)
        pos_anim = QPropertyAnimation(widget, b"pos", widget)
        pos_anim.setDuration(duration)
        pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        pos_anim.setStartValue(end + QPoint(dx, dy))
        pos_anim.setEndValue(end)
        op_anim = QPropertyAnimation(fx, b"opacity", widget)
        op_anim.setDuration(duration)
        op_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        op_anim.setStartValue(0.0)
        op_anim.setEndValue(1.0)

        def _cleanup() -> None:
            widget.setGraphicsEffect(None)

        op_anim.finished.connect(_cleanup)
        pos_anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        op_anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    if delay > 0:
        QTimer.singleShot(delay, _run)
    else:
        _run()


def hbox(*widgets, spacing: int = 6, margins=(0, 0, 0, 0), stretch_at: int | None = None) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for i, w in enumerate(widgets):
        if stretch_at is not None and i == stretch_at:
            lay.addStretch()
        if w is None:
            lay.addStretch()
        elif isinstance(w, QWidget):
            lay.addWidget(w)
        else:
            lay.addLayout(w)
    return lay
