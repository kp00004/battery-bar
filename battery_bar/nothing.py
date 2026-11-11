"""Nothing / CMF earbuds: left, right and case battery + which bud is in the case.

Talks the buds' own control protocol over RFCOMM (what the Nothing X app uses). Frame format and
battery command from Gadgetbridge's Nothing support (https://gadgetbridge.org); position events
(0xE002) worked out with this project's listener on CMF Buds 2.

  frame   = 0x55 | control u16 | command u16 | length u16 | seq u8 | payload | crc16 (if control & 0x20)
  battery = request 0xC007 (control 0x5120), push 0xE001: n, then n x {id, value}
            id 2 = left, 3 = right, 4 = case; value & 0x7F = %, & 0x80 = charging
  position push 0xE002: n, then n x {id, state}; here id 3 = left, 2 = right, state 1 = in case, 2 = out
"""
import asyncio
import re
import struct
import time
import uuid

from winrt.windows.devices.bluetooth import BluetoothCacheMode, BluetoothDevice
from winrt.windows.devices.bluetooth.rfcomm import RfcommServiceId
from winrt.windows.networking.sockets import StreamSocket
from winrt.windows.storage.streams import DataReader, DataWriter, InputStreamOptions

CTRL_UUID = uuid.UUID("aeac4a03-dff5-498f-843a-34487cf133eb")
NAME_RE = re.compile(r"(?i)^(nothing\b|cmf buds|ear ?\()")
_BATT_IDS = {2: "L", 3: "R", 4: "case"}
_POS_IDS = {3: "L", 2: "R"}


def is_nothing(name: str) -> bool:
    return bool(NAME_RE.search(name or ""))


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def frame(control: int, command: int, payload: bytes = b"") -> bytes:
    m = struct.pack("<BHHHB", 0x55, control, command, len(payload), 0) + payload
    return m + struct.pack("<H", crc16(m))


BATTERY_REQ = frame(0x5120, 0xC007)


class BudsState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.link = False
        self.bat = {}          # "L"/"R"/"case" -> (level, charging)
        self.pos = {}          # "L"/"R" -> "case" | "out"
        self.case_stale = False

    def feed(self, cmd: int, pl: bytes, log=lambda *a: None):
        if cmd in (0xE001, 0xC007) and pl:
            b = {}
            for k in range(pl[0]):
                pid, val = pl[1 + 2 * k], pl[2 + 2 * k]
                if pid in _BATT_IDS:
                    b[_BATT_IDS[pid]] = (val & 0x7F, bool(val & 0x80))
            self.case_stale = "case" not in b
            self.bat = {**self.bat, **b}
            log("buds battery", self.bat)
        elif cmd == 0xE002 and pl:
            for k in range(pl[0]):
                pid, val = pl[1 + 2 * k], pl[2 + 2 * k]
                if pid in _POS_IDS:
                    self.pos[_POS_IDS[pid]] = "case" if val & 0x03 == 1 else "out"
            log("buds position", self.pos)


async def session(address: int, st: BudsState, reask_s: float, refresh, log=lambda *a: None) -> bool:
    """Hold the control link while the buds are connected. Returns False if the device has no such service."""
    dev = await BluetoothDevice.from_bluetooth_address_async(address)
    if dev is None:
        return True
    sock = None
    try:
        if dev.connection_status != 1:
            return True
        res = await dev.get_rfcomm_services_for_id_async(RfcommServiceId.from_uuid(CTRL_UUID),
                                                          BluetoothCacheMode.UNCACHED)
        if not res.services or res.services.size == 0:
            return False
        svc = res.services.get_at(0)
        sock = StreamSocket()
        await sock.connect_async(svc.connection_host_name, svc.connection_service_name)
        w, r = DataWriter(sock.output_stream), DataReader(sock.input_stream)
        r.input_stream_options = InputStreamOptions.PARTIAL
        q: asyncio.Queue = asyncio.Queue()

        async def reader():
            try:
                while True:
                    n = await r.load_async(512)
                    if not n:
                        break
                    c = bytearray(n)
                    r.read_bytes(c)
                    await q.put(bytes(c))
            except Exception:
                pass
            await q.put(None)

        async def ask():
            w.write_bytes(BATTERY_REQ)
            await w.store_async()

        rt = asyncio.ensure_future(reader())
        st.link = True
        log("buds link up", hex(address))
        await ask()
        buf, last = b"", time.monotonic()
        while True:
            try:
                chunk = await asyncio.wait_for(q.get(), 1.0)
            except asyncio.TimeoutError:
                chunk = b""
            if chunk is None:
                break
            buf += chunk
            i = 0
            while i + 8 <= len(buf):
                if buf[i] != 0x55:
                    i += 1
                    continue
                control, command, length = struct.unpack_from("<HHH", buf, i + 1)
                end = i + 8 + length + (2 if control & 0x20 else 0)
                if end > len(buf):
                    break
                if control & 0x1F == 0:
                    st.feed(command | 0x8000, buf[i + 8:i + 8 + length], log)
                i = end
            buf = buf[i:]
            if refresh() or time.monotonic() - last > reask_s:
                await ask()
                last = time.monotonic()
        rt.cancel()
        return True
    except Exception as e:
        log("buds session error", e)
        return True
    finally:
        st.reset()
        log("buds link down", hex(address))
        if sock:
            sock.close()
        dev.close()
