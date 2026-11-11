"""Paired Bluetooth devices, their type, connection state and the battery % Windows knows."""
import ctypes
import ctypes.wintypes as wt
import re
import uuid
from dataclasses import dataclass

from winrt.windows.devices.bluetooth import BluetoothDevice, BluetoothLEDevice
from winrt.windows.devices.enumeration import DeviceInformation

cfg = ctypes.windll.cfgmgr32


@dataclass
class Device:
    address: int
    name: str
    le: bool
    connected: bool
    icon: str

    @property
    def addr_hex(self) -> str:
        return "%012X" % self.address


# ---------------- type -> icon ----------------
_BUD_WORDS = re.compile(r"(?i)\b(buds?|earbuds?|pods|tws|freebuds|airdots|earphones?|ear ?\()")


def _icon_from_name(name: str) -> str | None:
    n = name.lower()
    if _BUD_WORDS.search(name):
        return "earbuds"
    for words, icon in ((("mouse", "mx master", "trackball"), "mouse"),
                        (("keyboard", "keys"), "keyboard"),
                        (("controller", "gamepad", "xbox", "dualsense", "dualshock", "joy-con"), "gamepad"),
                        (("headphone", "headset", "wh-", "qc"), "headphones"),
                        (("speaker", "soundbar", "jbl", "boom"), "speaker"),
                        (("watch", "band"), "watch"),
                        (("pen", "stylus"), "pen")):
        if any(w in n for w in words):
            return icon
    return None


def _icon_classic(d) -> str:
    c = d.class_of_device
    major, minor = int(c.major_class), int(c.minor_class)
    by_name = _icon_from_name(d.name or "")
    if major == 4:  # audio/video
        if by_name in ("earbuds", "speaker"):
            return by_name
        return "speaker" if minor in (5, 10) else "headphones"
    if major == 5:  # peripheral
        if minor & 0x30 == 0x20:
            return "mouse"
        if minor & 0x30:
            return "keyboard"
        if minor & 0x0F in (1, 2):
            return "gamepad"
        if minor & 0x0F == 5:
            return "pen"
    if major == 2:
        return "phone"
    if major == 7:
        return "watch"
    return by_name or "bluetooth"


def _icon_le(d) -> str:
    raw = d.appearance.raw_value
    cat, sub = raw >> 6, raw & 0x3F
    if cat == 0x0F:  # HID
        return {1: "keyboard", 2: "mouse", 3: "gamepad", 4: "gamepad", 7: "pen"}.get(sub, _icon_from_name(d.name or "") or "bluetooth")
    if cat == 0x01:
        return "phone"
    if cat == 0x03:
        return "watch"
    if cat in (0x25, 0x26, 0x21):  # audio sink/source, hearing aid
        return _icon_from_name(d.name or "") or "headphones"
    return _icon_from_name(d.name or "") or "bluetooth"


async def paired() -> list[Device]:
    """All paired devices (classic + LE). Reads Windows' cache only, no radio traffic."""
    out: dict[int, Device] = {}
    for le, cls in ((False, BluetoothDevice), (True, BluetoothLEDevice)):
        try:
            infos = await DeviceInformation.find_all_async_aqs_filter(cls.get_device_selector_from_pairing_state(True))
        except OSError:
            continue
        for i in range(infos.size):
            try:
                d = await cls.from_id_async(infos.get_at(i).id)
            except OSError:
                continue
            if d is None:
                continue
            try:
                dev = Device(d.bluetooth_address, d.name or "Bluetooth device", le,
                             d.connection_status == 1, _icon_le(d) if le else _icon_classic(d))
                prev = out.get(dev.address)
                if prev is None or (dev.connected and not prev.connected):
                    out[dev.address] = dev
            finally:
                d.close()
    return list(out.values())


# ---------------- battery from Windows (same number Settings shows) ----------------
class DEVPROPKEY(ctypes.Structure):
    _fields_ = [("fmtid", ctypes.c_byte * 16), ("pid", ctypes.c_ulong)]


_BATT = DEVPROPKEY((ctypes.c_byte * 16).from_buffer_copy(uuid.UUID("104EA319-6EE2-4701-BD47-8DDBF425BBE5").bytes_le), 2)


def _all_device_ids() -> list[str]:
    size = ctypes.c_ulong()
    cfg.CM_Get_Device_ID_List_SizeW(ctypes.byref(size), None, 0)
    buf = ctypes.create_unicode_buffer(size.value)
    cfg.CM_Get_Device_ID_ListW(None, buf, size, 0)
    return [s for s in buf[:].split("\0") if s]


def windows_battery(addr_hex: str) -> int | None:
    """Battery % that Windows stores for any device node belonging to this Bluetooth address."""
    key = addr_hex.upper()
    for dev_id in _all_device_ids():
        if not dev_id.upper().startswith(("BTH", "BTHENUM", "BTHLE")) or key not in dev_id.upper():
            continue
        inst = wt.DWORD()
        if cfg.CM_Locate_DevNodeW(ctypes.byref(inst), dev_id, 0) != 0:
            continue
        ptype, val, sz = wt.ULONG(), ctypes.c_ubyte(), wt.ULONG(1)
        if cfg.CM_Get_DevNode_PropertyW(inst, ctypes.byref(_BATT), ctypes.byref(ptype),
                                        ctypes.byref(val), ctypes.byref(sz), 0) == 0:
            return int(val.value)
    return None
