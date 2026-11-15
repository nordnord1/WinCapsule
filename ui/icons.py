"""Pure vector icon renderer, static PNG mascot loader, and animated waveform widget."""

from __future__ import annotations

import math
import os
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget


def load_mascot_pixmap(path: str, size: int = 24, accent: str = "#E2A86B") -> QPixmap:
    """
    Load a user-provided static PNG/WEBP character image scaled smoothly to `size`,
    or render a sleek static crystal/avatar emblem when no file path is set.
    """
    dpr = 2.0
    target_px = int(size * dpr)
    if path and os.path.isfile(path):
        src = QPixmap(path)
        if not src.isNull():
            scaled = src.scaled(
                target_px,
                target_px,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            scaled.setDevicePixelRatio(dpr)
            return scaled

    # Sleek static geometric character emblem when no custom PNG is selected yet
    pm = QPixmap(target_px, target_px)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    s = float(size)
    cx, cy = s / 2.0, s / 2.0
    ac = QColor(accent)

    # Outer soft halo
    halo = QColor(ac)
    halo.setAlpha(42)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(halo)
    p.drawRoundedRect(QRectF(1.5, 1.5, s - 3.0, s - 3.0), s * 0.34, s * 0.34)

    # Inner diamond/crystal character silhouette
    diamond = QPainterPath()
    diamond.moveTo(cx, s * 0.18)
    diamond.lineTo(s * 0.80, cy)
    diamond.lineTo(cx, s * 0.82)
    diamond.lineTo(s * 0.20, cy)
    diamond.closeSubpath()
    p.setPen(QPen(ac, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    in_fill = QColor(ac)
    in_fill.setAlpha(95)
    p.setBrush(in_fill)
    p.drawPath(diamond)

    p.setBrush(QColor("#F4F2EE"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(cx, cy), 2.0, 2.0)
    p.end()
    return pm


def render_vector_pixmap(
    kind: str,
    size: int = 18,
    color: str = "#F4F2EE",
    accent: str = "#E2A86B",
) -> QPixmap:
    """Draw a crisp anti-aliased vector icon of the given kind."""
    dpr = 2.0
    px = int(size * dpr)
    pm = QPixmap(px, px)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    c = QColor(color)
    ac = QColor(accent)
    pen = QPen(
        c,
        1.65,
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    s = float(size)
    cx, cy = s / 2.0, s / 2.0

    if kind == "cycle_tab":
        # Double-chevron / cycle forward icon for the blue-boxed tab switcher button
        p.setPen(
            QPen(
                ac,
                1.75,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        path = QPainterPath()
        path.moveTo(s * 0.26, s * 0.26)
        path.lineTo(s * 0.52, cy)
        path.lineTo(s * 0.26, s * 0.74)
        path.moveTo(s * 0.50, s * 0.26)
        path.lineTo(s * 0.76, cy)
        path.lineTo(s * 0.50, s * 0.74)
        p.drawPath(path)

    elif kind == "pipette":
        # Eyedropper / Color picker vector icon
        p.setPen(
            QPen(
                ac,
                1.65,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        p.drawLine(QPointF(s * 0.22, s * 0.78), QPointF(s * 0.56, s * 0.44))
        p.drawLine(QPointF(s * 0.46, s * 0.34), QPointF(s * 0.66, s * 0.54))
        p.setBrush(ac)
        p.drawEllipse(QPointF(s * 0.68, s * 0.32), s * 0.12, s * 0.12)

    elif kind == "hide":
        path = QPainterPath()
        path.moveTo(s * 0.15, cy)
        path.quadTo(cx, s * 0.22, s * 0.85, cy)
        path.quadTo(cx, s * 0.78, s * 0.15, cy)
        p.drawPath(path)
        p.drawLine(QPointF(s * 0.24, s * 0.76), QPointF(s * 0.76, s * 0.24))

    elif kind == "collapse":
        path = QPainterPath()
        path.moveTo(s * 0.38, s * 0.26)
        path.lineTo(s * 0.64, cy)
        path.lineTo(s * 0.38, s * 0.74)
        p.drawPath(path)

    elif kind == "back":
        path = QPainterPath()
        path.moveTo(s * 0.62, s * 0.24)
        path.lineTo(s * 0.34, cy)
        path.lineTo(s * 0.62, s * 0.76)
        p.drawPath(path)

    elif kind == "refresh":
        rect = QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.56)
        p.drawArc(rect, 35 * 16, 285 * 16)
        path = QPainterPath()
        path.moveTo(s * 0.62, s * 0.18)
        path.lineTo(s * 0.78, s * 0.28)
        path.lineTo(s * 0.64, s * 0.38)
        p.drawPath(path)

    elif kind == "play":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        path = QPainterPath()
        path.moveTo(s * 0.32, s * 0.22)
        path.lineTo(s * 0.76, cy)
        path.lineTo(s * 0.32, s * 0.78)
        path.closeSubpath()
        p.drawPath(path)

    elif kind == "pause":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(s * 0.28, s * 0.22, s * 0.14, s * 0.56), 1.8, 1.8)
        p.drawRoundedRect(QRectF(s * 0.58, s * 0.22, s * 0.14, s * 0.56), 1.8, 1.8)

    elif kind == "prev":
        p.drawLine(QPointF(s * 0.26, s * 0.26), QPointF(s * 0.26, s * 0.74))
        path = QPainterPath()
        path.moveTo(s * 0.74, s * 0.26)
        path.lineTo(s * 0.38, cy)
        path.lineTo(s * 0.74, s * 0.74)
        path.closeSubpath()
        p.setBrush(c)
        p.drawPath(path)

    elif kind == "next":
        p.drawLine(QPointF(s * 0.74, s * 0.26), QPointF(s * 0.74, s * 0.74))
        path = QPainterPath()
        path.moveTo(s * 0.26, s * 0.26)
        path.lineTo(s * 0.62, cy)
        path.lineTo(s * 0.26, s * 0.74)
        path.closeSubpath()
        p.setBrush(c)
        p.drawPath(path)

    elif kind == "music_note":
        p.drawLine(QPointF(s * 0.42, s * 0.68), QPointF(s * 0.42, s * 0.25))
        p.drawLine(QPointF(s * 0.76, s * 0.60), QPointF(s * 0.76, s * 0.18))
        p.drawLine(QPointF(s * 0.42, s * 0.25), QPointF(s * 0.76, s * 0.18))
        p.setBrush(ac)
        p.drawEllipse(QPointF(s * 0.33, s * 0.68), 2.8, 2.2)
        p.drawEllipse(QPointF(s * 0.67, s * 0.60), 2.8, 2.2)

    elif kind in ("speaker", "speaker_mute"):
        path = QPainterPath()
        path.moveTo(s * 0.20, s * 0.40)
        path.lineTo(s * 0.34, s * 0.40)
        path.lineTo(s * 0.52, s * 0.24)
        path.lineTo(s * 0.52, s * 0.76)
        path.lineTo(s * 0.34, s * 0.60)
        path.lineTo(s * 0.20, s * 0.60)
        path.closeSubpath()
        p.drawPath(path)
        if kind == "speaker":
            p.drawArc(QRectF(s * 0.44, s * 0.32, s * 0.26, s * 0.36), -45 * 16, 90 * 16)
        else:
            p.setPen(QPen(QColor("#F43F5E"), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(s * 0.62, s * 0.38), QPointF(s * 0.80, s * 0.62))
            p.drawLine(QPointF(s * 0.80, s * 0.38), QPointF(s * 0.62, s * 0.62))

    elif kind == "clipboard":
        p.drawRoundedRect(QRectF(s * 0.25, s * 0.24, s * 0.50, s * 0.58), 2.5, 2.5)
        p.setBrush(QColor("#141821"))
        p.drawRoundedRect(QRectF(s * 0.38, s * 0.16, s * 0.24, s * 0.14), 1.5, 1.5)

    elif kind == "trash":
        p.drawLine(QPointF(s * 0.22, s * 0.30), QPointF(s * 0.78, s * 0.30))
        p.drawRoundedRect(QRectF(s * 0.30, s * 0.30, s * 0.40, s * 0.50), 2.0, 2.0)
        p.drawLine(QPointF(s * 0.40, s * 0.20), QPointF(s * 0.60, s * 0.20))

    elif kind == "capslock":
        path = QPainterPath()
        path.moveTo(cx, s * 0.16)
        path.lineTo(s * 0.80, s * 0.48)
        path.lineTo(s * 0.62, s * 0.48)
        path.lineTo(s * 0.62, s * 0.66)
        path.lineTo(s * 0.38, s * 0.66)
        path.lineTo(s * 0.38, s * 0.48)
        path.lineTo(s * 0.20, s * 0.48)
        path.closeSubpath()
        p.setPen(QPen(ac, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
        p.drawLine(QPointF(s * 0.34, s * 0.82), QPointF(s * 0.66, s * 0.82))

    elif kind == "download":
        p.setPen(QPen(ac, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawLine(QPointF(cx, s * 0.18), QPointF(cx, s * 0.62))
        p.drawLine(QPointF(s * 0.32, s * 0.46), QPointF(cx, s * 0.64))
        p.drawLine(QPointF(s * 0.68, s * 0.46), QPointF(cx, s * 0.64))
        p.drawLine(QPointF(s * 0.22, s * 0.80), QPointF(s * 0.78, s * 0.80))

    elif kind == "sun":
        p.setPen(QPen(ac, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawEllipse(QPointF(cx, cy), s * 0.20, s * 0.20)
        for i in range(8):
            ang = i * math.pi / 4.0
            r1, r2 = s * 0.30, s * 0.40
            p.drawLine(
                QPointF(cx + math.cos(ang) * r1, cy + math.sin(ang) * r1),
                QPointF(cx + math.cos(ang) * r2, cy + math.sin(ang) * r2),
            )

    elif kind in ("cloud", "cloud_sun", "rain", "storm", "snow", "mist"):
        if kind == "cloud_sun":
            p.setPen(QPen(ac, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawEllipse(QPointF(s * 0.36, s * 0.36), s * 0.15, s * 0.15)
        p.setPen(QPen(c, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        cloud = QPainterPath()
        cloud.addRoundedRect(QRectF(s * 0.20, s * 0.42, s * 0.60, s * 0.26), 5.0, 5.0)
        p.drawPath(cloud)
        if kind == "rain":
            p.setPen(QPen(ac, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(s * 0.36, s * 0.74), QPointF(s * 0.32, s * 0.86))
            p.drawLine(QPointF(s * 0.54, s * 0.74), QPointF(s * 0.50, s * 0.86))
        elif kind == "storm":
            p.setPen(QPen(ac, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(s * 0.52, s * 0.68), QPointF(s * 0.44, s * 0.80))
            p.drawLine(QPointF(s * 0.44, s * 0.80), QPointF(s * 0.54, s * 0.80))

    # ── v4 icons ──────────────────────────────────────────────────────
    elif kind == "screenshot":
        L = s * 0.18
        for (x, y, dx, dy) in (
            (s * 0.16, s * 0.16, 1, 1),
            (s * 0.84, s * 0.16, -1, 1),
            (s * 0.16, s * 0.84, 1, -1),
            (s * 0.84, s * 0.84, -1, -1),
        ):
            p.drawLine(QPointF(x, y), QPointF(x + dx * L, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + dy * L))
        p.setPen(QPen(ac, 1.6))
        p.drawEllipse(QPointF(cx, cy), s * 0.13, s * 0.13)

    elif kind == "folder":
        path = QPainterPath()
        path.moveTo(s * 0.14, s * 0.30)
        path.lineTo(s * 0.40, s * 0.30)
        path.lineTo(s * 0.48, s * 0.38)
        path.lineTo(s * 0.86, s * 0.38)
        path.lineTo(s * 0.86, s * 0.78)
        path.lineTo(s * 0.14, s * 0.78)
        path.closeSubpath()
        p.drawPath(path)
        p.setPen(QPen(ac, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(s * 0.30, s * 0.56), QPointF(s * 0.70, s * 0.56))

    elif kind == "calc":
        p.drawRoundedRect(QRectF(s * 0.22, s * 0.14, s * 0.56, s * 0.72), 3.0, 3.0)
        p.setPen(QPen(ac, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(s * 0.34, s * 0.30), QPointF(s * 0.66, s * 0.30))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        for gx in (0.37, 0.50, 0.63):
            for gy in (0.50, 0.66):
                p.drawEllipse(QPointF(s * gx, s * gy), s * 0.04, s * 0.04)

    elif kind == "pulse":
        path = QPainterPath()
        path.moveTo(s * 0.10, cy)
        path.lineTo(s * 0.32, cy)
        path.lineTo(s * 0.42, s * 0.26)
        path.lineTo(s * 0.56, s * 0.76)
        path.lineTo(s * 0.66, cy)
        path.lineTo(s * 0.90, cy)
        p.setPen(QPen(ac, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)

    elif kind == "swap":
        p.setPen(QPen(ac, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawLine(QPointF(s * 0.18, s * 0.36), QPointF(s * 0.80, s * 0.36))
        p.drawLine(QPointF(s * 0.66, s * 0.22), QPointF(s * 0.80, s * 0.36))
        p.drawLine(QPointF(s * 0.82, s * 0.64), QPointF(s * 0.20, s * 0.64))
        p.drawLine(QPointF(s * 0.34, s * 0.78), QPointF(s * 0.20, s * 0.64))

    elif kind == "copy":
        p.drawRoundedRect(QRectF(s * 0.34, s * 0.32, s * 0.46, s * 0.50), 3.0, 3.0)
        path = QPainterPath()
        path.moveTo(s * 0.24, s * 0.66)
        path.lineTo(s * 0.20, s * 0.66)
        path.lineTo(s * 0.20, s * 0.18)
        path.lineTo(s * 0.62, s * 0.18)
        path.lineTo(s * 0.62, s * 0.24)
        p.drawPath(path)

    elif kind == "paste":
        p.drawRoundedRect(QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.62), 3.0, 3.0)
        p.setPen(QPen(ac, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawRoundedRect(QRectF(s * 0.38, s * 0.14, s * 0.24, s * 0.14), 2.0, 2.0)
        p.drawLine(QPointF(s * 0.36, s * 0.52), QPointF(s * 0.64, s * 0.52))
        p.drawLine(QPointF(s * 0.36, s * 0.66), QPointF(s * 0.56, s * 0.66))

    elif kind == "close":
        p.drawLine(QPointF(s * 0.28, s * 0.28), QPointF(s * 0.72, s * 0.72))
        p.drawLine(QPointF(s * 0.72, s * 0.28), QPointF(s * 0.28, s * 0.72))

    elif kind == "chevron_down":
        path = QPainterPath()
        path.moveTo(s * 0.28, s * 0.40)
        path.lineTo(cx, s * 0.62)
        path.lineTo(s * 0.72, s * 0.40)
        p.drawPath(path)

    elif kind == "keyboard":
        p.drawRoundedRect(QRectF(s * 0.12, s * 0.28, s * 0.76, s * 0.46), 3.0, 3.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        for gx in (0.26, 0.40, 0.54, 0.68):
            p.drawEllipse(QPointF(s * gx, s * 0.42), s * 0.035, s * 0.035)
        p.setBrush(ac)
        p.drawRoundedRect(QRectF(s * 0.30, s * 0.55, s * 0.40, s * 0.07), 1.5, 1.5)

    elif kind == "translate":
        p.setPen(QPen(c, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawLine(QPointF(s * 0.14, s * 0.24), QPointF(s * 0.52, s * 0.24))
        p.drawLine(QPointF(s * 0.33, s * 0.16), QPointF(s * 0.33, s * 0.24))
        path = QPainterPath()
        path.moveTo(s * 0.44, s * 0.24)
        path.quadTo(s * 0.38, s * 0.48, s * 0.16, s * 0.58)
        path.moveTo(s * 0.24, s * 0.34)
        path.quadTo(s * 0.32, s * 0.48, s * 0.48, s * 0.56)
        p.drawPath(path)
        p.setPen(QPen(ac, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        a_path = QPainterPath()
        a_path.moveTo(s * 0.52, s * 0.86)
        a_path.lineTo(s * 0.68, s * 0.46)
        a_path.lineTo(s * 0.84, s * 0.86)
        p.drawPath(a_path)
        p.drawLine(QPointF(s * 0.58, s * 0.72), QPointF(s * 0.78, s * 0.72))

    elif kind == "palette":
        p.drawEllipse(QPointF(cx, cy), s * 0.34, s * 0.34)
        p.setPen(Qt.PenStyle.NoPen)
        for (gx, gy, col) in ((0.38, 0.38, "#F43F5E"), (0.60, 0.36, "#34D399"), (0.66, 0.58, "#38BDF8")):
            p.setBrush(QColor(col))
            p.drawEllipse(QPointF(s * gx, s * gy), s * 0.065, s * 0.065)
        p.setBrush(ac)
        p.drawEllipse(QPointF(s * 0.40, s * 0.62), s * 0.08, s * 0.08)

    elif kind == "person":
        p.drawEllipse(QPointF(cx, s * 0.36), s * 0.15, s * 0.15)
        path = QPainterPath()
        path.moveTo(s * 0.20, s * 0.84)
        path.quadTo(cx, s * 0.44, s * 0.80, s * 0.84)
        p.setPen(QPen(ac, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPath(path)

    elif kind == "pill":
        p.drawRoundedRect(QRectF(s * 0.14, s * 0.34, s * 0.72, s * 0.32), s * 0.16, s * 0.16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ac)
        p.drawEllipse(QPointF(s * 0.32, cy), s * 0.07, s * 0.07)
        p.drawRoundedRect(QRectF(s * 0.46, s * 0.46, s * 0.28, s * 0.08), 2.0, 2.0)

    elif kind == "grid":
        for gx in (0.20, 0.54):
            for gy in (0.20, 0.54):
                p.drawRoundedRect(QRectF(s * gx, s * gy, s * 0.26, s * 0.26), 2.5, 2.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ac)
        p.drawRoundedRect(QRectF(s * 0.54, s * 0.54, s * 0.26, s * 0.26), 2.5, 2.5)

    elif kind == "sliders":
        for i, (y, kx) in enumerate(((0.28, 0.62), (0.50, 0.36), (0.72, 0.56))):
            p.setPen(QPen(c, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(s * 0.16, s * y), QPointF(s * 0.84, s * y))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ac)
            p.drawEllipse(QPointF(s * kx, s * y), s * 0.08, s * 0.08)

    elif kind == "cloud_key":
        p.drawEllipse(QPointF(s * 0.34, cy), s * 0.14, s * 0.14)
        p.setPen(QPen(ac, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(s * 0.48, cy), QPointF(s * 0.84, cy))
        p.drawLine(QPointF(s * 0.72, cy), QPointF(s * 0.72, s * 0.64))
        p.drawLine(QPointF(s * 0.82, cy), QPointF(s * 0.82, s * 0.60))

    elif kind == "usb":
        p.drawRoundedRect(QRectF(s * 0.34, s * 0.18, s * 0.32, s * 0.18), 2.0, 2.0)
        p.setPen(QPen(ac, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawRoundedRect(QRectF(s * 0.28, s * 0.36, s * 0.44, s * 0.44), 3.0, 3.0)
        p.drawLine(QPointF(s * 0.43, s * 0.25), QPointF(s * 0.43, s * 0.29))
        p.drawLine(QPointF(s * 0.57, s * 0.25), QPointF(s * 0.57, s * 0.29))

    elif kind == "headphones":
        p.drawArc(QRectF(s * 0.18, s * 0.18, s * 0.64, s * 0.64), 0, 180 * 16)
        p.setPen(QPen(ac, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawRoundedRect(QRectF(s * 0.14, s * 0.48, s * 0.16, s * 0.30), 3.0, 3.0)
        p.drawRoundedRect(QRectF(s * 0.70, s * 0.48, s * 0.16, s * 0.30), 3.0, 3.0)

    elif kind == "mouse":
        p.drawRoundedRect(QRectF(s * 0.28, s * 0.16, s * 0.44, s * 0.68), s * 0.22, s * 0.22)
        p.setPen(QPen(ac, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(cx, s * 0.28), QPointF(cx, s * 0.42))

    elif kind == "bluetooth":
        p.setPen(QPen(ac, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        pts = [
            QPointF(s * 0.30, s * 0.34),
            QPointF(s * 0.68, s * 0.66),
            QPointF(s * 0.48, s * 0.84),
            QPointF(s * 0.48, s * 0.16),
            QPointF(s * 0.68, s * 0.34),
            QPointF(s * 0.30, s * 0.66),
        ]
        for i in range(len(pts) - 1):
            p.drawLine(pts[i], pts[i + 1])

    p.end()
    return pm


def render_vector_icon(
    kind: str,
    size: int = 18,
    color: str = "#F4F2EE",
    accent: str = "#E2A86B",
) -> QIcon:
    return QIcon(render_vector_pixmap(kind, size=size, color=color, accent=accent))


class WaveformWidget(QWidget):
    """Animated 4-bar audio equalizer for the droplet."""

    def __init__(self, accent_color: str = "#E2A86B", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = QColor(accent_color)
        self._playing = False
        self._phase = 0.0
        self.setFixedSize(20, 16)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

    def set_accent(self, color_hex: str) -> None:
        self._accent = QColor(color_hex)
        self.update()

    def set_playing(self, playing: bool) -> None:
        self._playing = playing
        if playing and not self._timer.isActive():
            self._timer.start()
        elif not playing and self._timer.isActive():
            self._timer.stop()
        self.update()

    def _tick(self) -> None:
        self._phase += 0.45
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._accent)

        w = self.width()
        h = self.height()
        bar_w = 2.4
        gap = 2.2
        total_w = 4 * bar_w + 3 * gap
        start_x = (w - total_w) / 2.0

        offsets = (0.0, 1.3, 2.5, 0.8)
        for i, off in enumerate(offsets):
            if self._playing:
                ratio = 0.30 + 0.62 * (0.5 + 0.5 * math.sin(self._phase + off))
            else:
                ratio = 0.24
            bh = max(3.0, h * ratio)
            x = start_x + i * (bar_w + gap)
            y = (h - bh) / 2.0
            p.drawRoundedRect(QRectF(x, y, bar_w, bh), 1.2, 1.2)
        p.end()
