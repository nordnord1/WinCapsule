"""System tray icon and context menu for Pill."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from core.i18n import tr


def create_droplet_icon(accent_hex: str = "#6C8EFF") -> QIcon:
    """Render a crisp 64x64 droplet icon for the system tray and dialogs."""
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    path = QPainterPath()
    path.moveTo(60, 4)
    path.lineTo(14, 4)
    path.quadTo(4, 4, 4, 14)
    path.lineTo(4, 24)
    path.cubicTo(4, 48, 20, 60, 44, 60)
    path.lineTo(52, 60)
    path.quadTo(60, 60, 60, 52)
    path.closeSubpath()

    painter.fillPath(path, QColor(accent_hex))
    painter.setBrush(QColor("#FFFFFF"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(26, 22, 16, 16)
    painter.end()
    return QIcon(pm)


class PillTray(QSystemTrayIcon):
    """Tray icon allowing quick show/hide, settings, and exit."""

    toggle_visibility_requested = Signal()
    open_settings_requested = Signal()
    quit_requested = Signal()

    def __init__(self, accent_color: str = "#6C8EFF", parent=None) -> None:
        super().__init__(create_droplet_icon(accent_color), parent)
        self.setToolTip("Pill — Droplet Island")

        menu = QMenu()
        self._toggle_action = QAction(tr("tray_toggle"), menu)
        self._toggle_action.triggered.connect(self.toggle_visibility_requested.emit)
        menu.addAction(self._toggle_action)

        self._settings_action = QAction(tr("tray_settings"), menu)
        self._settings_action.triggered.connect(self.open_settings_requested.emit)
        menu.addAction(self._settings_action)

        menu.addSeparator()

        self._quit_action = QAction(tr("tray_quit"), menu)
        self._quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(self._quit_action)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def retranslate_ui(self) -> None:
        self._toggle_action.setText(tr("tray_toggle"))
        self._settings_action.setText(tr("tray_settings"))
        self._quit_action.setText(tr("tray_quit"))

    def update_icon(self, accent_color: str) -> None:
        self.setIcon(create_droplet_icon(accent_color))

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.toggle_visibility_requested.emit()
