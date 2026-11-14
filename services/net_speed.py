"""Live network Download/Upload speed monitor using psutil."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
import psutil
from PySide6.QtCore import QObject, QTimer, Signal

from core.i18n import tr


def format_speed(bytes_per_sec: float) -> str:
    """Format bytes/sec into a crisp human-readable speed string."""
    if bytes_per_sec < 1024.0:
        return f"{int(bytes_per_sec)} {tr('unit_bps')}"
    kb = bytes_per_sec / 1024.0
    if kb < 1024.0:
        return f"{kb:.1f} {tr('unit_kbps')}"
    mb = kb / 1024.0
    return f"{mb:.2f} {tr('unit_mbps')}"


@dataclass
class NetSpeedStats:
    down_bps: float = 0.0
    up_bps: float = 0.0
    down_history: list[float] = field(default_factory=list)

    @property
    def down_str(self) -> str:
        return format_speed(self.down_bps)

    @property
    def up_str(self) -> str:
        return format_speed(self.up_bps)


class NetSpeedService(QObject):
    """Samples network IO counters every second and emits NetSpeedStats."""

    speed_updated = Signal(object)  # NetSpeedStats

    def __init__(self, history_len: int = 24, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._history_len = history_len
        self._history: list[float] = [0.0] * history_len
        self._last_recv = 0
        self._last_sent = 0
        self._last_time = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._sample)

    def start(self) -> None:
        try:
            io = psutil.net_io_counters()
            self._last_recv = io.bytes_recv
            self._last_sent = io.bytes_sent
            self._last_time = time.monotonic()
        except Exception:
            pass
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _sample(self) -> None:
        try:
            now = time.monotonic()
            io = psutil.net_io_counters()
            dt = max(0.1, now - self._last_time)
            down = max(0.0, (io.bytes_recv - self._last_recv) / dt)
            up = max(0.0, (io.bytes_sent - self._last_sent) / dt)
            self._last_recv = io.bytes_recv
            self._last_sent = io.bytes_sent
            self._last_time = now

            self._history.append(down)
            if len(self._history) > self._history_len:
                self._history = self._history[-self._history_len :]

            self.speed_updated.emit(
                NetSpeedStats(
                    down_bps=down,
                    up_bps=up,
                    down_history=list(self._history),
                )
            )
        except Exception:
            pass
