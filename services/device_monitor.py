"""Windows PnP device arrival detector (USB flash drives, mice, Bluetooth headphones)."""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from PySide6.QtCore import QObject, QTimer, Signal

try:
    _setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
    _HAS_SETUPAPI = True
except Exception:  # pragma: no cover
    _setupapi = None
    _HAS_SETUPAPI = False

DIGCF_PRESENT = 0x00000002
DIGCF_ALLCLASSES = 0x00000004
SPDRP_DEVICEDESC = 0x00000000
SPDRP_CLASS = 0x00000007
SPDRP_FRIENDLYNAME = 0x0000000C
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


class _SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("ClassGuid", _GUID),
        ("DevInst", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


if _HAS_SETUPAPI:
    _setupapi.SetupDiGetClassDevsW.argtypes = [
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        wintypes.HWND,
        wintypes.DWORD,
    ]
    _setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    _setupapi.SetupDiEnumDeviceInfo.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_SP_DEVINFO_DATA),
    ]
    _setupapi.SetupDiEnumDeviceInfo.restype = wintypes.BOOL
    _setupapi.SetupDiGetDeviceRegistryPropertyW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_SP_DEVINFO_DATA),
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _setupapi.SetupDiGetDeviceRegistryPropertyW.restype = wintypes.BOOL
    _setupapi.SetupDiGetDeviceInstanceIdW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_SP_DEVINFO_DATA),
        wintypes.LPWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _setupapi.SetupDiGetDeviceInstanceIdW.restype = wintypes.BOOL
    _setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    _setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL


_CLASS_PRIORITY: dict[str, int] = {
    "AudioEndpoint": 100,
    "MEDIA": 90,
    "DiskDrive": 85,
    "WPD": 80,
    "Bluetooth": 75,
    "Mouse": 65,
    "Keyboard": 60,
    "Camera": 55,
    "Image": 50,
    "USB": 25,
    "HIDClass": 15,
}

_CLASS_ICON: dict[str, str] = {
    "AudioEndpoint": "headphones",
    "MEDIA": "headphones",
    "DiskDrive": "usb",
    "WPD": "usb",
    "Bluetooth": "bluetooth",
    "Mouse": "mouse",
    "Keyboard": "keyboard",
    "Camera": "usb",
    "Image": "usb",
    "USB": "usb",
    "HIDClass": "usb",
}

_SKIP_ID_PREFIXES = ("ROOT\\", "HTREE\\", "SWD\\PRINTENUM", "SWD\\DRIVERENUM", "ACPI\\")
_NOISY_NAMES = (
    "generic usb hub",
    "usb root hub",
    "usb composite device",
    "составное usb устройство",
    "корневой usb-концентратор",
    "microsoft radio device enumeration bus",
    "bluetooth device (rfcomm protocol tdi)",
    "microsoft bluetooth a2dp",
    "microsoft bluetooth hands-free",
    "hid-compliant vendor-defined",
    "hid-совместимое устройство",
    "usb-устройство ввода",
    "usb input device",
)


def _read_prop(h_dev, dev_info, prop: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    req = wintypes.DWORD()
    if _setupapi.SetupDiGetDeviceRegistryPropertyW(
        h_dev,
        ctypes.byref(dev_info),
        prop,
        None,
        buf,
        ctypes.sizeof(buf),
        ctypes.byref(req),
    ):
        return buf.value.strip()
    return ""


def scan_present_devices() -> dict[str, tuple[str, str]]:
    """Return {instance_id: (setup_class, friendly_name)} for present peripheral devices."""
    devices: dict[str, tuple[str, str]] = {}
    if not _HAS_SETUPAPI:
        return devices

    h_dev = _setupapi.SetupDiGetClassDevsW(
        None, None, None, DIGCF_PRESENT | DIGCF_ALLCLASSES
    )
    if not h_dev or h_dev == INVALID_HANDLE_VALUE:
        return devices

    try:
        dev_info = _SP_DEVINFO_DATA()
        dev_info.cbSize = ctypes.sizeof(_SP_DEVINFO_DATA)
        id_buf = ctypes.create_unicode_buffer(512)
        idx = 0
        while _setupapi.SetupDiEnumDeviceInfo(h_dev, idx, ctypes.byref(dev_info)):
            idx += 1
            if not _setupapi.SetupDiGetDeviceInstanceIdW(
                h_dev, ctypes.byref(dev_info), id_buf, 512, None
            ):
                continue
            inst_id = id_buf.value.upper()
            if inst_id.startswith(_SKIP_ID_PREFIXES):
                continue
            cls = _read_prop(h_dev, dev_info, SPDRP_CLASS)
            if cls not in _CLASS_PRIORITY:
                continue
            name = _read_prop(h_dev, dev_info, SPDRP_FRIENDLYNAME) or _read_prop(
                h_dev, dev_info, SPDRP_DEVICEDESC
            )
            if not name:
                continue
            devices[inst_id] = (cls, name)
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(h_dev)

    return devices


def pick_best_connected_device(
    added: list[tuple[str, str]],
) -> tuple[str, str] | None:
    """Pick the most informative user-facing (icon_kind, device_name) from newly added PnP nodes."""
    if not added:
        return None

    non_noisy = [
        (cls, name)
        for cls, name in added
        if not any(noisy in name.lower() for noisy in _NOISY_NAMES)
    ]
    pool = non_noisy or added
    best_cls, best_name = max(
        pool,
        key=lambda item: (_CLASS_PRIORITY.get(item[0], 0), len(item[1])),
    )
    return _CLASS_ICON.get(best_cls, "usb"), best_name


class DeviceMonitor(QObject):
    """Detects newly connected peripherals (USB, mouse, Bluetooth audio) without toast spam."""

    device_connected = Signal(str, str)  # icon_kind, device_name
    _snapshot_ready = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._known: dict[str, tuple[str, str]] = {}
        self._running = False
        self._scanning = False
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(450)
        self._debounce.timeout.connect(self._trigger_scan)

        self._poll = QTimer(self)
        self._poll.setInterval(3000)
        self._poll.timeout.connect(self._trigger_scan)

        self._snapshot_ready.connect(self._on_snapshot_ready)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._known = scan_present_devices()
        self._poll.start()

    def stop(self) -> None:
        self._running = False
        self._debounce.stop()
        self._poll.stop()

    def notify_wm_devicechange(self) -> None:
        """Called from PillWindow WM_DEVICECHANGE handler for rapid PnP detection."""
        if self._running:
            self._debounce.start()

    def _trigger_scan(self) -> None:
        if not self._running or self._scanning:
            return
        self._scanning = True
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        try:
            snap = scan_present_devices()
            self._snapshot_ready.emit(snap)
        except Exception:
            self._snapshot_ready.emit(None)

    def _on_snapshot_ready(self, snap: dict[str, tuple[str, str]] | None) -> None:
        self._scanning = False
        if not self._running or snap is None:
            return

        added = [val for key, val in snap.items() if key not in self._known]
        self._known = snap
        picked = pick_best_connected_device(added)
        if picked is not None:
            icon_kind, dev_name = picked
            self.device_connected.emit(icon_kind, dev_name)
