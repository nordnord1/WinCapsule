"""Global CapsLock state monitor for Windows."""

from __future__ import annotations

import ctypes
import threading
from PySide6.QtCore import QObject, Signal

try:
    from pynput import keyboard
except ImportError:  # pragma: no cover
    keyboard = None


VK_CAPITAL = 0x14


def is_capslock_on() -> bool:
    """Read current Windows CapsLock toggle state."""
    try:
        return bool(ctypes.windll.user32.GetKeyState(VK_CAPITAL) & 1)
    except AttributeError:
        return False


class CapsLockMonitor(QObject):
    """Listens for CapsLock key presses and emits the new toggle state."""

    toggled = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._listener = None
        self._last_state = is_capslock_on()

    def start(self) -> None:
        if keyboard is None or self._listener is not None:
            return

        def on_press(key) -> None:
            if key == keyboard.Key.caps_lock:
                # Delay slightly so Windows updates the toggle state before GetKeyState reads it.
                threading.Timer(0.04, self._check_and_emit).start()

        self._listener = keyboard.Listener(on_press=on_press)
        self._listener.daemon = True
        self._listener.start()

    def _check_and_emit(self) -> None:
        current = is_capslock_on()
        self._last_state = current
        self.toggled.emit(current)

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
