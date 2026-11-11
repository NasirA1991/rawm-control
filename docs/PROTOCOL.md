# The RAWM vendor HID protocol

This is the protocol implemented by `rawm_control.protocol`, recovered from the
official **RAWM HUB** web driver (`https://rawmtech.com/hub.html`, bundle
`https://hub.miracletek.net/hub/js/library.min.js`). It is shared by the
supported RAWM mouse profiles in the bundled device table and by the vendor's
Windows/Android tools.

> Scope: this documents what was verified on an **ER21Pro** (`1915:2338`,
> firmware `G-1.0.0`, PAW3950). Everything below matches the shipped web
> driver's code; items marked *inferred* have not been exercised on hardware.

## Contents

1. [USB / HID layout](#1-usb--hid-layout)
2. [Report framing](#2-report-framing)
3. [Commands](#3-commands)
4. [Configuration write](#4-configuration-write)
5. [CRC envelope](#5-crc-envelope)
6. [Notifications](#6-notifications)
7. [Receivers and other models](#7-receivers-and-other-models)
8. [Deliberately not implemented](#8-deliberately-not-implemented)
9. [How the web driver was unpacked](#9-how-the-web-driver-was-unpacked)

## 1. USB / HID layout

`lsusb -v` on the ER21Pro dongle:

| Interface | Class | Endpoint | Report descriptor |
|-----------|-------|----------|-------------------|
| 0 | HID, protocol Mouse | IN 0x81, 5 bytes | standard mouse + wheel |
| 1 | HID, protocol Keyboard | IN 0x82, 8 bytes | 6KRO boot keyboard |
| 2 | HID, vendor page `0xFF00` | IN 0x83 / OUT 0x03, 64 bytes | vendor collection |

The vendor interface report descriptor is only 25 bytes:

```text
06 00 FF        Usage Page (Vendor Defined 0xFF00)
09 01           Usage (0x01)
A1 01           Collection (Application)
15 00             Logical Minimum (0)
26 FF 00          Logical Maximum (255)
75 08             Report Size (8)
95 40             Report Count (64)
09 01             Usage (0x01)
81 00             Input  (Data, Array, Abs)     -> 64-byte IN report
09 01             Usage (0x01)
91 00             Output (Data, Array, Abs)     -> 64-byte OUT report
C0              End Collection
```

There are **no report IDs**. `/dev/hidraw*` for this interface is found by
matching `HID_ID=0003:00001915:*` in sysfs *and* a report descriptor containing
`06 00 FF`. Report id 0 is used for both directions.

## 2. Report framing

### Host → device

Each 64-byte output report starts with the packet type and payload length:

```text
byte 0    0x80 | payload_length      (PACKET_TYPE_EVENT_DATA)
byte 1..  concatenated frames
```

If a frame is longer than 63 bytes it is split across several reports; every
report gets its own `0x80 | n` header. There is **no** `FF FF FF FF` prefix and
no report-id byte on this path (tested both ways; the device ignores prefixed
packets).

### Device → host

The device prepends a 4-byte resync marker to **every frame**:

```text
FF FF FF FF   <frame>
```

Frames may straddle report boundaries and several frames may share a report.
`parse_cmd` in the web driver therefore starts at offset 4 of its reassembly
buffer and consumes `frame_length + 4` bytes. Reports whose first byte has the
`0x40` type bit are buffer-size/flow-control packets and can be ignored for
configuration (only relevant when tunnelling through a receiver).

### Frame

```text
byte 0    command (bits 0-3) | ((frame_length >> 8) << 4)
byte 1    frame_length & 0xFF
byte 2    sub-type (CONFIG_TYPE_* or NOTIFY_TYPE_*)
byte 3..  data
```

The length is a 12-bit value stored as a nibble in byte 0 (bits 8-11) plus the
low byte. On the wire the query reply measured 538 bytes and the parameter
block 77+5 bytes, so multi-report reassembly is mandatory.

## 3. Commands

| Value | Name | Purpose |
|-------|------|---------|
| `0x0` | `CMD` | base |
| `0x1` | `CMD_QUERY` | request the JSON device description |
| `0x2` | `CMD_QUERY_RESULT` | reply; payload is raw JSON (the "sub-type" byte is `{`) |
| `0x3` | `CMD_CONFIG` | write configuration |
| `0x6` | `CMD_ACTION` | perform a one-shot action |
| `0x7` | `CMD_SYNC` | resync (not used when `SYNC_BY_CMD_SYNC` is false) |
| `0xB` | `CMD_NOTIFY` | device-initiated notification |
| `0xE` | `CMD_PING` | keepalive / wake |

### Query

```text
3-byte header + sub-type 0x03 (OS_PC) + data: 00 00 <6-byte unix time LE>
```

The mouse answers with one `CMD_QUERY_RESULT` frame containing a JSON object.
Keys observed on the ER21Pro:

| Key | Meaning | Example |
|-----|---------|---------|
| `r` / `rc` | firmware string / revision code | `"G-1.0.0"` / `1` |
| `hw` | hardware code | |
| `dn` / `pi` / `vi` | device name, product id, vendor id | `"ER21Pro"` / `9016` / `6421` |
| `battery` / `chr` | battery percent / charging | `100` / `1` |
| `cpi` | active CPI | `1600` |
| `polling` | polling rate in Hz | `1000` |
| `light` | LED bit-field (see below) | `48` (`0x30`) |
| `cpi_l` | 8 CPI level slots (0 = unused) | `[1600,0,...]` |
| `cpi_l_c` | 8 per-level colour masks | `[6,0,...]` |
| `ob` | active onboard profile | `0` |
| `addr` | MAC | |
| `esb_addr` | paired receiver address(es) | |
| `cn` | config version | `7` |
| `pm` | power mode index | `2` |
| `lod` / `lod_c` | lift-off distance / calibration | `2` / `0` |
| `kd` | per-key debounce | `[34,34,136,...]` |
| `ms` | motion sync | `0` |
| `at` | angle tuning, signed degrees | `0` |
| `as` | angle snapping | `0` |
| `rctrl` | ripple control | `0` |
| `top` / `atp` | TX output power / auto TX power | `8` / `1` |
| `lz`, `lua`, `noack` | compression / Lua / no-ack flags | |
| `st` | sleep timer, seconds | `300` |
| `rf_ch` | RF channel | `2` |
| `crc` | writes must use the CRC envelope | `1` |
| `gm` | glass mode `[mode, enabled]` | `[0,0]` |
| `ocn` / `oci` / `ocs` | onboard config count / index / status | `4` / `0` / `[3,130,134,132]` |
| `ec` / `dgom` | enhanced CPI / dynamic GOM | `1` / `1` |
| `sst` | sensor | `"PAW3950"` |
| `hc` | hop-channel capability (`0xFF` = unsupported) | `255` |
| `wired` | USB cable attached | absent when wireless |

A second notify frame (`NOTIFY_TYPE_MOUSE_ESB_ADDR`, `0x0C`) follows with a JSON
body `{"esb_selected":0,"esb_addr":["..."]}`.

### Polling-rate negotiation (wired vs. receiver)

The UI must not offer rates the current link cannot carry. The web driver's
`get_polling_rates()` / `get_max_polling_rate()` logic is:

1. start with the mouse model's `polling_rates` table;
2. if the mouse is a *virtual client* of a receiver dongle, append the dongle's
   `boost_polling_rates` (an 8K receiver adds 2000/4000/8000);
3. always include powers of two from 125 Hz up to the current rate (so the
   current value stays visible even if it is out of range);
4. clamp the maximum to the model's `polling_rate_max` (default 8000);
5. cap by power mode: Office = 125 Hz, LP = 1000 Hz, HP/Gaming+ = 8000 Hz.

A direct (non-virtual) or USB-wired mouse never gets the receiver boost, so an
ER21Pro on its own dongle or cable tops out at 1000 Hz. Behind the 8K HS
receiver it reaches 8000 Hz on the same firmware. `rawm_control.devices`
reproduces this in `effective_polling_rates()` and `max_polling_rate()`.

`rawm_control.protocol.encode_mouse_param()` stores the rate as a u16, so 8000
is `0x1F40` with no special handling.

## 4. Configuration write

All mouse settings are written as **one** `CONFIG_TYPE_MOUSE_PARAM` (`0x15`)
structure. The official UI simply mutates its local `device_info` object and
resends the whole block.

`CONFIG_TYPE_MOUSE_PARAM` payload, in order (little-endian):

| # | Field | Size | Notes |
|---|-------|------|-------|
| 1 | resolution (16-bit) | 2 | `0,0` when a 32-bit value is used |
| 2 | polling rate | 2 | Hz, e.g. `1000` |
| 3 | light | 1 | bit-field |
| 4 | CPI level count | 1 | 0 when any level needs 32 bits |
| 5 | CPI levels (16-bit) | n×2 | 8 slots on current models |
| 6 | onboard profile | 1 | |
| 7 | power mode | 1 | 0 Office, 1 LP, 2 HP, 3 Gaming+ |
| 8 | resolution (32-bit) | 4 | zero for 16-bit forms |
| 9 | 32-bit CPI levels | 1 + n×4 | count 0 for 16-bit forms |
| 10 | LOD | 1 | 1/2/3 |
| 11 | key-delay count + values | 1 + n | 7 values on ER21Pro |
| 12 | motion sync | 1 | |
| 13 | angle tuning | 1 | signed int8, -30..30 |
| 14 | angle snapping | 1 | |
| 15 | ripple control | 1 | |
| 16 | colour count + masks | 1 + n | masks use low 3 bits (RGB) |
| 17 | TX output power | 1 | |
| 18 | battery-level count + mV | 1 + n×2 | 11 calibration points |
| 19 | auto TX power | 1 | |
| 20 | onboard-status count + bytes | 1 + n | 4 bytes on ER21Pro |
| 21 | glass-mode enabled | 1 | |

For the ER21Pro this is **82 bytes**, giving a 77-byte frame.

### LED bit-field

| Bit | Name | Meaning |
|-----|------|---------|
| `0x80` | `LED_BLINK` | blink |
| `0x40` | `LED_ROTATE` | rotate |
| `0x20` | `LED_AUTO_OFF` | turn off when idle |
| `0x10` | `LED_CPI` | use per-level CPI colours |
| `0x08` | `LED_FLAG` | "apply lighting change" flag |
| `0x04/0x02/0x01` | R/G/B | static colour; `6` = yellow, `3` = sky blue |

The web driver ORs `LED_FLAG` when it changes lighting; queries return the field
without that bit.

### Key delay encoding

`kd` is one byte per button. The **low nibble is the press delay** and the
**high nibble is the release delay**, both in milliseconds (0–10). Example:
`0x22` = 2 ms press, 2 ms release; `0x88` = 8 ms / 8 ms. The vendor UI edits
these nibbles in place and resends the full parameter block.

## 5. CRC envelope

When the query says `"crc": 1`, **configuration** frames are wrapped:

```text
03 | total_len            (CMD_CONFIG, top nibble = len bits 8-11)
24                        CONFIG_TYPE_CRC
crc16_lo crc16_hi         over the inner frame (length-prefixed)
<inner frame>
```

The CRC is a CRC-16/CCITT-style variant (init `0xFFFF`, no table):

```python
crc = 0xFFFF
for b in buf:
    crc = ((crc >> 8) & 0xFF) | ((crc << 8) & 0xFFFF)
    crc ^= b
    crc ^= (crc & 0xFF) >> 4
    crc ^= ((crc << 8) << 4) & 0xFFFF
    crc ^= ((crc & 0xFF) << 4) << 1 & 0xFFFF
    crc &= 0xFFFF
```

Verified against the exact `crc16_compute` from `library.min.js`
(`crc16(b"\x01\x02\x03") == 0xADAD`). Queries are accepted without the envelope
even when `crc` is 1, but writes are wrapped.

Motion-sync round trip was verified on hardware: encode the full block with
`ms=1`, send, re-query, and the mouse reports `"ms":1`. Repeating with `ms=0`
restores it.

## 6. Notifications

`CMD_NOTIFY` frames arrive unsolicited; sub-types match `NOTIFY_TYPE_*`:

| Type | Data |
|------|------|
| `0x00` / `0x06` | CPI (16/32-bit LE) |
| `0x01` | polling rate (u16 LE) |
| `0x02` | lighting bit-field |
| `0x03` | surface quality, link equaliser, applied TX power |
| `0x05` | power mode |
| `0x07` | LOD |
| `0x08` | key delay array (one packed byte per button) |
| `0x0C` | ESB address JSON |
| `0x0D` / `0x0E` / `0x0F` / `0x10` | motion sync / angle tuning (s8) / snapping / ripple |
| `0x14` | onboard profile/config dump, terminated by `0xFF` |
| `0x15` | peer info |
| `0x16` | battery calibration (u16 mV pairs) |
| `0x17` | battery percent, charging |
| `0x1A` | sleep timer (u16 seconds) |
| `0x1C` | RSSI (s8 dBm, after `ACTION_READ_RSSI`) |
| `0x23` | onboard status |

Actions (`CMD_ACTION`, u32 LE argument): `0x42` read RSSI, `0x34` save config to
flash (used for onboard profiles), `0x33` reboot, `0x3F` shutdown to DFU.

## 7. Receivers and other models

A receiver dongle (PIDs `0x232A`, `0x232B`, `0x2335`, `0x233C`, ...) presents the
vendor collection but forwards packets to the paired mouse over Nordic ESB. The
web driver then wraps packets as:

```text
byte 0    0xC0 | ESB channel       (PACKET_TYPE_EXTENDED)
byte 1    0x80 | payload length    (inner report header)
byte 2..  event stream for that channel
```

Payload chunks shrink to 62 bytes because of the extra channel byte. The reply
uses the same wrapper; inner `0x40` packets are receiver buffer-size
advertisements and are ignored.

A query sent directly to the dongle returns only the dongle's identity, e.g.
`{"r":"G-1.8.0","dn":"RAWM HS Receiver","pi":9003,"esb_ch":255,...}`. The web
driver then creates a virtual client on channel 0 (`ESB_CHANNEL_MOUSE`), queries
it, and treats the reply as the mouse. RAWM Control does the same:

1. query the dongle directly (identifies it and proves it is alive),
2. set `channel = 0`,
3. query again; the reply is the paired mouse's JSON (here an ER21Pro),
4. all subsequent parameter writes go through the channel wrapper.

This path was verified with a RAWM HS Receiver (`1915:232b`) and an ER21Pro:
`rawmctl status` reports the ER21Pro with 100 % battery, and a motion-sync write
through the dongle was confirmed by re-query. If the mouse is asleep the dongle
answers the extended packet only with a buffer-size report; the app keeps the
banner "Receiver connected, but the paired mouse is asleep" and retries instead
of showing the dongle's placeholder fields.

Multiple dongles/mice could be multiplexed by keeping one `FrameStream` per
channel; the UI currently connects to one mouse at a time and prefers a directly
connected mouse over a receiver.

## 8. Deliberately not implemented

This is the wire-level gap list; the user-facing summary is in the
[README limitations](../README.md#limitations).

- Key remapping, macros and onboard-profile editing (`CONFIG_TYPE_MOUSE_KEY`,
  `_MOUSE_FUNCTION`, macro segments)
- Firmware update / DFU
- DPI-XY and brightness (`CONFIG_TYPE_SET_BRIGHTNESS`)
- The vendor's telemetry upload (`mouse_config.php`); this app never phones home

## 9. How the web driver was unpacked

`library.min.js` is obfuscated with a shuffled plaintext string table
(`_0x1d36`) indexed through `_0x70bc(index - 0x139)`. `tools/deob.js` evaluates
the decoder in a `vm` sandbox, discovers every alias of the decoder, substitutes
all 9,062 call sites, then Prettier formats the result. Running the bundle's own
rotating-array checksum is required, which the script does. The recovered
constants (`CMD_*`, `CONFIG_TYPE_*`, `NOTIFY_TYPE_*`, the device PID table,
packet framing and the full parameter-block writer) are readable in the
formatted output and were re-implemented here; no vendor code is shipped.
