"""Download folder watcher that tracks active, paused, and completed downloads."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import sys
import threading
import time
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from core.i18n import tr

TEMP_EXTENSIONS = {
    ".crdownload",
    ".part",
    ".tmp",
    ".opdownload",
    ".download",
    ".partial",
    ".!ut",
    ".bc!",
    ".aria2",
}
IGNORED_FILENAMES = {"desktop.ini", "thumbs.db", ".ds_store"}


def is_temp_file(path: str | Path) -> bool:
    """Return True if path looks like an in-progress temp or hidden system file."""
    p = Path(path)
    low_name = p.name.lower()
    if low_name in IGNORED_FILENAMES or p.name.startswith(".") or p.name.startswith("~$"):
        return True
    return p.suffix.lower() in TEMP_EXTENSIONS


def _is_active_download_temp(path: str | Path) -> bool:
    p = Path(path)
    low_name = p.name.lower()
    if low_name in IGNORED_FILENAMES or p.name.startswith(".") or p.name.startswith("~$"):
        return False
    return p.suffix.lower() in TEMP_EXTENSIONS


def _display_name_for_temp(p: Path) -> str:
    stem = p.stem
    if stem.lower().startswith("unconfirmed "):
        return "Download"
    return stem or p.name


if sys.platform == "win32":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _kernel32.CreateFileW.restype = wintypes.HANDLE
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
else:
    _kernel32 = None
    _INVALID_HANDLE_VALUE = None


def _is_file_in_use(path: Path) -> bool:
    """Return True on Windows if another process currently holds a lock on the file."""
    if _kernel32 is None or not path.exists():
        return False
    try:
        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_EXISTING = 3
        FILE_ATTRIBUTE_NORMAL = 0x80
        handle = _kernel32.CreateFileW(
            str(path),
            GENERIC_READ | GENERIC_WRITE,
            0,  # exclusive check: fails with ERROR_SHARING_VIOLATION (32) if open anywhere
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )
        if handle == _INVALID_HANDLE_VALUE:
            err = ctypes.get_last_error()
            return err == 32  # ERROR_SHARING_VIOLATION
        _kernel32.CloseHandle(handle)
        return False
    except Exception:
        return False


def format_size(num_bytes: int) -> str:
    """Format byte size into a human-readable string."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024.0
    return f"{size:.1f} GB"


class _DownloadHandler(FileSystemEventHandler):
    def __init__(self, on_ready, on_progress, on_cleared, stop_event: threading.Event) -> None:
        super().__init__()
        self._on_ready = on_ready
        self._on_progress = on_progress
        self._on_cleared = on_cleared
        self._stop_event = stop_event
        self._verifying: set[str] = set()
        self._completed: dict[str, float] = {}
        self._progress_ts: dict[str, float] = {}
        self._temp_state: dict[str, tuple[int, float]] = {}  # path -> (last_size, last_growth_ts)
        self._had_active = False
        self._lock = threading.Lock()

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src = getattr(event, "src_path", "")
        dest = getattr(event, "dest_path", "")
        if src:
            with self._lock:
                self._temp_state.pop(src, None)
        if dest and not is_temp_file(dest):
            self._schedule_verify(dest)

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if _is_active_download_temp(event.src_path):
            self._report_temp_file(Path(event.src_path))
            return
        if not is_temp_file(event.src_path):
            self._schedule_verify(event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if _is_active_download_temp(event.src_path):
            self._report_temp_file(Path(event.src_path))
            return
        if not is_temp_file(event.src_path):
            self._schedule_verify(event.src_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        if _is_active_download_temp(event.src_path):
            with self._lock:
                self._temp_state.pop(event.src_path, None)
            # Firefox deletes `<file>.part` when `<file>` finishes
            candidate = Path(event.src_path).with_suffix("")
            if candidate.exists() and not is_temp_file(candidate):
                self._schedule_verify(str(candidate))

    def _report_temp_file(self, p: Path, from_poll: bool = False) -> None:
        try:
            size = p.stat().st_size if p.exists() else 0
        except OSError:
            size = 0
        now = time.monotonic()
        key = str(p)
        paused = False
        with self._lock:
            prev_size, growth_ts = self._temp_state.get(key, (-1, now))
            if size != prev_size:
                growth_ts = now
            elif now - growth_ts >= 3.0 and (size > 0 or from_poll):
                paused = True
            self._temp_state[key] = (size, growth_ts)
            self._had_active = True
            last_emit = self._progress_ts.get(key, 0.0)
            if not from_poll and size == prev_size and now - last_emit < 0.35:
                return
            self._progress_ts[key] = now

        size_str = format_size(size)
        if paused:
            size_str = f"{tr('dl_paused')} · {size_str}"
        self._on_progress(_display_name_for_temp(p), size_str)

    def poll_folders(self, folders: list[str], known_files: set[str]) -> None:
        """Scan watched folders periodically so Windows buffered writes still report live progress."""
        active_temps: list[Path] = []
        for folder in folders:
            if not folder or not os.path.isdir(folder):
                continue
            try:
                with os.scandir(folder) as it:
                    for entry in it:
                        try:
                            if not entry.is_file(follow_symlinks=False):
                                continue
                        except OSError:
                            continue
                        ep = Path(entry.path)
                        if _is_active_download_temp(ep):
                            active_temps.append(ep)
                        elif not is_temp_file(ep) and entry.path not in known_files:
                            known_files.add(entry.path)
                            self._schedule_verify(entry.path)
            except OSError:
                continue

        if active_temps:
            for tp in active_temps:
                self._report_temp_file(tp, from_poll=True)
            return

        with self._lock:
            stale = [k for k in self._temp_state if not Path(k).exists()]
            for k in stale:
                self._temp_state.pop(k, None)
            should_clear = self._had_active and not self._temp_state and not self._verifying
            if should_clear:
                self._had_active = False
        if should_clear:
            self._on_cleared()

    def _has_temp_sibling(self, p: Path) -> bool:
        for ext in TEMP_EXTENSIONS:
            if Path(f"{p}{ext}").exists():
                return True
        return False

    def _schedule_verify(self, path_str: str) -> None:
        now = time.monotonic()
        with self._lock:
            if path_str in self._verifying:
                return
            if now - self._completed.get(path_str, 0.0) < 4.0:
                return
            self._verifying.add(path_str)
        threading.Thread(target=self._verify_and_emit, args=(path_str,), daemon=True).start()

    def _verify_and_emit(self, path_str: str) -> None:
        p = Path(path_str)
        try:
            prev_size = -1
            stable_ticks = 0
            growth_ts = time.monotonic()
            zero_ticks = 0

            while not self._stop_event.is_set():
                if not p.exists() or is_temp_file(p) or self._has_temp_sibling(p):
                    return
                try:
                    size = p.stat().st_size
                except OSError:
                    return

                in_use = _is_file_in_use(p)
                now = time.monotonic()
                changed = size != prev_size

                if changed:
                    prev_size = size
                    growth_ts = now
                    stable_ticks = 0
                elif not in_use and size > 0:
                    stable_ticks += 1
                else:
                    stable_ticks = 0

                if not in_use and size > 0 and stable_ticks >= 2:
                    with self._lock:
                        self._completed[path_str] = time.monotonic()
                        self._had_active = False
                    self._on_ready(str(p), p.name, format_size(size))
                    return

                if in_use or (size > 0 and changed):
                    with self._lock:
                        self._had_active = True
                    msg = format_size(size)
                    if in_use and now - growth_ts >= 3.0:
                        msg = f"{tr('dl_paused')} · {msg}"
                    self._on_progress(p.name, msg)
                    zero_ticks = 0
                elif size == 0:
                    zero_ticks += 1
                    if zero_ticks >= 10:
                        # Still 0 bytes after ~4.5s and not locked -> stop waiting;
                        # on_modified will re-trigger if data arrives later.
                        return

                self._stop_event.wait(0.45)
        finally:
            with self._lock:
                self._verifying.discard(path_str)


class DownloadMonitor(QObject):
    """Watches configured folders and emits download_progress / download_cleared / download_finished."""

    download_progress = Signal(str, str)  # file_name, size_or_status
    download_cleared = Signal()
    download_finished = Signal(str, str, str)  # full_path, file_name, size_str

    def __init__(self, folders: list[str], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._folders = list(folders)
        self._observer: Observer | None = None
        self._stop_event = threading.Event()
        self._poll_thread: threading.Thread | None = None
        self._handler = _DownloadHandler(
            self._emit_finished,
            self._emit_progress,
            self._emit_cleared,
            self._stop_event,
        )

    def _emit_progress(self, file_name: str, size_str: str) -> None:
        self.download_progress.emit(file_name, size_str)

    def _emit_cleared(self) -> None:
        self.download_cleared.emit()

    def _emit_finished(self, full_path: str, file_name: str, size_str: str) -> None:
        self.download_finished.emit(full_path, file_name, size_str)

    def _snapshot_existing_files(self) -> set[str]:
        existing: set[str] = set()
        for folder in self._folders:
            if not folder or not os.path.isdir(folder):
                continue
            try:
                with os.scandir(folder) as it:
                    for entry in it:
                        if not _is_active_download_temp(entry.path):
                            existing.add(entry.path)
            except OSError:
                continue
        return existing

    def _poll_loop(self, known_files: set[str]) -> None:
        while not self._stop_event.is_set():
            self._handler.poll_folders(list(self._folders), known_files)
            self._stop_event.wait(0.6)

    def start(self) -> None:
        self.stop()
        self._stop_event.clear()
        observer = Observer()
        scheduled_any = False
        for folder in self._folders:
            if folder and os.path.isdir(folder):
                observer.schedule(self._handler, folder, recursive=False)
                scheduled_any = True
        if scheduled_any:
            observer.daemon = True
            observer.start()
            self._observer = observer
            known = self._snapshot_existing_files()
            self._poll_thread = threading.Thread(
                target=self._poll_loop, args=(known,), daemon=True
            )
            self._poll_thread.start()

    def update_folders(self, folders: list[str]) -> None:
        if list(folders) != self._folders:
            self._folders = list(folders)
            self.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=2.0)
            self._poll_thread = None
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2.0)
            self._observer = None
