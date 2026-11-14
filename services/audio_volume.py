"""Windows Master Audio Volume controller via pycaw / CoreAudio."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

try:
    from pycaw.pycaw import AudioUtilities

    PYCAW_AVAILABLE = True
except ImportError:  # pragma: no cover
    PYCAW_AVAILABLE = False
    AudioUtilities = None


class AudioVolumeService(QObject):
    """Reads and sets Windows master speaker volume (0..100) and mute state."""

    volume_changed = Signal(int, bool)  # volume_pct, is_muted

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._endpoint = None
        self._last_vol = -1
        self._last_mute = False
        self._timer = QTimer(self)
        self._timer.setInterval(1200)
        self._timer.timeout.connect(self._poll)

    def _ensure_endpoint(self):
        if self._endpoint is not None or not PYCAW_AVAILABLE:
            return self._endpoint
        try:
            device = AudioUtilities.GetSpeakers()
            if hasattr(device, "EndpointVolume"):
                self._endpoint = device.EndpointVolume
            else:
                from ctypes import POINTER, cast
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import IAudioEndpointVolume

                interface = device.Activate(
                    IAudioEndpointVolume._iid_, CLSCTX_ALL, None
                )
                self._endpoint = cast(interface, POINTER(IAudioEndpointVolume))
        except Exception:
            self._endpoint = None
        return self._endpoint

    def start(self) -> None:
        self._poll()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def get_state(self) -> tuple[int, bool]:
        ep = self._ensure_endpoint()
        if ep is None:
            return (50, False)
        try:
            vol = round(float(ep.GetMasterVolumeLevelScalar()) * 100)
            muted = bool(ep.GetMute())
            return (max(0, min(100, vol)), muted)
        except Exception:
            return (50, False)

    def set_volume(self, pct: int) -> None:
        ep = self._ensure_endpoint()
        if ep is None:
            return
        try:
            scalar = max(0.0, min(1.0, pct / 100.0))
            ep.SetMasterVolumeLevelScalar(scalar, None)
            self._last_vol = pct
        except Exception:
            pass

    def toggle_mute(self) -> None:
        ep = self._ensure_endpoint()
        if ep is None:
            return
        try:
            new_mute = not bool(ep.GetMute())
            ep.SetMute(int(new_mute), None)
            self._poll()
        except Exception:
            pass

    def _poll(self) -> None:
        vol, muted = self.get_state()
        if vol != self._last_vol or muted != self._last_mute:
            self._last_vol = vol
            self._last_mute = muted
            self.volume_changed.emit(vol, muted)
