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
protocol used here was recovered from the public RAWM HUB web driver.

## Compatibility at a glance

| Status | Hardware | What it means |
|---|---|---|
| **Verified** | ER21Pro (`1915:2338`) direct, and through the **RAWM HS Receiver** (`1915:232b`) | Tested on physical hardware. |
| **Catalogued, unverified** | Other recognised RAWM mouse profiles in the [device list](docs/DEVICES.md) | Shared vendor protocol; the app shows **UNVERIFIED MODEL**. These profiles are configurable, but have not been tested on physical hardware. |
| **Read-only** | Unknown USB product IDs and RAWM keyboards (AK60 `1915:2345`, Z68A `1915:2342`) | Diagnostics only; the app never writes configuration to them. |

Only the ER21Pro is hardware-verified — this is not a claim that the whole RAWM
family works. The complete matrix of model names, USB IDs, receiver IDs, polling
limits and power-mode restrictions is in [docs/DEVICES.md](docs/DEVICES.md).

> **Project disclosure:** RAWM Control was built with AI assistance. It is an
> independent project, not affiliated with or supported by RAWM or MiraclTek.

## Quick start

For Arch, CachyOS and EndeavourOS:

```bash
paru -S rawm-control
rawm-control
```

For other distributions, use the Flatpak or AppImage from the
[latest release](https://github.com/NasirA1991/rawm-control/releases/latest).
See the [installation guide](docs/INSTALL.md) for dependencies, permissions,
updates and uninstall instructions.

**On this page:** [Compatibility](#compatibility-at-a-glance)
· [Features](#features) · [Screenshots](#screenshots)
· [Installation](#installation) · [Permissions](#permissions) · [Usage](#usage)
· [CLI](#cli) · [Supported devices](#supported-devices)
· [Limitations](#limitations) · [Troubleshooting](#troubleshooting)
· [Documentation](#documentation) · [Contributing](#contributing)
· [Security](#security) · [License](#license)

## Features

- **Device and battery** — battery percentage, charging and connection status,
  configurable tray icon styles, and a Passive tray state when no mouse is
  connected.
- **Performance and sensor** — polling rate, Motion Sync, ripple control, angle
  snapping and tuning, lift-off distance, glass mode, power mode, sleep timer
  and wireless turbo where the model supports them.
- **DPI and lighting** — active CPI/DPI plus eight configurable levels with
  indicator colours; static lighting and idle auto-off.
- **Button settings** — independent press and release debounce.
- **Recovery and reliability** — restore the settings detected when the mouse
  connected, write only changed fields on a fresh query, verify writes by
  reading them back, and lock the device against concurrent configurators.
- **CLI and automation** — `rawmctl` provides status and settings without
  importing GTK, including from SSH or a headless terminal.
- **Local by design** — no telemetry, accounts or cloud service. Device reports
  are generated locally and never uploaded automatically.

## Screenshots

| Device overview | Performance and sensor |
|:--:|:--:|
| ![Device page showing ER21Pro battery, firmware and support status](docs/screenshots/device.png) | ![Performance page with polling rate and sensor settings](docs/screenshots/performance.png) |
| **DPI levels** | **Tray icons** |
| ![DPI page with active resolution and eight levels](docs/screenshots/dpi.png) | ![Tray icons showing battery, charging and disconnected states](docs/screenshots/tray-styles.png) |

<sub>The four main-window images are captured from demo mode. The tray image shows
the app's actual icon renders at real panel sizes; the surrounding panel is
supplied by the desktop. Available controls depend on the connected model.</sub>

## Installation

| Method | Best for | `rawmctl` |
|---|---|---|
| **AUR** `rawm-control` / `rawm-control-git` | Arch, CachyOS, EndeavourOS | Yes |
| **Flatpak** | Most distributions; requires the GNOME 50 runtime | Yes, inside the sandbox |
| **AppImage** | Trying the app without installing | GUI only |
| **Source** | Development and packaging | Yes |

- **AUR** installs the per-product udev rule automatically.
- **Flatpak** uses broader `--device=all` access so the sandbox can reach
  `/dev/hidraw*`.
- **AppImage** uses the host Python 3.10+ and GTK/PyGObject stack, and does not
  include `rawmctl`.
- **Source** installs can use the system or `--user` layout; a user install
  still needs the udev rule for hardware access.

The [installation guide](docs/INSTALL.md) has the exact commands for every
format, dependencies, release verification, updates and uninstall instructions.

## Permissions

Native packages install a udev rule for the known RAWM mouse and receiver
product IDs only. They do not grant access to every device using vendor ID
`1915`, and unknown products and keyboards are excluded from writable access.
Flatpak is different: its `--device=all` permission is broader than the native
rule, so prefer a native package if you want narrower access.

If a source or AppImage install reports a permission error, the Device banner
offers **Copy setup command**. The rule and reload commands are documented in
the [installation guide](docs/INSTALL.md#permissions). Do not run the
application as root as a workaround for HID permissions.

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
rawmctl scan
rawmctl dpi 1600
rawmctl polling 1000
rawmctl report                     # read-only report for a support issue
```

Setters read the value back and exit non-zero when the mouse does not confirm
the change. See the [CLI reference](docs/CLI.md) for every command, output
format and exit code.

## Supported devices

The complete compatibility matrix is in [docs/DEVICES.md](docs/DEVICES.md). The
bundled data has 23 mouse product IDs across 21 model rows, nine receiver
dongles and two keyboard products. Only the ER21Pro is hardware-verified.

Recognised but unverified models are configurable and show an **UNVERIFIED
MODEL** badge; the badge means untested, not read-only. Unknown PIDs and
keyboards are different: they remain read-only and are never written. Receiver
dongles are supported, but the paired mouse may be asleep; the app shows a Retry
banner rather than inventing values.

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
| Permission denied | Follow the [permissions setup](docs/INSTALL.md#permissions), then reconnect the receiver. |
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

## Security

Report vulnerabilities through the private process in [SECURITY.md](SECURITY.md)
rather than a public issue. The policy describes the local-HID security model and
what is out of scope.

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
