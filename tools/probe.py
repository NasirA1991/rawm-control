#!/usr/bin/env python3
"""Minimal RAWM / MiraclTek vendor-HID probe.

Talks to the 64-byte vendor collection (usage page 0xFF00) of a RAWM mouse
to validate the packet framing recovered from the RAWM HUB web driver.
"""
import os
import select
import struct
import sys
import time

VID = 0x1915
VENDOR_PAGE = b"\x06\x00\xff"


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
            out.append((name, desc))
    return out


def open_hidraw(name):
    return os.open(f"/dev/{name}", os.O_RDWR | os.O_NONBLOCK)


def drain(fd, timeout=0.15):
    end = time.time() + timeout
    chunks = []
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], max(0, end - time.time()))
        if not r:
            break
        try:
            chunks.append(os.read(fd, 256))
        except BlockingIOError:
            time.sleep(0.005)
        except OSError as e:
            chunks.append(f"ERR {e}".encode())
            break
    return chunks


def send(fd, payload, lead_zero=False):
    # read_event(): byte0 = PACKET_TYPE_EVENT_DATA | payload length.
    frame = bytes([0x80 | (len(payload) & 0x3F)]) + bytes(payload)
    frame += b"\x00" * (64 - len(frame))
    if lead_zero:
        frame = b"\x00" + frame
    try:
        n = os.write(fd, frame)
        return f"wrote {n}/{len(frame)}"
    except OSError as e:
        return f"write failed: {e}"


def main():
    hits = find_vendor_hidraw()
    if not hits:
        print("no vendor-page hidraw device for 1915 found")
        return 2
    for name, desc in hits:
        print(f"found {name} descriptor={desc.hex()}")

    name = hits[0][0]
    fd = open_hidraw(name)
    print(f"opened /dev/{name}")

    # Query packet: CMD_QUERY, 0, OS_PC, 0, 0, then a 6-byte timestamp.
    ts = int(time.time())
    payload = [0x01, 0x00, 0x03, 0x00, 0x00]
    for i in range(6):
        payload.append((ts >> (8 * i)) & 0xFF)
    # crc_process(): the frame is length-prefixed inside the packet.
    n = len(payload)
    payload[0] = ((n >> 4) & 0xF0) | 0x01
    payload[1] = n & 0xFF
    print("query payload:", bytes(payload).hex())

    for lead_zero in (False, True):
        print(f"-- send lead_zero={lead_zero}")
        print(send(fd, payload, lead_zero))
        for ch in drain(fd, 1.2):
            print("  recv", ch.hex(" "), "|", ch[1:].decode("ascii", "replace").replace("\x00", ".")[:60])
        time.sleep(0.2)
    os.close(fd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
