"""Windows shell:startup shortcut helper for WinCapsule."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from core.config import app_base_dir, resource_path

SHORTCUT_NAME = "WinCapsule.lnk"


def startup_dir() -> Path:
    """Return the current user's Windows Startup folder (shell:startup)."""
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def shortcut_path(folder: Path | None = None) -> Path:
    """Return full path to WinCapsule.lnk inside Startup."""
    return (folder or startup_dir()) / SHORTCUT_NAME


def is_autostart_enabled(folder: Path | None = None) -> bool:
    """Return True if the startup shortcut exists."""
    return shortcut_path(folder).exists()


def _launch_spec() -> tuple[str, str, str, str]:
    """Return (target_exe, arguments, working_dir, icon_path) for current runtime."""
    base = app_base_dir()
    ico = resource_path("icon.ico")
    ico_str = str(ico) if ico.exists() else ""

    if getattr(sys, "frozen", False):
        exe = str(Path(sys.executable).resolve())
        return exe, "", str(Path(exe).resolve().parent), ico_str

    exe_path = Path(sys.executable).resolve()
    pythonw = exe_path.with_name("pythonw.exe")
    target = str(pythonw if pythonw.exists() else exe_path)
    main_py = str((base / "main.py").resolve())
    return target, f'"{main_py}"', str(base), ico_str


def set_autostart_enabled(enabled: bool, folder: Path | None = None) -> bool:
    """Create or remove WinCapsule.lnk in Windows shell:startup. Returns resulting state."""
    lnk = shortcut_path(folder)
    if not enabled:
        try:
            if lnk.exists():
                lnk.unlink()
        except OSError:
            pass
        return lnk.exists()

    lnk.parent.mkdir(parents=True, exist_ok=True)
    target, args, work_dir, icon = _launch_spec()

    env = os.environ.copy()
    env["WC_LNK"] = str(lnk)
    env["WC_TGT"] = target
    env["WC_ARGS"] = args
    env["WC_DIR"] = work_dir
    env["WC_ICO"] = icon

    ps_script = (
        "$sh = New-Object -ComObject WScript.Shell; "
        "$sc = $sh.CreateShortcut($env:WC_LNK); "
        "$sc.TargetPath = $env:WC_TGT; "
        "if ($env:WC_ARGS) { $sc.Arguments = $env:WC_ARGS }; "
        "$sc.WorkingDirectory = $env:WC_DIR; "
        "if ($env:WC_ICO) { $sc.IconLocation = $env:WC_ICO }; "
        "$sc.Save()"
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            env=env,
            capture_output=True,
            timeout=8,
            creationflags=creationflags,
            check=True,
        )
    except Exception:
        return lnk.exists()
    return lnk.exists()
