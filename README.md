# RAWM Control

<p align="center">
  <img src="data/icons/rawm-control-256.png" width="128" alt="RAWM Control icon">
</p>

[![CI](https://github.com/NasirA1991/rawm-control/actions/workflows/ci.yml/badge.svg)](https://github.com/NasirA1991/rawm-control/actions/workflows/ci.yml)
[![Release](https://github.com/NasirA1991/rawm-control/actions/workflows/release.yml/badge.svg)](https://github.com/NasirA1991/rawm-control/actions/workflows/release.yml)
[![AUR](https://img.shields.io/aur/version/rawm-control?label=AUR)](https://aur.archlinux.org/packages/rawm-control)
[![AUR git](https://img.shields.io/aur/version/rawm-control-git?label=AUR%20git)](https://aur.archlinux.org/packages/rawm-control-git)

Native **GTK4 / libadwaita** configuration for RAWM gaming mice on Linux — no
browser tab, no Windows VM, no vendor service.

RAWM only ships a WebHID driver (the *RAWM HUB* page) plus Windows/Android
clients. RAWM Control talks to the mouse's 64-byte vendor HID collection
directly, using a protocol recovered from that web driver. It was developed and
verified against an **ER21Pro** (`1915:2338`), both over its own link and through
the **RAWM HS Receiver** (`1915:232b`).

![Device page](docs/screenshots/device.png)

<sub>Screenshots are rendered by the built-in demo mode (`--demo`).</sub>

> **Hardware status:** only the **ER21Pro** has been verified on physical
> hardware. Other RAWM models use the same protocol and capability database,
> but are not confirmed. [Send a read-only device report](docs/DEVICE_REPORTS.md)
> if you have another model.

> **Development disclosure:** RAWM Control was built with AI assistance. It is
> an independent project and is not affiliated with RAWM or MiraclTek.

## Quick install

**Arch, CachyOS or EndeavourOS:** use `paru`, `yay`, or any other AUR helper.

```bash
paru -S rawm-control       # stable release; yay -S rawm-control works too
paru -S rawm-control-git   # latest main
```

**Other distributions:** download the latest AppImage or Flatpak from the
[releases page](https://github.com/NasirA1991/rawm-control/releases/latest), or
see [Installation](#installation) for dependencies and source builds.

**On this page:** [Features](#features) · [Installation](#installation)
· [Permissions](#permissions) · [Usage](#usage)
· [Supported devices](#supported-devices) · [Limitations](#limitations)
· [Troubleshooting](#troubleshooting) · [Contributing](#contributing)

## Features

- **Tray battery** — five icon designs, including *Number only* for small
  panels, with quick actions and charging/connection state in the tooltip.
- **Performance** — polling rate (up to 8000 Hz through an 8K receiver), motion
  sync, ripple control, angle snapping/tuning, lift-off distance, glass mode,
  power mode, sleep timer and wireless turbo.
- **DPI** — active CPI slider and eight DPI levels with indicator colours.
- **Lighting** — DPI-colour indicator, static colour, off and auto-off.
- **Key delay** — per-button press/release debounce.
- **Recovery** — restore the settings detected on connection; reset local app
  preferences without touching the mouse.
- **CLI** — `rawmctl` for scripts, keybinds and status bars.
- **Private** — no telemetry, accounts or cloud.

![Tray icon styles](docs/screenshots/tray-styles.png)

![Performance](docs/screenshots/performance.png)
![DPI](docs/screenshots/dpi.png)

## Installation

| Format | Best for | Includes |
|---|---|---|
| **AUR** `rawm-control` / `rawm-control-git` | Arch, CachyOS, EndeavourOS | source built against your system |
| **Flatpak** `.flatpak` | any distro with Flatpak | GNOME runtime with Python, GTK4 and libadwaita |
| **AppImage** `.AppImage` | trying it without installing | the app; uses your system GTK4 |
| **Source** | packaging and development | source and install script |

### Arch / CachyOS (AUR)

Any AUR helper works. For example:

```bash
paru -S rawm-control       # latest tagged release
paru -S rawm-control-git   # latest main
# yay -S rawm-control / rawm-control-git
```

The packages install the udev rule, desktop entry and tray integration.
`rawm-control-git` tracks `main`; `paru -Syu` / `yay -Syu` rebuilds it.

### Flatpak

Download the `.flatpak` from the [releases page](https://github.com/NasirA1991/rawm-control/releases/latest), then:

```bash
flatpak install --user ./rawm-control-*.flatpak
flatpak run io.github.rawmcontrol.RawmControl
```

The Flatpak is self-contained and exposes `/dev/hidraw*` through
`--device=all`. Native packages give narrower device access; see
[Permissions](#permissions). It is not distributed through Flathub.

### AppImage

Download the `.AppImage`, then:

```bash
chmod +x rawm-control-*.AppImage
./rawm-control-*.AppImage
```

The AppImage uses the host's Python 3, GTK4, libadwaita, PyGObject, pycairo and
dbus-python. Install those first:

```bash
# Arch / CachyOS
sudo pacman -S python-gobject gtk4 libadwaita python-cairo python-dbus hicolor-icon-theme
# Debian / Ubuntu
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-cairo python3-dbus hicolor-icon-theme
# Fedora
sudo dnf install python3-gobject gtk4 libadwaita python3-cairo python3-dbus hicolor-icon-theme
```

Use the Flatpak if you want a fully bundled runtime.

### From source

Dependencies: `python python-gobject gtk4 libadwaita python-cairo python-dbus
hicolor-icon-theme`.

```bash
git clone https://github.com/NasirA1991/rawm-control.git
cd rawm-control
./rawm-control --demo       # preview without a mouse
python3 -m rawm_control     # run from the checkout
sudo ./install.sh           # /usr, including the udev rule
# or:
./install.sh --user         # ~/.local, no root (udev rule separate)
```

Or build a local Arch package with `makepkg -si`.

## Permissions

The vendor HID collection is `/dev/hidrawN`, normally `root:root` with a udev
`uaccess` ACL. The rule is vendor-wide (`1915`), while the app itself only opens
known mouse products and rejects keyboards/unknown devices.

For a source or AppImage install, add the rule once (the source copy is at
`data/udev/71-rawm-hid.rules`):

```bash
echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1915", TAG+="uaccess", MODE="0660"' \
  | sudo tee /usr/lib/udev/rules.d/71-rawm-hid.rules >/dev/null
sudo udevadm control --reload-rules && sudo udevadm trigger
# unplug/replug the receiver
```

System/AUR installs do this automatically. Flatpak uses `--device=all`, which is
broader than the udev rule; use the AUR or source package if you prefer narrower
device access.

## Usage

```bash
rawm-control                # window + tray
rawm-control --tray         # start minimized
rawm-control --no-tray      # window only
rawm-control --demo         # simulated ER21Pro
```

Closing the window keeps the app in the tray. **Quit** from the tray menu or
press `Ctrl+Q` to exit.

### CLI

```bash
rawmctl status
rawmctl polling 8000
rawmctl motion-sync on
rawmctl dpi 1600
rawmctl power HP
rawmctl sleep 5
rawmctl scan
rawmctl report                 # read-only report for a GitHub issue
rawmctl status --json          # identifiers redacted
```

Setters read back the value and exit non-zero if the mouse did not confirm the
change.

### Tray

Left-click opens the window; right-click opens the context menu. Some GNOME
AppIndicator extensions always show the menu on primary click. GNOME needs an
AppIndicator/KStatusNotifierItem extension; KDE Plasma, XFCE and most other SNI
hosts work directly.

## Supported devices

The app covers the RAWM family through the vendor capability database. **Only
the ER21Pro is hardware-verified.** See
[docs/DEVICES.md](docs/DEVICES.md) for every model, USB ID and polling limit.

Receiver dongles are supported. Unknown PIDs and keyboards are read-only: the
app will not send mouse configuration to them. To help verify another model,
use **Device → Diagnostics → Save device report**, review the file and attach
it to a [device support issue](https://github.com/NasirA1991/rawm-control/issues/new?template=device-report.yml).
Nothing is uploaded automatically.

## Limitations

Not implemented yet:

- key remapping, macros, R-Plus layer and onboard-profile editing;
- X/Y-linked DPI, free-rate polling, RF channel selection and the 2.4 GHz test;
- Lighting Loop/Customize modes and receiver LEDs;
- brightness and firmware update/DFU.

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/PROTOCOL.md](docs/PROTOCOL.md)
for the technical details.

## Troubleshooting

- **Permission denied** — install the udev rule above and replug the receiver.
- **Mouse asleep** — move it or turn it on; the receiver banner has a Retry
  button.
- **Settings don't stick** — close RAWM HUB or any other configurator; two
  writers conflict.
- **No tray icon on GNOME** — install an AppIndicator extension.
- **AppImage won't start** — install the GTK4/PyGObject dependencies above, or
  use the Flatpak.
- **Tray menu issues on KDE** — update to the latest release.

## Contributing

Bug reports, device reports and pull requests are welcome. See
[CONTRIBUTING.md](CONTRIBUTING.md) for tests, local builds and architecture.
Protocol changes should keep [docs/PROTOCOL.md](docs/PROTOCOL.md) and the tests
in sync.

## Disclaimer

RAWM Control is an independent project, not affiliated with or supported by RAWM
or MiraclTek. The protocol was recovered from the publicly served RAWM HUB web
driver; no vendor code is included. Changing mouse settings writes to
firmware-managed configuration — use at your own risk.

## License

MIT. See [LICENSE](LICENSE).
