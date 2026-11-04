"""RAWM (MiraclTek) vendor-HID protocol.

Recovered from the RAWM HUB web driver served at https://rawmtech.com/hub.html
(``library.min.js``).  The 64-byte vendor HID collection (usage page 0xFF00,
report id 0) carries a stream of little frames:

    host -> device:  [cmd | size_hi] [size_lo] [sub-type] [data ...]

    device -> host:  the same frame, preceded by the 4-byte resync marker
                     FF FF FF FF, packed into HID reports that start with
                     0x80 | n  (PACKET_TYPE_EVENT_DATA)

Everything the mouse exposes (battery, CPI, polling rate, motion sync, LOD,
angle tuning, ripple control, power mode, lighting, ...) is read through a
single JSON document returned by CMD_QUERY and written through one
CONFIG_TYPE_MOUSE_PARAM structure.  Frames can be wrapped in a CRC16 envelope
(CONFIG_TYPE_CRC) once the device reports ``"crc": 1``.

This module is transport-agnostic for tests: :class:`FrameStream` and the
encoder functions are pure, while :class:`RawmDevice` owns a hidraw fd.
"""

from __future__ import annotations

import copy
import json
import os
import select
import struct
import time
from dataclasses import dataclass, field, replace
from typing import Iterable, Iterator

VID = 0x1915
VENDOR_USAGE_PAGE = b"\x06\x00\xff"
REPORT_SIZE = 64
PACKET_SIZE_MASK = 0x3F
PACKET_TYPE_MASK = 0xC0
PACKET_CHANNEL_MASK = 0x3F
PACKET_TYPE_RAW = 0x00
PACKET_TYPE_BUFFER_SIZE = 0x40
PACKET_TYPE_EVENT_DATA = 0x80
PACKET_TYPE_EXTENDED = 0xC0
MAX_FRAME = 0xFFF

CMD = 0x0
CMD_QUERY = 0x1
CMD_QUERY_RESULT = 0x2
CMD_CONFIG = 0x3
CMD_ACTION = 0x6
CMD_NOTIFY = 0xB
CMD_PING = 0xE

OS_PC = 0x3

CONFIG_TYPE_LIGHT = 0x12
CONFIG_TYPE_MOUSE_KEY = 0x16
CONFIG_TYPE_MOUSE_PARAM = 0x15
CONFIG_TYPE_SET_COLOR_CODE = 0x1F
CONFIG_TYPE_SET_SLEEP_TIME = 0x21
CONFIG_TYPE_CRC = 0x24
CONFIG_TYPE_SET_BRIGHTNESS = 0x31
CONFIG_TYPE_SET_AUTO_HOP = 0x32

ACTION_READ_RSSI = 0x42
ACTION_SAVE_CONFIG_TO_FDS = 0x34
ACTION_REBOOT = 0x33

NOTIFY_CPI = 0x00
NOTIFY_POLLING = 0x01
NOTIFY_LIGHT = 0x02
NOTIFY_ASSIST = 0x03
NOTIFY_POWER_MODE = 0x05
NOTIFY_CPI2 = 0x06
NOTIFY_LOD = 0x07
NOTIFY_KEY_DELAY = 0x08
NOTIFY_MOTION_SYNC = 0x0D
NOTIFY_ANGLE_TUNING = 0x0E
NOTIFY_ANGLE_SNAPPING = 0x0F
NOTIFY_RIPPLE_CONTROL = 0x10
NOTIFY_MOUSE_CONFIG = 0x14
NOTIFY_PEER = 0x15
NOTIFY_BATTERY_LEVELS = 0x16
NOTIFY_BATTERY = 0x17
NOTIFY_SLEEP_TIME = 0x1A
NOTIFY_RSSI = 0x1C
NOTIFY_LUA_STATUS = 0x1D
NOTIFY_GLASS_MODE = 0x21
NOTIFY_ONBOARD_STATUS = 0x23

# light bit-field (device_info["light"])
LED_BLINK = 0x80
LED_ROTATE = 0x40
LED_AUTO_OFF = 0x20
LED_CPI = 0x10
LED_FLAG = 0x08
LED_R = 0x04
LED_G = 0x02
LED_B = 0x01
LED_RGB_MASK = 0x07

COLOR_NAMES = ["Off", "Red", "Green", "Blue", "Yellow", "Purple", "Sky blue", "White"]
COLOR_BITS = {
    "off": 0,
    "red": LED_R,
    "green": LED_G,
    "blue": LED_B,
    "yellow": LED_R | LED_G,
    "purple": LED_R | LED_B,
    "skyblue": LED_G | LED_B,
    "white": LED_R | LED_G | LED_B,
}
COLOR_BITS_TO_NAME = {v: k for k, v in COLOR_BITS.items()}

# Default calibration table used by every RAWM mice seen so far.  The device
# reports its own copy via NOTIFY_BATTERY_LEVELS; this is only a fallback used
# when writing a parameter block before the first notification arrives.
DEFAULT_BATTERY_LEVELS = [4100, 4020, 3900, 3790, 3720, 3670, 3630, 3610, 3560, 3480, 3200]


class ProtocolError(Exception):
    """The device sent something we could not parse."""


class DeviceNotFound(ProtocolError):
    pass


class PermissionDenied(ProtocolError):
    pass


def crc16(data: bytes) -> int:
    """CRC-16/CCITT variant used by the firmware's CONFIG_TYPE_CRC envelope."""
    crc = 0xFFFF
    for byte in data:
        crc = ((crc >> 8) & 0xFF) | ((crc << 8) & 0xFFFF)
        crc ^= byte
        crc ^= (crc & 0xFF) >> 4
        crc ^= (crc << 8) << 4 & 0xFFFF
        crc ^= ((crc & 0xFF) << 4) << 1 & 0xFFFF
        crc &= 0xFFFF
    return crc


def encode_event(cmd: int, subtype: int, data: bytes = b"", crc: bool = False) -> bytes:
    """Build one host->device frame, optionally wrapped in the CRC envelope."""
    size = 3 + len(data)
    if size > MAX_FRAME:
        raise ProtocolError(f"frame too large: {size}")
    inner = bytes([((size >> 8) << 4) | (cmd & 0x0F), size & 0xFF, subtype]) + bytes(data)
    if not crc:
        return inner
    total = len(inner) + 5
    checksum = crc16(inner)
    return (
        bytes(
            [
                ((total >> 8) << 4) | CMD_CONFIG,
                total & 0xFF,
                CONFIG_TYPE_CRC,
                checksum & 0xFF,
                (checksum >> 8) & 0xFF,
            ]
        )
        + inner
    )


@dataclass(frozen=True)
class Frame:
    cmd: int
    size: int
    subtype: int
    data: bytes

    @property
    def payload(self) -> bytes:
        """Frame content including the subtype byte (as the web driver sees it)."""
        return bytes([self.subtype]) + self.data


class FrameStream:
    """Incrementally reassemble device->host frames from raw report payloads."""

    MARKER = b"\xff\xff\xff\xff"

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, payload: bytes) -> list[Frame]:
        self._buf += payload
        out: list[Frame] = []
        while True:
            idx = self._buf.find(self.MARKER)
            if idx < 0:
                # keep enough tail for a marker split across reports
                if len(self._buf) > 3:
                    del self._buf[:-3]
                return out
            if idx:
                del self._buf[:idx]
            if len(self._buf) < 6:
                return out
            size = ((self._buf[4] << 4) & 0xF00) | self._buf[5]
            if size < 3 or size > MAX_FRAME:
                del self._buf[:4]
                continue
            if len(self._buf) < 4 + size:
                return out
            raw = bytes(self._buf[4 : 4 + size])
            del self._buf[: 4 + size]
            out.append(Frame(raw[0] & 0x0F, size, raw[2], raw[3:]))


def report_payloads(report: bytes) -> bytes:
    """Return the event payload inside a 64-byte input report (or b"")."""
    if not report:
        return b""
    kind = report[0] & PACKET_TYPE_MASK
    length = report[0] & PACKET_SIZE_MASK
    if kind in (PACKET_TYPE_EVENT_DATA, PACKET_TYPE_EXTENDED) and length:
        return bytes(report[1 : 1 + length])
    return b""


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


@dataclass
class MouseState:
    """Everything the app displays, mirroring the web driver's device_info."""

    device_name: str = ""
    product_id: int = 0
    vendor_id: int = VID
    firmware: str = ""
    firmware_code: int = 0
    hardware_code: int = 0
    sensor: str = ""
    battery: int = 100
    charging: bool = False
    wired: bool = False
    cpi: int = 1600
    cpi_levels: list[int] = field(default_factory=lambda: [400, 800, 1600, 3200, 0, 0, 0, 0])
    cpi_level_colors: list[int] = field(default_factory=lambda: [LED_R, LED_G, LED_R | LED_G, LED_R, 0, 0, 0, 0])
    polling_rate: int = 1000
    lod: int = 2
    power_mode: int = 2
    motion_sync: int = 0
    angle_tuning: int = 0
    angle_snapping: int = 0
    ripple_control: int = 0
    light: int = LED_CPI | LED_AUTO_OFF
    key_delay: list[int] = field(default_factory=lambda: [8] * 7)
    sleep_time: int = 300
    tx_output_power: int = 0xFF
    auto_tx_power: int = 1
    onboard: int = 0
    onboard_count: int = 4
    onboard_status: list[int] = field(default_factory=list)
    glass_mode: int = 0
    glass_mode_enabled: int = 0
    enhanced_cpi: bool = False
    crc: bool = False
    esb_address: str = ""
    mac_address: str = ""
    config_num: int = 0
    battery_levels: list[int] = field(default_factory=lambda: list(DEFAULT_BATTERY_LEVELS))
    surface_quality: int = 0
    rssi: int | None = None
    via_receiver: bool = False
    receiver_product_id: int | None = None
    rf_channel: int = 2
    hop_channel: bool = True

    @property
    def power_mode_name(self) -> str:
        names = ["Office", "LP (low power)", "HP (high performance)", "Gaming+"]
        return names[self.power_mode] if 0 <= self.power_mode < len(names) else str(self.power_mode)

    @property
    def connection(self) -> str:
        if self.wired:
            return "USB wired"
        return "2.4 GHz wireless"

    @property
    def light_enabled(self) -> bool:
        return bool(self.light & (LED_CPI | LED_RGB_MASK))

    @property
    def light_auto_off(self) -> bool:
        return bool(self.light & LED_AUTO_OFF)

    @property
    def light_static_color(self) -> int:
        return self.light & LED_RGB_MASK


def state_from_query(doc: dict, base: MouseState | None = None) -> MouseState:
    """Build a MouseState from the JSON document returned by CMD_QUERY.

    Every malformed or unexpected reply becomes a ProtocolError.  A partial
    dictionary must never be allowed to escape into a full configuration
    write, and a firmware quirk must not kill the worker thread.
    """
    if not isinstance(doc, dict):
        raise ProtocolError("query reply is not a JSON object")
    # Parse into a copy so a malformed reply cannot partially mutate the
    # previous known-good state (which is used as the write baseline).
    st = copy.deepcopy(base) if base is not None else MouseState()

    def put(attr: str, key: str, transform=lambda v: v) -> None:
        if key not in doc or doc[key] is None:
            return
        try:
            setattr(st, attr, transform(doc[key]))
        except (TypeError, ValueError, IndexError, OverflowError) as exc:
            raise ProtocolError(f"invalid '{key}' in query reply") from exc

    put("device_name", "dn", str)
    put("product_id", "pi", int)
    put("vendor_id", "vi", int)
    put("firmware", "r", str)
    put("firmware_code", "rc", int)
    put("hardware_code", "hw", int)
    put("sensor", "sst", str)
    put("battery", "battery", int)
    put("charging", "chr", lambda v: bool(v))
    put("wired", "wired", lambda v: bool(v))
    put("cpi", "cpi", int)
    put("polling_rate", "polling", int)
    put("light", "light", int)
    put("lod", "lod", int)
    put("power_mode", "pm", int)
    put("motion_sync", "ms", int)
    put("angle_tuning", "at", lambda v: (int(v) << 24) >> 24)  # signed int8
    put("angle_snapping", "as", int)
    put("ripple_control", "rctrl", int)
    put("sleep_time", "st", int)
    put("tx_output_power", "top", int)
    put("auto_tx_power", "atp", int)
    put("onboard", "ob", int)
    put("onboard_count", "ocn", int)
    put("config_num", "cn", int)
    put("enhanced_cpi", "ec", lambda v: bool(v))
    put("crc", "crc", lambda v: bool(v))
    put("mac_address", "addr", str)
    put("esb_address", "esb_addr", str)
    put("rf_channel", "rf_ch", int)
    put("glass_mode", "gm", lambda v: int(v[0]) if isinstance(v, list) else int(v))
    put("glass_mode_enabled", "gm", lambda v: int(v[1]) if isinstance(v, list) else 1)
    put("hop_channel", "hc", lambda v: int(v) != 0xFF)

    def int_list(key: str, limit: int) -> list[int] | None:
        if key not in doc or doc[key] is None:
            return None
        value = doc[key]
        if not isinstance(value, list):
            raise ProtocolError(f"invalid '{key}' in query reply: expected a list")
        try:
            return [int(x) for x in value[:limit]]
        except (TypeError, ValueError, OverflowError) as exc:
            raise ProtocolError(f"invalid '{key}' in query reply") from exc

    cpi_levels = int_list("cpi_l", 8)
    if cpi_levels is not None:
        st.cpi_levels = cpi_levels + [0] * max(0, 8 - len(cpi_levels))
    colors = int_list("cpi_l_c", 8)
    if colors is not None:
        st.cpi_level_colors = [x & LED_RGB_MASK for x in colors] + [0] * max(0, 8 - len(colors))
    delays = int_list("kd", 32)
    if delays is not None:
        st.key_delay = delays
    onboard = int_list("ocs", 32)
    if onboard is not None:
        st.onboard_status = onboard
    return st


def encode_mouse_param(state: MouseState) -> bytes:
    """Serialize MouseState into the CONFIG_TYPE_MOUSE_PARAM payload."""
    out = bytearray()
    res = state.cpi & 0xFFFFFFFF
    use32_res = res > 0xFFFF
    levels = [int(x) & 0xFFFFFFFF for x in state.cpi_levels]
    use32_levels = any(x > 0xFFFF for x in levels)

    # 1. resolution (16-bit form when it fits)
    if use32_res:
        out += b"\x00\x00"
    else:
        out += struct.pack("<H", res)

    # 2. polling rate
    out += struct.pack("<H", clamp(state.polling_rate, 0, 0xFFFF) & 0xFFFF)

    # 3. lighting bit-field
    out.append(state.light & 0xFF)

    # 4. 16-bit CPI levels
    if use32_levels:
        out.append(0)
    else:
        out.append(len(levels) & 0xFF)
        for level in levels:
            out += struct.pack("<H", level & 0xFFFF)

    # 5. onboard profile + power mode
    out.append(state.onboard & 0xFF)
    out.append(state.power_mode & 0xFF)

    # 6. 32-bit resolution (zero when the 16-bit form was used)
    out += struct.pack("<I", 0 if not use32_res else res)

    # 7. 32-bit CPI levels
    if use32_levels:
        out.append(len(levels) & 0xFF)
        for level in levels:
            out += struct.pack("<I", level)
    else:
        out.append(0)

    # 8. LOD
    out.append(state.lod & 0xFF)

    # 9. per-key debounce
    delays = state.key_delay or []
    out.append(len(delays) & 0xFF)
    out += bytes(x & 0xFF for x in delays)

    # 10. sensor features
    out.append(state.motion_sync & 0xFF)
    out.append((state.angle_tuning & 0xFF))
    out.append(state.angle_snapping & 0xFF)
    out.append(state.ripple_control & 0xFF)

    # 11. per-level colours, low 3 bits (RGB)
    colors = state.cpi_level_colors or []
    out.append(len(colors) & 0xFF)
    out += bytes(x & LED_RGB_MASK for x in colors)

    # 12. radio
    out.append(state.tx_output_power & 0xFF)

    # 13. battery calibration (millivolts)
    levels_batt = state.battery_levels or DEFAULT_BATTERY_LEVELS
    out.append(len(levels_batt) & 0xFF)
    for mv in levels_batt:
        out += struct.pack("<H", int(mv) & 0xFFFF)

    out.append(state.auto_tx_power & 0xFF)

    # 14. onboard profile status
    statuses = state.onboard_status or []
    out.append(len(statuses) & 0xFF)
    out += bytes(x & 0xFF for x in statuses)

    # 15. glass mode
    out.append(state.glass_mode_enabled & 0xFF)
    return bytes(out)


def encode_mouse_param_frame(state: MouseState, crc: bool | None = None) -> bytes:
    use_crc = state.crc if crc is None else crc
    return encode_event(CMD_CONFIG, CONFIG_TYPE_MOUSE_PARAM, encode_mouse_param(state), use_crc)


def encode_query_frame(crc: bool = False) -> bytes:
    timestamp = int(time.time())
    data = b"\x00\x00" + timestamp.to_bytes(6, "little")
    return encode_event(CMD_QUERY, OS_PC, data, crc)


def encode_sleep_time_frame(seconds: int, crc: bool = False) -> bytes:
    return encode_event(CMD_CONFIG, CONFIG_TYPE_SET_SLEEP_TIME, struct.pack("<H", int(seconds) & 0xFFFF), crc)


def encode_action_frame(action: int, value: int = 0, crc: bool = False) -> bytes:
    return encode_event(CMD_ACTION, action, struct.pack("<I", value & 0xFFFFFFFF), crc)


@dataclass
class HidrawDevice:
    path: str
    name: str
    product_id: int
    vendor_id: int = VID
    interface: str = ""

    @property
    def hidraw_name(self) -> str:
        return os.path.basename(self.path)


def _read_uevent(dev_path: str) -> dict[str, str]:
    try:
        with open(os.path.join(dev_path, "device", "uevent"), encoding="utf-8") as fh:
            return dict(line.split("=", 1) for line in fh.read().splitlines() if "=" in line)
    except OSError:
        return {}


def discover(vendor_id: int = VID) -> list[HidrawDevice]:
    """Find RAWM vendor HID collections under /sys/class/hidraw."""
    base = "/sys/class/hidraw"
    found: list[HidrawDevice] = []
    try:
        entries = sorted(os.listdir(base))
    except OSError:
        return found

    for name in entries:
        sysdev = os.path.join(base, name)
        uevent = _read_uevent(sysdev)
        hid_id = uevent.get("HID_ID", "").upper()
        # HID_ID=0003:00001915:00002338
        if f":0000{vendor_id:04X}:" not in hid_id:
            continue
        try:
            with open(os.path.join(sysdev, "device", "report_descriptor"), "rb") as fh:
                descriptor = fh.read()
        except OSError:
            continue
        if VENDOR_USAGE_PAGE not in descriptor:
            continue
        try:
            product_id = int(hid_id.split(":")[-1], 16)
        except ValueError:
            product_id = 0
        found.append(
            HidrawDevice(
                path=f"/dev/{name}",
                name=uevent.get("HID_NAME", "RAWM mouse"),
                product_id=product_id,
                vendor_id=vendor_id,
                interface=os.path.basename(os.path.realpath(os.path.join(sysdev, "device"))),
            )
        )
    return found


def find_device(vendor_id: int = VID) -> HidrawDevice:
    devices = discover(vendor_id)
    if not devices:
        raise DeviceNotFound("No RAWM mouse with a vendor HID collection was found")
    # Prefer the collection with a 64-byte report descriptor (all current models).
    for dev in devices:
        try:
            with open(f"/sys/class/hidraw/{dev.hidraw_name}/device/report_descriptor", "rb") as fh:
                desc = fh.read()
        except OSError:
            desc = b""
        if b"\x95\x40" in desc:  # Report Count (64)
            return dev
    return devices[0]


class RawmDevice:
    """Blocking hidraw transport.  One instance must be owned by one thread."""

    def __init__(self, path: str, debug: bool = False, channel: int | None = None) -> None:
        self.path = path
        self.debug = debug
        self.channel = channel
        self.fd = -1
        self.stream = FrameStream()
        self.last_error: str | None = None

    # -- lifecycle ---------------------------------------------------------
    def open(self) -> None:
        if self.fd >= 0:
            return
        try:
            self.fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)
        except PermissionError as exc:
            raise PermissionDenied(
                f"Cannot open {self.path}: permission denied. "
                "Install the udev rule (71-rawm-hid.rules) or run as root."
            ) from exc
        except FileNotFoundError as exc:
            raise DeviceNotFound(f"{self.path} disappeared") from exc

    def close(self) -> None:
        if self.fd >= 0:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = -1

    @property
    def is_open(self) -> bool:
        return self.fd >= 0

    # -- transport ---------------------------------------------------------
    def write_frame(self, frame: bytes) -> None:
        """Send one or more host frames, chunked into 64-byte reports."""
        if self.fd < 0:
            raise ProtocolError("device is not open")
        # Direct link: one report per 63-byte payload chunk, prefixed with
        # PACKET_TYPE_EVENT_DATA | length.  Behind a receiver the packet is
        # wrapped in PACKET_TYPE_EXTENDED | ESB channel and carries one less
        # byte (the web driver's send_client_data()).
        if self.channel is None:
            chunk_size = REPORT_SIZE - 1
            header = b""
        else:
            chunk_size = REPORT_SIZE - 2
            header = bytes([PACKET_TYPE_EXTENDED | (self.channel & 0x3F)])
        for offset in range(0, len(frame), chunk_size):
            chunk = frame[offset : offset + chunk_size]
            report = header + bytes([PACKET_TYPE_EVENT_DATA | len(chunk)]) + chunk
            report += b"\x00" * (REPORT_SIZE - len(report))
            try:
                view = memoryview(report)
                while view:
                    count = os.write(self.fd, view)
                    if count <= 0:
                        raise ProtocolError("short HID write")
                    view = view[count:]
            except OSError as exc:
                raise ProtocolError(f"write failed: {exc}") from exc
            if self.debug:
                print(">>", report.hex(" "))

    def read_ready(self, timeout: float) -> bool:
        if self.fd < 0:
            return False
        ready, _, _ = select.select([self.fd], [], [], timeout)
        return bool(ready)

    def drain(self, timeout: float = 0.0) -> list[Frame]:
        """Read all currently available reports and return complete frames."""
        frames: list[Frame] = []
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            remaining = max(0.0, deadline - time.monotonic())
            if not self.read_ready(remaining if timeout else 0.0):
                break
            try:
                report = os.read(self.fd, REPORT_SIZE + 1)
            except BlockingIOError:
                break
            except OSError as exc:
                self.last_error = str(exc)
                raise ProtocolError(str(exc)) from exc
            if not report:
                break
            if self.debug:
                print("<<", report.hex(" "))
            payload = self._extract_payload(report)
            if payload:
                frames.extend(self.stream.feed(payload))
        return frames

    def _extract_payload(self, report: bytes) -> bytes:
        """Unwrap direct or ESB-channel reports into event-stream bytes."""
        if not report:
            return b""
        kind = report[0] & PACKET_TYPE_MASK
        if kind == PACKET_TYPE_EXTENDED:
            channel = report[0] & PACKET_CHANNEL_MASK
            if self.channel is not None and channel != self.channel:
                return b""  # traffic for another virtual client
            inner = report[1:]
            if not inner:
                return b""
            inner_kind = inner[0] & PACKET_TYPE_MASK
            length = inner[0] & PACKET_SIZE_MASK
            if inner_kind == PACKET_TYPE_BUFFER_SIZE:
                return b""  # receiver flow-control advertisement
            return bytes(inner[1 : 1 + length])
        if kind == PACKET_TYPE_EVENT_DATA and self.channel is None:
            return report_payloads(report)
        return b""

    # -- high level --------------------------------------------------------
    def query_document(self, timeout: float = 1.2) -> tuple[dict | None, list[Frame]]:
        """Send CMD_QUERY and return the raw JSON document plus frames.

        No configuration is written; this is safe for diagnostics.
        """
        self.stream = FrameStream()
        self.write_frame(encode_query_frame())
        frames: list[Frame] = []
        deadline = time.monotonic() + timeout
        doc: dict | None = None
        while time.monotonic() < deadline:
            for frame in self.drain(min(0.2, max(0.0, deadline - time.monotonic()))):
                frames.append(frame)
                if frame.cmd == CMD_QUERY_RESULT and doc is None:
                    raw = frame.payload.rstrip(b"\x00")
                    try:
                        parsed = json.loads(raw)
                    except (ValueError, UnicodeDecodeError) as exc:
                        raise ProtocolError(f"bad query reply: {exc}") from exc
                    if not isinstance(parsed, dict):
                        raise ProtocolError("bad query reply: expected a JSON object")
                    doc = parsed
            if doc is not None and time.monotonic() > deadline - timeout + 0.25:
                break
        # collect anything still queued without blocking
        frames.extend(self.drain(0))
        return doc, frames

    def query(self, timeout: float = 1.2) -> tuple[MouseState | None, list[Frame]]:
        """Send CMD_QUERY and gather the returned JSON + frames."""
        doc, frames = self.query_document(timeout)
        return (state_from_query(doc) if doc is not None else None), frames

    def set_state(self, state: MouseState) -> None:
        self.write_frame(encode_mouse_param_frame(state))

    def set_sleep_time(self, seconds: int, crc: bool = False) -> None:
        self.write_frame(encode_sleep_time_frame(seconds, crc))

    def read_rssi(self, crc: bool = False) -> None:
        self.write_frame(encode_action_frame(ACTION_READ_RSSI, 0, crc))

    def save_to_flash(self, flag: int = 0, crc: bool = True) -> None:
        self.write_frame(encode_action_frame(ACTION_SAVE_CONFIG_TO_FDS, flag, crc))


def apply_notifications(state: MouseState, frames: Iterable[Frame]) -> tuple[MouseState, set[str]]:
    """Update *state* from device notifications; return changed field names."""
    changed: set[str] = set()
    for frame in frames:
        if frame.cmd != CMD_NOTIFY:
            continue
        data = frame.data
        sub = frame.subtype
        if sub == NOTIFY_BATTERY and len(data) >= 1:
            new_battery = data[0]
            if new_battery != state.battery:
                state.battery = new_battery
                changed.add("battery")
            new_charging = len(data) > 1 and data[1] == 1
            if new_charging != state.charging:
                state.charging = new_charging
                changed.add("charging")
        elif sub == NOTIFY_POLLING and len(data) >= 2:
            value = data[0] | (data[1] << 8)
            if value != state.polling_rate:
                state.polling_rate = value
                changed.add("polling_rate")
        elif sub in (NOTIFY_CPI, NOTIFY_CPI2):
            if len(data) >= 2:
                value = data[0] | (data[1] << 8)
                if len(data) >= 4:
                    value |= (data[2] << 16) | (data[3] << 24)
                if value != state.cpi:
                    state.cpi = value
                    changed.add("cpi")
        elif sub == NOTIFY_ASSIST and data:
            if state.surface_quality != data[0]:
                state.surface_quality = data[0]
                changed.add("surface_quality")
        elif sub == NOTIFY_LOD and data:
            if state.lod != data[0]:
                state.lod = data[0]
                changed.add("lod")
        elif sub == NOTIFY_POWER_MODE and data:
            if state.power_mode != data[0]:
                state.power_mode = data[0]
                changed.add("power_mode")
        elif sub == NOTIFY_MOTION_SYNC and data:
            if state.motion_sync != data[0]:
                state.motion_sync = data[0]
                changed.add("motion_sync")
        elif sub == NOTIFY_ANGLE_TUNING and data:
            value = (data[0] << 24) >> 24
            if state.angle_tuning != value:
                state.angle_tuning = value
                changed.add("angle_tuning")
        elif sub == NOTIFY_ANGLE_SNAPPING and data:
            if state.angle_snapping != data[0]:
                state.angle_snapping = data[0]
                changed.add("angle_snapping")
        elif sub == NOTIFY_RIPPLE_CONTROL and data:
            if state.ripple_control != data[0]:
                state.ripple_control = data[0]
                changed.add("ripple_control")
        elif sub == NOTIFY_LIGHT and data:
            if state.light != data[0]:
                state.light = data[0]
                changed.add("light")
        elif sub == NOTIFY_KEY_DELAY:
            delays = list(data)
            if state.key_delay != delays:
                state.key_delay = delays
                changed.add("key_delay")
        elif sub == NOTIFY_SLEEP_TIME and len(data) >= 2:
            value = data[0] | (data[1] << 8)
            if state.sleep_time != value:
                state.sleep_time = value
                changed.add("sleep_time")
        elif sub == NOTIFY_BATTERY_LEVELS and len(data) >= 2:
            levels = [data[i] | (data[i + 1] << 8) for i in range(0, len(data) - 1, 2)]
            if levels and levels != state.battery_levels:
                state.battery_levels = levels
                changed.add("battery_levels")
        elif sub == NOTIFY_RSSI and data:
            value = struct.unpack("b", data[:1])[0]
            if state.rssi != value:
                state.rssi = value
                changed.add("rssi")
        elif sub == NOTIFY_ONBOARD_STATUS:
            statuses = list(data)
            if statuses and statuses != state.onboard_status:
                state.onboard_status = statuses
                changed.add("onboard_status")
        elif sub == NOTIFY_GLASS_MODE and data:
            if state.glass_mode_enabled != data[0]:
                state.glass_mode_enabled = data[0]
                changed.add("glass_mode")
    return state, changed
