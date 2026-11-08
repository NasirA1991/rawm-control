# Contributing

Bug reports, device reports and pull requests are welcome.

## Tests

Install the same system test dependencies CI uses (Debian/Ubuntu naming):

```bash
sudo apt install python3-dbus python3-cairo python3-gi \
  gir1.2-gtk-4.0 gir1.2-adw-1 libgtk-4-1 libadwaita-1-0
```

Then run:

```bash
python3 -m unittest discover -s tests -v
RAWM_HW_TEST=1 python3 -m unittest tests.test_hardware -v
```

The hardware tests are opt-in. Device reports are more useful than a generic
"it doesn't work" issue; see [docs/DEVICE_REPORTS.md](docs/DEVICE_REPORTS.md).

## Build the release artifacts

```bash
version=$(python3 -c "from rawm_control.config import VERSION; print(VERSION)")
./packaging/appimage/build.sh "$version" dist
./packaging/flatpak/build.sh "$version" dist
```

The AppImage build uses a pinned appimagetool release and verifies its SHA-256.
The Flatpak manifest needs the GNOME 50 runtime and SDK.

## Architecture

```
GTK4 UI ──► DeviceWorker (thread) ──► /dev/hidrawN (vendor HID, 64-byte reports)
                     │                        │
                     └── FrameStream ◄────────┘  FF FF FF FF + frame
```

- `rawm_control/protocol.py` — framing, CRC16, query parsing, parameter block,
  discovery and hidraw transport.
- `rawm_control/worker.py` — owns the fd, rebases and verifies writes, emits
  state and reconnects.
- `rawm_control/tray.py` — StatusNotifierItem + DBusMenu over raw DBus;
  cairo-drawn icons.
- `rawm_control/devices.py` + `rawm_control/data/devices.json` — per-model
  capabilities.
- [docs/PROTOCOL.md](docs/PROTOCOL.md) — protocol write-up.

`tools/` contains the reverse-engineering helpers:

- `tools/deob.js` — rebuilds the web driver's shuffled string table and
  substitutes all decoder calls.
- `tools/rawm_proto.py` — protocol playground (scan, query, frame dump).
- `tools/tray_mockups.py` / `tools/tray_styles.py` — tray icon renders.

## Scope

Not implemented yet:

- key remapping, macros, the R-Plus secondary layer and onboard-profile editing;
- X/Y-linked DPI, the X-Polling free-rate slider, RF channel selection and the
  2.4 GHz optimization test;
- Lighting Loop/Customize modes and switchable receiver LEDs;
- brightness and firmware update/DFU.

The wire protocol for most of these is documented in
[docs/PROTOCOL.md](docs/PROTOCOL.md); they need UI and verification work.

## Development disclosure

This project was built with AI assistance. Keep that in mind when reviewing
changes, and test hardware-affecting changes on a real device before merging.
