"""Entry point for the Pill v3 (Windows Droplet Island) application."""

from __future__ import annotations

import sys
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from core.config import AppConfig, ConfigManager, resource_path
from core.i18n import set_language
from services.audio_volume import AudioVolumeService
from services.capslock import CapsLockMonitor
from services.clipboard_mgr import ClipboardManager
from services.downloads import DownloadMonitor
from services.media_smtc import MediaSMTCService
from services.weather import WeatherService
from ui.pill_window import PillWindow
from ui.tray import PillTray

SINGLE_INSTANCE_KEY = "PillDropletIslandInstance"


class PillApp:
    """Coordinates UI, configuration, and all background services."""

    def __init__(self, qt_app: QApplication) -> None:
        self.qt_app = qt_app
        self.config_mgr = ConfigManager()
        self.cfg = self.config_mgr.config
        set_language(self.cfg.appearance.language)

        self.window = PillWindow(self.cfg)
        self.tray = PillTray(self.cfg.appearance.accent_color)
        self.tray.show()

        self.capslock = CapsLockMonitor()
        self.downloads = DownloadMonitor(self.cfg.downloads.watch_folders)
        self.clipboard = ClipboardManager(max_items=self.cfg.clipboard.max_items)
        self.media = MediaSMTCService()
        self.audio_vol = AudioVolumeService()
        self.weather = WeatherService(
            api_key=self.cfg.weather.api_key,
            city=self.cfg.weather.city,
            units=self.cfg.weather.units,
            refresh_minutes=self.cfg.weather.refresh_minutes,
        )

        self._ipc_server = QLocalServer(self.window)
        self._setup_single_instance_server()
        self._connect_signals()

    def _setup_single_instance_server(self) -> None:
        QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
        if self._ipc_server.listen(SINGLE_INSTANCE_KEY):
            self._ipc_server.newConnection.connect(self._on_new_instance_connected)

    def _on_new_instance_connected(self) -> None:
        conn = self._ipc_server.nextPendingConnection()
        if conn is not None:
            conn.close()
        self.quit()

    def _connect_signals(self) -> None:
        self.window.settings_applied.connect(self._on_settings_applied)
        self.window.hide_requested.connect(self.hide_pill)

        self.tray.toggle_visibility_requested.connect(self.toggle_visibility)
        self.tray.open_settings_requested.connect(self.open_settings)
        self.tray.quit_requested.connect(self.quit)

        self.capslock.toggled.connect(self.window.show_capslock_toast)
        self.downloads.download_progress.connect(self.window.show_download_progress)
        self.downloads.download_cleared.connect(self.window.clear_download_progress)
        self.downloads.download_finished.connect(self.window.show_download_toast)

        self.clipboard.history_changed.connect(
            lambda: self.window.expanded_panel.update_clipboard(self.clipboard.items)
        )
        self.window.expanded_panel.clipboard_item_clicked.connect(
            self.clipboard.copy_to_clipboard
        )
        self.window.expanded_panel.clipboard_clear_requested.connect(self.clipboard.clear)

        self.media.media_updated.connect(self.window.update_media)
        self.window.expanded_panel.play_pause_requested.connect(self.media.play_pause)
        self.window.expanded_panel.next_track_requested.connect(self.media.next_track)
        self.window.expanded_panel.prev_track_requested.connect(self.media.prev_track)

        self.audio_vol.volume_changed.connect(self.window.expanded_panel.update_volume_ui)
        self.window.expanded_panel.volume_set_requested.connect(self.audio_vol.set_volume)
        self.window.expanded_panel.mute_toggle_requested.connect(self.audio_vol.toggle_mute)

        self.weather.weather_updated.connect(self.window.update_weather)
        self.weather.weather_error.connect(self.window.update_weather_error)
        self.window.expanded_panel.weather_refresh_requested.connect(self.weather.refresh)
        self.window.expanded_panel.weather_city_changed.connect(self._on_weather_city_changed)

    def start(self) -> None:
        self.clipboard.start()
        self.window.expanded_panel.update_clipboard(self.clipboard.items)
        self.capslock.start()
        self.downloads.start()
        self.media.start()
        self.audio_vol.start()
        self.weather.start()

        if not self.cfg.appearance.hidden:
            self.window.show()

    def _on_weather_city_changed(self, city: str) -> None:
        self.cfg.weather.city = city
        self.config_mgr.save(self.cfg)
        self.weather.set_city(city)

    def toggle_visibility(self) -> None:
        self.cfg.appearance.hidden = not self.cfg.appearance.hidden
        self.config_mgr.save(self.cfg)
        self.window.apply_config(self.cfg)

    def hide_pill(self) -> None:
        self.cfg.appearance.hidden = True
        self.config_mgr.save(self.cfg)
        self.window.apply_config(self.cfg)

    def open_settings(self) -> None:
        self.window.open_inline_settings()

    def _on_settings_applied(self, new_cfg: AppConfig) -> None:
        prev_weather = (
            self.cfg.weather.api_key,
            self.cfg.weather.city,
            self.cfg.weather.units,
            self.cfg.weather.refresh_minutes,
        )
        self.cfg = new_cfg
        self.config_mgr.save(new_cfg)
        self.window.apply_config(new_cfg)
        self.tray.update_icon(new_cfg.appearance.accent_color)
        self.tray.retranslate_ui()
        self.clipboard.set_max_items(new_cfg.clipboard.max_items)
        self.downloads.update_folders(new_cfg.downloads.watch_folders)

        cur_weather = (
            new_cfg.weather.api_key,
            new_cfg.weather.city,
            new_cfg.weather.units,
            new_cfg.weather.refresh_minutes,
        )
        if cur_weather != prev_weather:
            self.weather.configure(
                api_key=new_cfg.weather.api_key,
                city=new_cfg.weather.city,
                units=new_cfg.weather.units,
                refresh_minutes=new_cfg.weather.refresh_minutes,
            )

    def quit(self) -> None:
        self._ipc_server.close()
        self.capslock.stop()
        self.downloads.stop()
        self.media.stop()
        self.audio_vol.stop()
        self.weather.stop()
        self.tray.hide()
        self.qt_app.quit()


def _notify_existing_instance_to_exit() -> None:
    sock = QLocalSocket()
    sock.connectToServer(SINGLE_INSTANCE_KEY)
    if sock.waitForConnected(150):
        sock.disconnectFromServer()


def main() -> int:
    _notify_existing_instance_to_exit()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Pill")
    ico = resource_path("icon.ico")
    if ico.exists():
        app.setWindowIcon(QIcon(str(ico)))

    pill = PillApp(app)
    pill.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
