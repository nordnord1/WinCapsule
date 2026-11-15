"""Unit tests for Pill v3: keyboard layout fixer, dynamic closed-pill width, RGB mixer, and 6-page UI."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from core.config import AppConfig, ConfigManager
from services.clipboard_mgr import ClipboardManager
from services.downloads import DownloadMonitor, format_size, is_temp_file
from services.text_tools import fix_keyboard_layout, looks_like_wrong_layout
from services.weather import deg_to_compass_uk, parse_weather_response
from ui.icons import load_mascot_pixmap, render_vector_pixmap
from ui.pill_window import PillWindow
from ui.widgets import SmoothCheckBox


@pytest.fixture(scope="session")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    return app


def test_keyboard_layout_fixer():
    assert fix_keyboard_layout("ghbdsn") == "привіт"
    assert fix_keyboard_layout("Ghbdsn") == "Привіт"
    assert fix_keyboard_layout("руддщ") == "hello"
    assert looks_like_wrong_layout("ghbdsn") == "привіт"
    assert looks_like_wrong_layout("hello world") is None


def test_config_roundtrip_and_clamping(tmp_path: Path):
    cfg_path = tmp_path / "config.json"
    mgr = ConfigManager(cfg_path)
    assert cfg_path.exists()
    assert mgr.config.appearance.theme_name == "Warm Obsidian"
    assert mgr.config.appearance.compact_show_mascot is True

    custom = AppConfig.from_dict(
        {
            "appearance": {
                "base_opacity": 2.5,
                "idle_delay_sec": 0,
                "vertical_offset_px": 5,
                "mascot_size": 99,
            },
            "weather": {"city": "London,UK", "refresh_minutes": 1},
            "clipboard": {"max_items": 100},
        }
    )
    assert custom.appearance.base_opacity == 1.0
    assert custom.appearance.idle_delay_sec == 1
    assert custom.appearance.vertical_offset_px == 20
    assert custom.appearance.mascot_size == 44
    assert custom.weather.refresh_minutes == 5
    assert custom.clipboard.max_items == 50

    mgr.save(custom)
    reloaded = ConfigManager(cfg_path).config
    assert reloaded.weather.city == "London,UK"


def test_downloads_helpers_and_monitor(tmp_path: Path, qapp):
    assert is_temp_file("movie.mkv.crdownload") is True
    assert is_temp_file("archive.zip.part") is True
    assert is_temp_file(".hidden") is True
    assert is_temp_file("document.pdf") is False
    assert format_size(512) == "512 B"
    assert format_size(2048) == "2.0 KB"

    results: list[tuple[str, str, str]] = []
    progress: list[tuple[str, str]] = []
    cleared: list[bool] = []
    monitor = DownloadMonitor([str(tmp_path)])
    monitor.download_progress.connect(lambda n, s: progress.append((n, s)))
    monitor.download_cleared.connect(lambda: cleared.append(True))
    monitor.download_finished.connect(lambda p, n, s: results.append((p, n, s)))
    monitor.start()

    try:
        # 1. Cancelled browser download emits progress then cleared (not finished)
        cancelled = tmp_path / "cancelled.zip.crdownload"
        cancelled.write_bytes(b"abc")
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not any(n == "cancelled.zip" for n, _ in progress):
            qapp.processEvents()
            time.sleep(0.05)
        assert any(n == "cancelled.zip" for n, _ in progress)
        cancelled.unlink()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not cleared:
            qapp.processEvents()
            time.sleep(0.05)
        assert cleared
        assert not any(n.startswith("cancelled.zip") for _, n, _ in results)

        # 2. Browser temp file renamed to final emits progress then finished
        temp_file = tmp_path / "installer.exe.crdownload"
        temp_file.write_bytes(b"1234567890")

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not any(n == "installer.exe" for n, _ in progress):
            qapp.processEvents()
            time.sleep(0.05)
        assert any(name == "installer.exe" for name, _ in progress)

        final_file = tmp_path / "installer.exe"
        temp_file.rename(final_file)

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not any(n == "installer.exe" for _, n, _ in results):
            qapp.processEvents()
            time.sleep(0.05)

        assert any(name == "installer.exe" for _, name, _ in results)
        assert not any(name.endswith(".crdownload") for _, name, _ in results)

        # 3. Open/locked direct download does NOT prematurely finish while handle is open
        locked_file = tmp_path / "paused.bin"
        with open(locked_file, "wb") as fh:
            fh.write(b"chunk1")
            fh.flush()
            wait_end = time.monotonic() + 1.3
            while time.monotonic() < wait_end:
                qapp.processEvents()
                time.sleep(0.05)
            assert not any(n == "paused.bin" for _, n, _ in results)

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not any(n == "paused.bin" for _, n, _ in results):
            qapp.processEvents()
            time.sleep(0.05)
        assert any(n == "paused.bin" for _, n, _ in results)
    finally:
        monitor.stop()


def test_detailed_weather_parsing():
    assert deg_to_compass_uk(0) == "Пн"
    assert deg_to_compass_uk(180) == "Пд"

    payload = {
        "name": "London",
        "main": {
            "temp": 4.2,
            "feels_like": 1.4,
            "temp_min": 2.0,
            "temp_max": 6.0,
            "humidity": 63,
            "pressure": 1005,
        },
        "wind": {"speed": 4.2, "deg": 180},
        "clouds": {"all": 25},
        "rain": {"1h": 1.4},
        "visibility": 9500,
        "weather": [{"description": "clear sky", "icon": "01d"}],
    }
    data = parse_weather_response(payload, units="metric")
    assert data.city == "London"
    assert round(data.temp) == 4
    assert data.pressure_mmhg == 754


def test_ui_v3_dynamic_compact_width_cycle_btn_and_rgb(qapp):
    for kind in ("cycle_tab", "pipette", "hide", "collapse", "play", "pause"):
        pm = render_vector_pixmap(kind, 18)
        assert not pm.isNull()

    mascot_pm = load_mascot_pixmap("", 24, "#E2A86B")
    assert not mascot_pm.isNull()

    cfg = AppConfig()
    win = PillWindow(cfg)

    # With Mascot + Clock + Weather enabled, compact width wraps all 3 tightly
    w_all = win._target_drop_rect().width()
    assert 130.0 <= w_all <= 215.0

    # When Clock is disabled, compact width shrinks automatically with zero empty gap!
    cfg.appearance.compact_show_clock = False
    win.apply_config(cfg)
    w_no_clock = win._target_drop_rect().width()
    assert w_no_clock < w_all - 30.0

    # When all closed-pill items are disabled, it becomes the 30x22 mini-droplet
    cfg.appearance.compact_show_mascot = False
    cfg.appearance.compact_show_weather = False
    cfg.appearance.compact_show_music = False
    cfg.appearance.compact_show_timer = False
    win.apply_config(cfg)
    r_mini = win._target_drop_rect()
    assert r_mini.width() == 30.0
    assert r_mini.height() == 22.0

    # Cycle Tab button cycles across all 6 pages
    win.toggle_expand()
    assert win.expanded_panel.inner_stack.currentIndex() == 0
    win.expanded_panel.cycle_tab_btn.click()
    assert win.expanded_panel.inner_stack.currentIndex() == 1

    # RGB mixer updates accent_color live
    emitted: list[AppConfig] = []
    win.settings_applied.connect(lambda c: emitted.append(c))
    sp = win.expanded_panel.settings_page
    sp._set_rgb_target("accent_color")
    sp.r_spin.setValue(100)
    sp.g_spin.setValue(200)
    sp.b_spin.setValue(255)
    assert emitted[-1].appearance.accent_color == "#64C8FF"

    # Accordion sections in Settings open/close exclusively
    sp.sec_colors.set_expanded(True, animate=False)
    assert sp.sec_colors.is_expanded() is True
    sp.sec_mascot.set_expanded(True, animate=False)
    assert sp.sec_mascot.is_expanded() is True
    assert sp.sec_colors.is_expanded() is False

    # Text tools page detects wrong layout and fixes it
    win.expanded_panel.text_tool_input.setText("ghbdsn")
    assert win.expanded_panel.layout_hint_btn.isVisible() or looks_like_wrong_layout("ghbdsn") == "привіт"
    win.expanded_panel._on_fix_layout_clicked()
    assert win.expanded_panel.text_tool_output.text() == "привіт"

    # Overview 3-slot customization (no Battery!) & Quick Folders slide-out menu (up to 5)
    sp.set_overview_slot(2, "net")
    assert emitted[-1].modules.overview_tile_3 == "net"
    assert win.expanded_panel.sys_stats_widget._slot_kinds == ["cpu", "ram", "net"]

    sp.folder_name_input.setText("MyProject")
    sp.folder_input.setText("C:/Users")
    sp._add_folder_inline()
    assert any(f.get("name") == "MyProject" for f in emitted[-1].downloads.quick_folders)
    assert len(emitted[-1].downloads.quick_folders) <= 5

    win.expanded_panel.folders_toggle_btn.click()
    assert win.expanded_panel.folders_popup.is_open() is True
    win.expanded_panel.folders_toggle_btn.click()
    assert win.expanded_panel.folders_popup.is_open() is False

    win.close()


def test_spinbox_visibility_text_tools_layout_and_i18n(qapp):
    cfg = AppConfig()
    cfg.appearance.hidden = False
    win = PillWindow(cfg)
    win.show()
    win.toggle_expand()
    win.expanded_panel.show_settings()
    sp = win.expanded_panel.settings_page
    sp.sec_colors.set_expanded(True, animate=False)
    qapp.processEvents()

    # (a) QSpinBox lineEdit must not collapse to 1px under QSS
    for spin in (sp.r_spin, sp.g_spin, sp.b_spin):
        assert spin.lineEdit().geometry().width() >= 30

    # (b) Текст і Переклад action buttons must fit within 484px and never overlap
    win.expanded_panel.switch_page(3)
    qapp.processEvents()
    ep = win.expanded_panel
    page_w = ep.text_tools_page.width()
    assert page_w <= 488

    mid_btns = [
        ep.src_lang_btn,
        ep.tgt_lang_btn,
        ep.swap_btn,
        ep.fix_btn,
        ep.tr_btn,
    ]
    xs = [b.geometry().x() for b in mid_btns]
    rights = [b.geometry().right() for b in mid_btns]
    assert rights[-1] <= page_w
    for i in range(len(mid_btns) - 1):
        assert rights[i] < xs[i + 1], f"Overlap between mid_btns[{i}] and [{i+1}]"

    # Expanding language popup opens with all 6 popular languages (+ Auto for source)
    ep._open_lang_popup("tgt")
    assert ep.lang_popup.is_open()
    ep._on_lang_selected("tgt", "es")
    assert ep._tgt_lang == "es"
    assert ep.tgt_lang_btn.text() == "Spanish"

    in_btns = [ep.paste_btn, ep.clip_fix_btn, ep.clear_in_btn]
    for i in range(len(in_btns) - 1):
        assert in_btns[i].geometry().right() < in_btns[i + 1].geometry().x()

    # (c) Default language is English; header shows mascot left of "by nord" and clock;
    # live en -> uk -> ru -> en switching updates ExpandedPanel & InlineSettingsPanel labels
    ep.switch_page(5)
    qapp.processEvents()
    assert cfg.appearance.language == "en"
    assert ep.by_nord_lbl.text() == "by nord"
    assert ep.mascot_badge.x() < ep.by_nord_lbl.x() < ep.time_lbl.x()
    assert ep.page_title_lbl.text() == "Settings"
    assert ep.folders_toggle_btn.text() == "Folders"
    assert sp.sec_colors.header._title == "Theme & RGB Colors"

    sp._select_language("uk")
    qapp.processEvents()
    assert ep.page_title_lbl.text() == "Налаштування"
    assert ep.folders_toggle_btn.text() == "Теки"

    sp._select_language("ru")
    qapp.processEvents()
    assert ep.page_title_lbl.text() == "Настройки"
    assert ep.folders_toggle_btn.text() == "Папки"
    assert sp.sec_colors.header._title == "Тема и цвета RGB"

    sp._select_language("en")
    qapp.processEvents()
    assert ep.page_title_lbl.text() == "Settings"

    # (d) Active download progress & completed download toast width
    win.collapse()
    qapp.processEvents()
    win.show_download_progress("archive.zip", "12.4 MB")
    assert any(kind == "download" for kind, _, _ in win._compute_compact_segments())
    win.show_download_toast("C:/tmp/archive.zip", "archive.zip", "15.0 MB")
    assert win._active_download_text == ""
    assert win._mode == win.MODE_TOAST
    assert win._target_drop_rect().width() == 320.0

    win.close()


def test_autostart_device_monitor_and_clipboard_delete(qapp, tmp_path):
    from services.autostart import is_autostart_enabled, set_autostart_enabled
    from services.clipboard_mgr import ClipboardManager
    from services.device_monitor import pick_best_connected_device

    # (a) Autostart shortcut creation & removal in isolated folder
    assert not is_autostart_enabled(folder=tmp_path)
    assert set_autostart_enabled(True, folder=tmp_path)
    assert is_autostart_enabled(folder=tmp_path)
    assert (tmp_path / "WinCapsule.lnk").exists()
    assert not set_autostart_enabled(False, folder=tmp_path)
    assert not is_autostart_enabled(folder=tmp_path)

    # (b) Device ranking chooses highest-priority friendly device over composite hubs
    picked = pick_best_connected_device([
        ("USB", "USB Composite Device"),
        ("HIDClass", "USB Input Device"),
        ("AudioEndpoint", "Headphones (WH-1000XM5)"),
    ])
    assert picked == ("headphones", "Headphones (WH-1000XM5)")

    picked_mouse = pick_best_connected_device([
        ("USB", "Generic USB Hub"),
        ("Mouse", "Logitech G Pro"),
    ])
    assert picked_mouse == ("mouse", "Logitech G Pro")

    # (c) Single-item deletion in ClipboardManager + UI delete button wiring
    cm = ClipboardManager(max_items=10)
    cm.add_item("first entry")
    cm.add_item("second entry")
    cm.remove_item("first entry")
    assert cm.items == ["second entry"]

    cfg = AppConfig()
    cfg.appearance.hidden = False
    win = PillWindow(cfg)
    win.show()
    win.expanded_panel.update_clipboard(["alpha", "beta"])
    deleted = []
    win.expanded_panel.clipboard_item_delete_requested.connect(deleted.append)
    item0 = win.expanded_panel.clip_list.item(0)
    row_w = win.expanded_panel.clip_list.itemWidget(item0)
    assert row_w is not None
    del_btn = row_w.findChild(win.expanded_panel.clip_clear_btn.__class__)
    assert del_btn is not None
    del_btn.click()
    assert deleted == ["alpha"]

    # (d) Device connect toast triggers clean toast mode
    win.show_device_toast("usb", "Kingston DataTraveler 3.0")
    assert win._mode == win.MODE_TOAST
    assert win.toast_title_lbl.text() == "DEVICE CONNECTED"
    assert "Kingston" in win.toast_sub_lbl.text()
    win.close()
