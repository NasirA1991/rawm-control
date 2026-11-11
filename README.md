# RAWM Control

<p align="center">
  <img src="data/icons/rawm-control-256.png" width="112" alt="RAWM Control icon">
</p>

[![CI](https://github.com/NasirA1991/rawm-control/actions/workflows/ci.yml/badge.svg)](https://github.com/NasirA1991/rawm-control/actions/workflows/ci.yml)
[![Release](https://github.com/NasirA1991/rawm-control/actions/workflows/release.yml/badge.svg)](https://github.com/NasirA1991/rawm-control/actions/workflows/release.yml)
[![AUR](https://img.shields.io/aur/version/rawm-control?label=AUR)](https://aur.archlinux.org/packages/rawm-control)
[![AUR git](https://img.shields.io/aur/version/rawm-control-git?label=AUR%20git)](https://aur.archlinux.org/packages/rawm-control-git)

RAWM Control is a native **GTK4 / libadwaita** configuration app for RAWM
gaming mice on Linux. It talks directly to the mouse's vendor HID interface, so
you do not need a browser tab, a Windows VM, or the vendor's background service.

RAWM currently provides a WebHID configurator and Windows/Android clients. The
protocol used here was recovered from the public RAWM HUB web driver. The app
was developed and tested against an **ER21Pro** (`1915:2338`), both on its own
link and through the **RAWM HS Receiver** (`1915:232b`).

> **Hardware status:** the ER21Pro is the only model verified on physical
> hardware. Other models in the bundled device database use the same protocol
> but are marked **UNVERIFIED MODEL** in the app. A read-only
> [device report](docs/DEVICE_REPORTS.md) helps confirm them.
>
> **Project disclosure:** RAWM Control was built with AI assistance. It is an
> independent project, not affiliated with or supported by RAWM or MiraclTek.

## Quick start

**Arch, CachyOS or EndeavourOS:** install the stable package from the AUR.

```bash
paru -S rawm-control
# or: yay -S rawm-control
```

**Other distributions:** use the Flatpak or AppImage from the
[latest release](https://github.com/NasirA1991/rawm-control/releases/latest).
The [installation guide](docs/INSTALL.md) covers dependencies, permissions,
updates and uninstall instructions.

**On this page:** [Features](#features) · [Screenshots](#screenshots)
· [Installation](#installation) · [Permissions](#permissions) · [Usage](#usage)
· [Supported devices](#supported-devices) · [Limitations](#limitations)
· [Troubleshooting](#troubleshooting) · [Documentation](#documentation)

## Features

- **Battery and tray** — battery level, charging state and connection status in
  the tray; five icon styles (`ring`, `number`, `battery`, `sidecar`, `mouse`),
  with a charging bolt and a Passive state when no mouse is connected.
- **Performance** — polling rate, motion sync, ripple control, angle snapping
  and tuning, lift-off distance, glass mode, power mode, sleep timer and
  wireless turbo where the model supports them.
- **CPI / DPI** — active resolution plus eight configurable levels with indicator
  colours.
- **Lighting** — DPI-colour indicator, static colour, off and idle auto-off.
- **Key delay** — per-button press and release debounce.
- **Recovery** — restore the settings detected when the mouse connected, or
  reset local app preferences without touching the mouse.
- **Safety** — only changed fields are written, on a fresh query, with a
  read-back check. Unknown and keyboard products stay read-only. A cross-process
  lock prevents two configurators from writing at once.
- **Automation** — `rawmctl` exposes status and settings without importing GTK.
- **Local by design** — no telemetry, accounts or cloud service. Device reports
  are generated locally and are never uploaded automatically.

## Screenshots

<p align="center">
  <img src="docs/screenshots/device.png" width="48%" alt="Device page showing battery, firmware and support status">
  <img src="docs/screenshots/performance.png" width="48%" alt="Performance page with polling rate and sensor settings">
</p>
<p align="center">
  <img src="docs/screenshots/dpi.png" width="48%" alt="DPI page with active resolution and eight levels">
  <img src="docs/screenshots/lighting.png" width="48%" alt="Lighting page with LED mode and idle behaviour">
</p>

![Tray icon styles](docs/screenshots/tray-styles.png)

<sub>Screenshots are rendered by demo mode. Available controls depend on the
connected model.</sub>

## Installation

| Format | Best for | Command-line tool |
|---|---|---|
| **AUR** `rawm-control` / `rawm-control-git` | Arch, CachyOS, EndeavourOS | `rawmctl` |
| **Flatpak** `.flatpak` | any distribution with Flatpak and the GNOME 50 runtime | `rawmctl` inside the sandbox |
| **AppImage** `.AppImage` | trying the app without installing | GUI only |
| **Source** | development and packaging | `rawmctl` |

### AUR

```bash
paru -S rawm-control       # latest tagged release
paru -S rawm-control-git   # latest main
```

The packages install the udev rule, desktop entry, tray integration and both
entry points. `rawm-control-git` follows `main`; update it with your AUR helper.

### Flatpak

Download the `.flatpak` from the release page, then:

```bash
flatpak install --user ./rawm-control-*.flatpak
flatpak run io.github.rawmcontrol.RawmControl
```

The Flatpak uses the GNOME 50 runtime, is not distributed through Flathub, and
exposes `/dev/hidraw*` through `--device=all`. To use the CLI inside the
sandbox:

```bash
flatpak run --command=rawmctl io.github.rawmcontrol.RawmControl status
```

### AppImage

```bash
chmod +x rawm-control-*.AppImage
./rawm-control-*.AppImage
```

The AppImage uses the host's Python 3 (3.10 or newer) and GTK/PyGObject stack.
Install the dependencies listed in the
[installation guide](docs/INSTALL.md#appimage) if it does not start. The
AppImage contains the GUI only; use the Flatpak or a native package for
`rawmctl`.

### From source

```bash
git clone https://github.com/NasirA1991/rawm-control.git
cd rawm-control
./rawm-control --demo         # preview without a mouse
sudo ./install.sh             # /usr, including the udev rule
# or, without root:
./install.sh --user           # ~/.local, no udev rule
```

Python 3.10 or newer and the GTK4/PyGObject dependencies are required. See
[installation](docs/INSTALL.md#from-source) for the full dependency list and
uninstall commands.

## Permissions

Native installs apply a udev rule for the known RAWM mouse and receiver product
IDs only; it does not grant access to every device using vendor ID `1915`.
Unknown and keyboard products remain read-only.

If a source or AppImage install reports a permission error, its Device banner
offers **Copy setup command**. You can also install the rule from a checkout:

```bash
sudo install -Dm644 data/udev/71-rawm-hid.rules \
  /usr/lib/udev/rules.d/71-rawm-hid.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
# unplug and reconnect the receiver
```

Flatpak uses `--device=all`, which is broader than the udev rule. Prefer a
native package if you want narrower device access. Full details, including how
to regenerate the rule after adding a product, are in
[the installation guide](docs/INSTALL.md#permissions).

## Usage

```bash
rawm-control                  # window and tray
rawm-control --tray           # start minimized (--minimized is an alias)
rawm-control --no-tray        # window only
rawm-control --demo           # simulated ER21Pro; no hardware access
rawm-control --page dpi       # open a page: device, performance, dpi, lighting
```

With the tray enabled, closing the window keeps the app running. Use **Quit** in
the tray menu or press `Ctrl+Q` to exit; with `--no-tray`, closing the window
exits. Left-click opens the window; right-click opens the menu. GNOME needs an
AppIndicator/KStatusNotifierItem extension, while KDE Plasma, XFCE and most
other SNI hosts work directly.

The tray menu includes **Tray category** (*Application status* by default, or
*Hardware*) and reports **Passive** when no mouse is connected, so hosts that
hide irrelevant indicators can hide it until a mouse appears.

### CLI

`rawmctl` is a standalone entry point and does not import GTK. It works over
SSH or from a terminal on a headless machine.

```bash
rawmctl status
rawmctl polling 1000
rawmctl motion-sync on
rawmctl dpi 1600
rawmctl power HP
rawmctl scan
rawmctl report                     # read-only report for a support issue
rawmctl status --json              # identifiers are redacted
```

Setters read the value back and exit non-zero when the mouse does not confirm
the change. See the [CLI reference](docs/CLI.md) for every command, output
format and exit code.

## Supported devices

The bundled database contains 23 mouse product IDs (21 model rows), nine
receiver dongles and two keyboard products. Only the ER21Pro is
hardware-verified. The complete list of model names, USB IDs and polling limits
is in [docs/DEVICES.md](docs/DEVICES.md).

Unverified models show an **UNVERIFIED MODEL** badge. Unknown PIDs and keyboards
are read-only: the app will not send mouse configuration to them. Receiver
dongles are supported, but the paired mouse may be asleep; the app shows a
Retry banner rather than inventing values.

To help confirm another model, use **Device → Diagnostics → Save device report**
(or `rawmctl report`), review the file, and attach it to a
[device support issue](https://github.com/NasirA1991/rawm-control/issues/new?template=device-report.yml).
Nothing is uploaded automatically.

## Limitations

Not implemented yet:

- key remapping, macros, R-Plus layer and onboard-profile editing;
- X/Y-linked DPI, free-rate polling, RF channel selection and the 2.4 GHz test;
- Lighting Loop/Customize modes and receiver LEDs;
- brightness and firmware update/DFU.

A generic factory reset is not offered because the app does not know each
model's factory parameter block. **Restore detected settings** only returns to
the snapshot read when the mouse connected. See
[docs/PROTOCOL.md](docs/PROTOCOL.md) for the wire-level details and
[CONTRIBUTING.md](CONTRIBUTING.md) if you want to work on these areas.

## Troubleshooting

| Problem | What to try |
|---|---|
| Permission denied | Install the udev rule above, then reconnect the receiver. |
| Mouse not found, or reported asleep | Wake the mouse or check the receiver connection; use Retry in the banner. |
| Settings do not stick | Close RAWM HUB or another configurator; only one writer is allowed. |
| No tray icon on GNOME | Install an AppIndicator/KStatusNotifierItem extension. |
| AppImage will not start | Install the host GTK/PyGObject dependencies or use the Flatpak. |
| `rawmctl` not found in the AppImage | The AppImage is GUI-only; use the Flatpak or a native install. |

The [troubleshooting guide](docs/TROUBLESHOOTING.md) covers error messages,
receiver behaviour, logs and support reports in more detail.

## Documentation

| I want to… | Read |
|---|---|
| install, update, verify or uninstall | [Installation](docs/INSTALL.md) |
| use the command line | [CLI reference](docs/CLI.md) |
| fix a problem | [Troubleshooting](docs/TROUBLESHOOTING.md) |
| check whether my model is supported | [Supported devices](docs/DEVICES.md) |
| send a device report | [Device reports](docs/DEVICE_REPORTS.md) |
| understand the protocol | [Protocol notes](docs/PROTOCOL.md) |
| understand the code structure | [Architecture](docs/ARCHITECTURE.md) |
| contribute or run the tests | [Contributing](CONTRIBUTING.md) |
| report a security issue | [Security policy](SECURITY.md) |

## Contributing

Bug reports, device reports and pull requests are welcome. Read
[CONTRIBUTING.md](CONTRIBUTING.md) before sending code, and use the
[security policy](SECURITY.md) for vulnerabilities rather than a public issue.
Protocol changes should keep the implementation, tests and
[docs/PROTOCOL.md](docs/PROTOCOL.md) in sync.

## Disclaimer

RAWM Control is an independent project. It is not affiliated with or supported
by RAWM or MiraclTek. The protocol was recovered from the publicly served RAWM
HUB web driver; no vendor code is included. Changing mouse settings writes to
firmware-managed configuration, so use it at your own risk.

## License

MIT. See [LICENSE](LICENSE).
