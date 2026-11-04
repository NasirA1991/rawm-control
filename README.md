# RAWM Control

[![CI](https://github.com/NasirA1991/rawm-control/actions/workflows/ci.yml/badge.svg)](https://github.com/NasirA1991/rawm-control/actions/workflows/ci.yml)
[![Release](https://github.com/NasirA1991/rawm-control/actions/workflows/release.yml/badge.svg)](https://github.com/NasirA1991/rawm-control/actions/workflows/release.yml)
[![AUR](https://img.shields.io/aur/version/rawm-control?label=AUR)](https://aur.archlinux.org/packages/rawm-control)
[![AUR git](https://img.shields.io/aur/version/rawm-control-git?label=AUR%20git)](https://aur.archlinux.org/packages/rawm-control-git)


Native **GTK4 / libadwaita** configuration for RAWM gaming mice on Linux — no
browser tab, no Windows VM, no vendor service.

RAWM only ships a WebHID driver (the *RAWM HUB* page) plus Windows/Android
clients. RAWM Control talks to the mouse's 64-byte vendor HID collection
directly, using a protocol recovered from that web driver. It was developed and
verified against an **ER21Pro** (`1915:2338`, firmware `G-1.0.0`, PAW3950),
both over its own link and through the **RAWM HS Receiver** (`1915:232b`).

![Device page](docs/screenshots/device.png)

<sub>Screenshots are rendered by the built-in demo mode (`--demo`).</sub>

> **Hardware status:** only the **ER21Pro** (direct and through an HS Receiver)
> has been verified on physical hardware. Other RAWM models use the same vendor
> HID protocol and capability database, so they are expected to work, but are
> not confirmed. If you have another model, please send a
> [read-only device report](docs/DEVICE_REPORTS.md) — no data is uploaded
> automatically.

## Features

- **Tray icon with live battery** — five selectable designs: *Ring + mouse*,
  *Number only*, *Battery + number*, *Mouse + number* and *Mouse only*. Pick one
  from the tray's **Tray icon** submenu; the choice is remembered. Number-only
  is the most readable on ~16 px panels. Charging state and connection type stay
  in the tooltip, with quick actions for polling rate, DPI, motion sync, angle
  snapping, refresh and quit.
- **Performance** — polling rate adapts to the link (1000 Hz wired/direct, up to
  8000 Hz through an 8K receiver; power-mode caps respected), motion sync,
  ripple control, angle snapping, angle tuning (−30°…+30°), lift-off distance
  with a surface-quality estimate, glass mode, power mode, sleep timer and
  wireless turbo.
- **DPI** — active CPI slider and eight DPI levels with per-level indicator
  colours.
- **Lighting** — DPI-colour indicator, static colour, off, and auto-off when idle.
- **Key delay** — per-button press/release debounce in milliseconds.
- **Hotplug** — detects the dongle, reconnects automatically, survives sleep.
- **CLI** (`rawmctl`) for scripts, keybinds and status bars.
- **Offline and private** — the official driver uploads telemetry
  (`mouse_config.php`); this app never phones home.

![Tray icon styles](docs/screenshots/tray-styles.png)

![Performance](docs/screenshots/performance.png)
![DPI](docs/screenshots/dpi.png)

## Install

Release builds are produced by GitHub Actions and attached to every `v*`
release. Pick the format that matches your system:

| Format | Best for | What it bundles |
|---|---|---|
| **AUR** `rawm-control` / `rawm-control-git` | Arch, CachyOS, EndeavourOS | source; builds against your system |
| **Flatpak** `.flatpak` | any distro with Flatpak | GNOME runtime: Python, GTK4, libadwaita, PyGObject, dbus-python |
| **AppImage** `.AppImage` | quick run anywhere with GTK4 installed | the app only; host provides GTK4/PyGObject |
| **Source tarball** | packaging and auditing | source + install script |

### Arch / CachyOS (AUR)

```bash
paru -S rawm-control-git     # latest main, rebuilt on updates
paru -S rawm-control         # latest tagged release
```

Both are published: [rawm-control](https://aur.archlinux.org/packages/rawm-control)
· [rawm-control-git](https://aur.archlinux.org/packages/rawm-control-git).

`rawm-control-git` tracks `main`; `paru -Syu` rebuilds it with the latest code.

The AUR packages install the udev rule, desktop entry and tray integration.

### Flatpak

Download `rawm-control-<version>-x86_64.flatpak` from the
[Releases page](https://github.com/NasirA1991/rawm-control/releases):

```bash
flatpak install --user ./rawm-control-0.1.4-x86_64.flatpak
flatpak run io.github.rawmcontrol.RawmControl
```

The Flatpak is fully self-contained and exposes `/dev/hidraw*` via
`--device=all`. If the mouse is not detected, make sure the host grants access
to the vendor HID collection (see [Permissions](#permissions)).

> **Sandbox note:** `--device=all` is required for Flatpak's hidraw access and
> grants the sandbox more device access than just this mouse. Native packages
> (AUR/source) are the narrower option if that matters to you.

The Flatpak is distributed self-hosted on GitHub Releases; it is not on
Flathub.

### AppImage

Download `rawm-control-<version>-x86_64.AppImage`, then:

```bash
chmod +x rawm-control-0.1.4-x86_64.AppImage
./rawm-control-0.1.4-x86_64.AppImage
```

The AppImage intentionally bundles only the application. It uses the host's
Python 3, PyGObject, GTK4, libadwaita, pycairo and dbus-python. Install them
with:

```bash
# Arch / CachyOS
sudo pacman -S python-gobject gtk4 libadwaita python-cairo python-dbus hicolor-icon-theme
# Debian / Ubuntu
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-cairo python3-dbus hicolor-icon-theme
# Fedora
sudo dnf install python3-gobject gtk4 libadwaita python3-cairo python3-dbus hicolor-icon-theme
```

A fully self-contained bundle is the Flatpak above. The AppImage intentionally
uses the host's GTK4 stack instead of shipping a large, fragile copy.

### From source

Dependencies: `python python-gobject gtk4 libadwaita python-cairo python-dbus
hicolor-icon-theme`.

```bash
git clone https://github.com/NasirA1991/rawm-control.git
cd rawm-control
./rawm-control --demo          # preview, no mouse required
python3 -m rawm_control        # run from the checkout
sudo ./install.sh              # /usr; installs the udev rule and desktop entry
# or:
./install.sh --user            # ~/.local, no root (udev rule separate)
```

or build a local Arch package:

```bash
makepkg -si
```

## Permissions

The vendor HID collection is `/dev/hidrawN`, usually `root:root` with a udev
`uaccess` ACL. The packaged rule is vendor-wide (`1915`), while the application
itself only opens known mouse products and rejects keyboards/unknown devices.
For system installs the rule is installed automatically:

```
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1915", TAG+="uaccess", MODE="0660"
```

For AppImage/Flatpak or a source run without `sudo ./install.sh`, install it
manually:

```bash
sudo install -m644 data/udev/71-rawm-hid.rules /usr/lib/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
# then unplug/replug the receiver
```

## Usage

```bash
rawm-control                # window + tray
rawm-control --tray         # start minimized
rawm-control --no-tray      # window only
rawm-control --demo         # simulated ER21Pro, no hardware
```

Close the window to keep it running in the tray; **Quit** from the tray menu
(or `Ctrl+Q`) exits.

### CLI

```bash
rawmctl status
rawmctl polling 8000
rawmctl motion-sync on
rawmctl angle-snapping off
rawmctl ripple-control on
rawmctl dpi 1600
rawmctl lod 2
rawmctl power HP
rawmctl sleep 5
rawmctl scan
rawmctl caps
rawmctl report                 # read-only report for a GitHub issue
rawmctl status --json          # identifiers redacted by default
rawmctl status --json --include-identifiers  # local debugging only
```

Setters re-query the mouse and exit non-zero if the device did not confirm the
change, so they are safe to use in scripts.

### Tray on GNOME

GNOME needs an AppIndicator/StatusNotifier extension (for example
*AppIndicator and KStatusNotifierItem Support*). KDE Plasma, XFCE, sway/waybar
and other SNI hosts work out of the box. Flatpak apps need the usual session-bus
access, which the manifest already declares.

## Supported devices

The protocol is shared across the current RAWM family. The bundled capability
table comes from the vendor's own device database. **Hardware verification so
far is limited to the ER21Pro** (direct and through an HS Receiver); the other
rows are supported by the capability database and the same protocol, but have
not been tested on physical units. Reports with model, PID and firmware are
very welcome: open **Device → Diagnostics → Save device report** (or run
`rawmctl report`), review the locally generated file, and attach it to the
[device support issue](https://github.com/NasirA1991/rawm-control/issues/new?template=device-report.yml).
Nothing is uploaded automatically, and MAC/serial fields are redacted. See
[docs/DEVICE_REPORTS.md](docs/DEVICE_REPORTS.md).

| Model | USB ID | Direct / own dongle | With 8K receiver |
|-------|--------|--------------------:|-----------------:|
| ER21 | 1915:233f | 1000 Hz | 8000 Hz |
| ER21M | 1915:2339 | 1000 Hz | 8000 Hz |
| ER21Pro | 1915:2338 | 1000 Hz | 8000 Hz |
| ES11 | 1915:2341 | 1000 Hz | 8000 Hz |
| ES21 | 1915:2333 | 1000 Hz | 8000 Hz |
| ES21M | 1915:2337 | 1000 Hz | 8000 Hz |
| ES21Pro | 1915:2352 / 2349 / 2334 | 1000 Hz | 8000 Hz |
| G11 | 1915:233a | 1000 Hz | 2000 Hz |
| G11Plus | 1915:2343 | 1000 Hz | 2000 Hz |
| G11Pro | 1915:2344 | 1000 Hz | 8000 Hz |
| LEVIATHAN V4 | 1915:234a | 8000 Hz | 8000 Hz |
| SA-MH01 | 1915:232c | 1000 Hz | 8000 Hz |
| SA-MH01Pro | 1915:2331 | 1000 Hz | 8000 Hz |
| SA-ML01 | 1915:2329 | 1000 Hz | 8000 Hz |
| SA-SH01 | 1915:232e | 1000 Hz | 8000 Hz |
| SA-SH01Pro | 1915:2332 | 1000 Hz | 8000 Hz |
| SA-SH01S | 1915:233e | 1000 Hz | 8000 Hz |
| SA-SL01 | 1915:232d | 1000 Hz | 8000 Hz |
| SA-SL01C | 1915:2340 | 1000 Hz | 2000 Hz |
| SADES Dagger | 1915:2348 | 1000 Hz | 8000 Hz |
| RAWM Knife | 1915:2328 | 1000 Hz | 8000 Hz |

“Direct / own dongle” is what the mouse advertises without a separate receiver;
“With 8K receiver” is what the vendor driver adds from a compatible dongle
(e.g. **RAWM HS Receiver `1915:232b`**). The effective maximum also depends on
the receiver model and power mode: **Office = 125 Hz, LP = 1000 Hz**, while
HP/Gaming+ allow the table maximum. The app shows the current rate **and** the
maximum for the current link (`rawmctl status` line: `polling 1000 Hz (max
8000 Hz)`).

**Receiver dongles are supported.** A dongle such as the *RAWM HS Receiver*
(`1915:232b`) describes itself on the direct link; the paired mouse is a virtual
client on ESB channel 0. RAWM Control wraps packets in the extended-channel
header, queries the mouse through the dongle, and writes settings back the same
way. Verified with an HS Receiver + ER21Pro. If the mouse is asleep the app
shows a retry banner instead of inventing values.

Unknown PIDs are treated as read-only diagnostics: the app will not open a
writable mouse session for them. Keyboards and other non-mouse RAWM products are
filtered out for the same reason. `rawmctl scan` lists receivers and their paired
mouse without writing anything.

Configuration writes are applied as **changed fields only**, rebased on a fresh
mouse query immediately before sending, and read back before the UI reports
success. Only known mouse PIDs are writable; unsupported controls are rejected
at the worker layer as well as hidden in the UI.

## Troubleshooting

- **"permission denied"** — install the udev rule above and replug the receiver.
- **"Receiver connected, but the paired mouse is asleep"** — move the mouse or
  turn it on; the app retries automatically.
- **Settings don't stick / flapping** — close the official RAWM HUB browser tab
  or vendor app; two configurators writing at once fight.
- **No tray icon on GNOME** — install an AppIndicator/KStatusNotifierItem
  extension.
- **AppImage won't start** — install the GTK4/PyGObject dependencies above, or
  use the Flatpak.
- **Tray submenu doesn't open on KDE** — update to the latest release; older
  builds lacked the required DBusMenu `AboutToShow` behaviour.

## Development

```bash
python3 -m unittest discover -s tests -v
RAWM_HW_TEST=1 python3 -m unittest tests.test_hardware -v

version=$(python3 -c "from rawm_control.config import VERSION; print(VERSION)")
./packaging/appimage/build.sh "$version" dist
./packaging/flatpak/build.sh "$version" dist
```

`tools/` contains the reverse-engineering helpers:

- `tools/deob.js` — rebuilds the web driver's shuffled string table and
  substitutes all decoder calls.
- `tools/rawm_proto.py` — protocol playground (scan, query, frame dump).
- `tools/tray_mockups.py` / `tools/tray_styles.py` — tray icon renders.

## Contributing

Bug reports, device reports and pull requests are welcome. Run the tests before
sending a change:

```bash
python3 -m unittest discover -s tests -v
```

For a new mouse model, include a
[read-only device report](docs/DEVICE_REPORTS.md) in the issue. Protocol changes
should keep [docs/PROTOCOL.md](docs/PROTOCOL.md) and the tests in sync.

## How it works

```
GTK4 UI ──► DeviceWorker (thread) ──► /dev/hidrawN (vendor HID, 64-byte reports)
                     │                        │
                     └── FrameStream ◄────────┘  FF FF FF FF + frame
```

- `rawm_control/protocol.py` — framing, CRC16, query parsing, parameter block,
  discovery, hidraw transport.
- `rawm_control/worker.py` — owns the fd, coalesces writes, emits state,
  reconnects.
- `rawm_control/tray.py` — StatusNotifierItem + DBusMenu on raw DBus (no GTK3),
  cairo-drawn icons.
- `rawm_control/devices.py` + `data/devices.json` — per-model capabilities.
- [docs/PROTOCOL.md](docs/PROTOCOL.md) — complete protocol write-up.

## Not implemented yet

- Key remapping (Key/Macro/Function/None), the R-Plus secondary layer, onboard
  profile editor with Restore / Apply & onboard.
- X/Y-linked DPI, the X-Polling free-rate slider, RF channel selection and the
  2.4 GHz optimization test.
- Lighting Loop/Customize modes and switchable receiver LEDs.
- Brightness and firmware update / DFU.

The wire protocol for most of these is documented in
[docs/PROTOCOL.md](docs/PROTOCOL.md); they need UI and verification work.

## Disclaimer

This is an independent project. It is not affiliated with, endorsed by or
supported by RAWM or MiraclTek. The protocol was recovered from the publicly
served RAWM HUB web driver; no vendor code is included. Changing device settings
writes to the mouse's firmware-managed configuration — use at your own risk.

## License

MIT. See [LICENSE](LICENSE).
