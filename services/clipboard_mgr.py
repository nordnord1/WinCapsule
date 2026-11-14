"""In-memory clipboard history manager backed by QClipboard."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QClipboard
from PySide6.QtWidgets import QApplication


class ClipboardManager(QObject):
    """Tracks copied text items and allows restoring any item to the clipboard."""

    history_changed = Signal()

    def __init__(self, max_items: int = 15, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._max_items = max_items
        self._items: list[str] = []
        self._ignore_next = False
        self._clipboard: QClipboard | None = None

    def start(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        self._clipboard = app.clipboard()
        self._clipboard.dataChanged.connect(self._on_clipboard_changed)
        initial = self._clipboard.text()
        if initial and initial.strip():
            self.add_item(initial)

    @property
    def items(self) -> list[str]:
        return list(self._items)

    def set_max_items(self, max_items: int) -> None:
        self._max_items = max(1, max_items)
        if len(self._items) > self._max_items:
            self._items = self._items[: self._max_items]
            self.history_changed.emit()

    def add_item(self, text: str) -> None:
        if not text or not text.strip():
            return
        if text in self._items:
            self._items.remove(text)
        self._items.insert(0, text)
        self._items = self._items[: self._max_items]
        self.history_changed.emit()

    def copy_to_clipboard(self, text: str) -> None:
        if self._clipboard is None:
            return
        self._ignore_next = True
        self._clipboard.setText(text)
        # Move selected item to top
        self.add_item(text)

    def clear(self) -> None:
        self._items.clear()
        self.history_changed.emit()

    def _on_clipboard_changed(self) -> None:
        if self._ignore_next:
            self._ignore_next = False
            return
        if self._clipboard is None:
            return
        text = self._clipboard.text()
        self.add_item(text)
