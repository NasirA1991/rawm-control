#!/usr/bin/env python3
"""RAWM (MiraclTek) vendor-HID protocol, as recovered from the RAWM HUB web driver.

Wire format
-----------
HID output/input report on the 64-byte vendor collection (usage page 0xFF00,
report id 0):

    byte 0        PACKET_TYPE_EVENT_DATA (0x80) | payload length (<= 63)
    byte 1..      payload

Payload is a byte stream of events, each prefixed with FF FF FF FF and shaped:

    byte 0        command (low nibble) | (frame length >> 8) << 4
    byte 1        frame length & 0xFF
    byte 2        sub-type (CONFIG_TYPE_* or NOTIFY_TYPE_*)
    byte 3..      data

CONFIG_TYPE_MOUSE_PARAM carries the whole performance configuration.
CMD_QUERY gets a JSON description in a CMD_QUERY_RESULT frame.
"""
import json
import os
import select
import time

VID = 0x1915
VENDOR_PAGE = b"\x06\x00\xff"

CMD = 0x0
CMD_QUERY = 0x1
CMD_QUERY_RESULT = 0x2
CMD_CONFIG = 0x3
CMD_ACTION = 0x6
CMD_PING = 0xE
CMD_NOTIFY = 0xB

PACKET_SIZE_MASK = 0x3F
PACKET_TYPE_MASK = 0xC0
PACKET_CHANNEL_MASK = 0x3F
PACKET_TYPE_BUFFER_SIZE = 0x40
PACKET_TYPE_EVENT_DATA = 0x80
PACKET_TYPE_EXTENDED = 0xC0

CONFIG_TYPE_MOUSE_PARAM = 0x15
CONFIG_TYPE_MOUSE_KEY = 0x16
CONFIG_TYPE_MOUSE_FUNCTION = 0x18
CONFIG_TYPE_SET_COLOR_CODE = 0x1F
CONFIG_TYPE_SET_SLEEP_TIME = 0x21
CONFIG_TYPE_CRC = 0x24
CONFIG_TYPE_SET_BRIGHTNESS = 0x31
CONFIG_TYPE_SET_AUTO_HOP = 0x32

ACTION_READ_RSSI = 0x42
ACTION_SAVE_CONFIG_TO_FDS = 0x34

NOTIFY = {
    0x00: "CPI",
    0x01: "POLLING",
    0x02: "LIGHT",
    0x06: "CPI2",
    0x07: "LOD",
    0x08: "KEY_DELAY",
    0x0D: "MOTION_SYNC",
    0x0E: "ANGLE_TUNING",
    0x0F: "ANGLE_SNAPPING",
    0x10: "RIPPLE_CONTROL",
    0x14: "MOUSE_CONFIG",
    0x15: "PEER",
    0x16: "BATTERY_LEVELS",
    0x17: "BATTERY",
    0x1A: "SLEEP_TIME",
    0x1C: "RSSI",
    0x21: "GLASS_MODE",
    0x23: "ONBOARD_STATUS",
}


def find_vendor_hidraw(vid=VID):
    base = "/sys/class/hidraw"
    out = []
    for name in sorted(os.listdir(base)):
        dev = os.path.join(base, name)
        try:
            with open(os.path.join(dev, "device", "report_descriptor"), "rb") as f:
                desc = f.read()
            with open(os.path.join(dev, "device", "uevent")) as f:
                uevent = f.read()
        except OSError:
            continue
        if f"HID_ID=0003:0000{vid:04X}:" not in uevent.upper():
            continue
        if VENDOR_PAGE in desc:
            with open(os.path.join(dev, "device", "uevent")) as f:
                kv = dict(l.split("=", 1) for l in f.read().splitlines() if "=" in l)
            out.append((name, kv.get("HID_NAME", ""), desc))
    return out


class Device:
    def __init__(self, path, debug=False):
        self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        self.stream = bytearray()
        self.debug = debug
        self.reports = []

    def close(self):
        os.close(self.fd)

    def send_event(self, cmd, subtype, data=b""):
        n = 3 + len(data)
        frame = bytes([((n >> 8) << 4) | (cmd & 0x0F), n & 0xFF, subtype]) + bytes(data)
        # Host -> device: frames are just concatenated, no resync prefix.
        payload = frame
        report = bytes([PACKET_TYPE_EVENT_DATA | (len(payload) & PACKET_SIZE_MASK)]) + payload
        report += b"\x00" * (64 - len(report))
        if self.debug:
            print(">>", report.hex(" "))
        os.write(self.fd, report)
        return n

    def send_raw_payload(self, payload):
        """Send a multi-report event stream (payload is chunks of <=63 bytes)."""
        for i in range(0, len(payload), 63):
            chunk = payload[i:i + 63]
            report = bytes([PACKET_TYPE_EVENT_DATA | len(chunk)]) + chunk
            report += b"\x00" * (64 - len(report))
            os.write(self.fd, report)

    def send_query(self):
        # sub-type is OS_PC (3); data is 0,0 + a 6-byte unix timestamp.
        ts = int(time.time())
        data = bytes([0x00, 0x00]) + ts.to_bytes(6, "little")
        return self.send_event(CMD_QUERY, 0x03, data)

    def send_action(self, action, value=0):
        return self.send_event(CMD_ACTION, action, int(value).to_bytes(4, "little"))

    def poll(self, timeout=0.2):
        """Read reports, append event payloads to the stream, return raw reports."""
        got = []
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return got
        while True:
            try:
                report = os.read(self.fd, 256)
            except BlockingIOError:
                break
            except OSError:
                break
            if not report:
                break
            got.append(report)
            self.reports.append(report)
            t = report[0] & PACKET_TYPE_MASK
            n = report[0] & PACKET_SIZE_MASK
            if t in (PACKET_TYPE_EVENT_DATA, PACKET_TYPE_EXTENDED) and n:
                self.stream += report[1:1 + n]
        return got

    def events(self):
        """Yield complete frames from the accumulated stream."""
        while True:
            i = self.stream.find(b"\xff\xff\xff\xff")
            if i < 0:
                # keep a small tail in case a marker is split across reports
                if len(self.stream) > 3:
                    del self.stream[:-3]
                return
            if i:
                del self.stream[:i]
            if len(self.stream) < 6:
                return
            n = ((self.stream[4] << 4) & 0xF00) | self.stream[5]
            if n < 3 or n > 0x0FFF:
                # not a real frame; drop marker and resync
                del self.stream[:4]
                continue
            if len(self.stream) < 4 + n:
                return
            frame = bytes(self.stream[4:4 + n])
            del self.stream[:4 + n]
            yield frame

    def drain_events(self, timeout=1.5):
        end = time.time() + timeout
        while time.time() < end:
            self.poll(min(0.15, max(0, end - time.time())))
        return list(self.events())


def parse_frame(frame):
    cmd = frame[0] & 0x0F
    n = ((frame[0] << 4) & 0xF00) | frame[1]
    subtype = frame[2] if len(frame) > 2 else None
    data = frame[3:]
    return cmd, n, subtype, data


if __name__ == "__main__":
    hits = find_vendor_hidraw()
    print("devices:", hits)
    d = Device(f"/dev/{hits[0][0]}", debug=True)
    d.send_query()
    frames = d.drain_events(3.0)
    print(f"\n{len(frames)} frames")
    for f in frames:
        cmd, n, sub, data = parse_frame(f)
        label = NOTIFY.get(sub, hex(sub)) if cmd == CMD_NOTIFY else ""
        print(f"cmd={cmd} len={n} sub={sub:#04x} {label:14} data={data.hex(' ')}")
        if cmd == CMD_QUERY_RESULT:
            print("   JSON:", data)
    d.close()
