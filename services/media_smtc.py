"""Windows System Media Transport Controls (SMTC) service."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from PySide6.QtCore import QObject, Signal

from core.i18n import tr

try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
    )
    from winrt.windows.storage.streams import DataReader

    WINRT_AVAILABLE = True
except ImportError:  # pragma: no cover
    WINRT_AVAILABLE = False
    MediaManager = None
    PlaybackStatus = None
    DataReader = None


@dataclass
class MediaInfo:
    title: str = ""
    artist: str = ""
    is_playing: bool = False
    has_media: bool = False
    thumbnail_bytes: bytes = b""


class MediaSMTCService(QObject):
    """Polls Windows SMTC for active media info and provides playback controls."""

    media_updated = Signal(object)  # MediaInfo

    def __init__(self, poll_interval: float = 1.2, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._poll_interval = poll_interval
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_signature: tuple[str, str, bool, bool] | None = None
        self._last_thumb_key: tuple[str, str] | None = None
        self._cached_thumb: bytes = b""

    def start(self) -> None:
        if not WINRT_AVAILABLE or self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def play_pause(self) -> None:
        self._dispatch_action("play_pause")

    def next_track(self) -> None:
        self._dispatch_action("next")

    def prev_track(self) -> None:
        self._dispatch_action("prev")

    def _dispatch_action(self, action: str) -> None:
        if not WINRT_AVAILABLE or self._loop is None or not self._loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(self._perform_action(action), self._loop)

    async def _perform_action(self, action: str) -> None:
        try:
            manager = await MediaManager.request_async()
            session = manager.get_current_session()
            if session is None:
                return
            if action == "play_pause":
                await session.try_toggle_play_pause_async()
            elif action == "next":
                await session.try_skip_next_async()
            elif action == "prev":
                await session.try_skip_previous_async()
        except Exception:
            pass

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._poll_loop())
        finally:
            self._loop.close()
            self._loop = None

    async def _poll_loop(self) -> None:
        while self._running:
            info = await self._fetch_media_info()
            sig = (info.title, info.artist, info.is_playing, info.has_media)
            if sig != self._last_signature:
                self._last_signature = sig
                self.media_updated.emit(info)
            await asyncio.sleep(self._poll_interval)

    async def _fetch_media_info(self) -> MediaInfo:
        try:
            manager = await MediaManager.request_async()
            session = manager.get_current_session()
            if session is None:
                return MediaInfo(has_media=False)

            playback = session.get_playback_info()
            is_playing = bool(
                playback is not None
                and playback.playback_status == PlaybackStatus.PLAYING
            )
            props = await session.try_get_media_properties_async()
            title = (props.title or "").strip() if props else ""
            artist = (props.artist or "").strip() if props else ""
            if not title and not artist:
                return MediaInfo(has_media=False)

            thumb_key = (title, artist)
            if thumb_key != self._last_thumb_key:
                self._last_thumb_key = thumb_key
                self._cached_thumb = await self._read_thumbnail(props)

            return MediaInfo(
                title=title or tr("untitled"),
                artist=artist or tr("unknown_artist"),
                is_playing=is_playing,
                has_media=True,
                thumbnail_bytes=self._cached_thumb,
            )
        except Exception:
            return MediaInfo(has_media=False)

    @staticmethod
    async def _read_thumbnail(props) -> bytes:
        try:
            if props is None or props.thumbnail is None:
                return b""
            stream = await props.thumbnail.open_read_async()
            size = stream.size
            if size == 0 or size > 2_000_000:
                return b""
            reader = DataReader(stream)
            await reader.load_async(size)
            buf = bytearray(size)
            reader.read_bytes(buf)
            reader.close()
            stream.close()
            return bytes(buf)
        except Exception:
            return b""
