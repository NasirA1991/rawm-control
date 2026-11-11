# Installation

RAWM Control is a Linux desktop app. Choose the package that matches how you
want to install and update it. The [README](../README.md) has the short version;
this page covers dependencies, permissions, verification and removal.

## Choose a format

| Format | Best for | Updates | Includes `rawmctl` |
|---|---|---|---|
| **AUR** `rawm-control` | Arch, CachyOS, EndeavourOS | AUR helper | Yes |
| **AUR** `rawm-control-git` | Arch-based systems following `main` | AUR helper rebuild | Yes |
| **Flatpak** | Any distribution with Flatpak | Install a newer `.flatpak` | Yes, inside the sandbox |
| **AppImage** | Trying the app without installing | Replace the file | No, GUI only |
| **Source** | Development and packaging | `git pull` and reinstall | Yes |

Release artifacts are built and checked for the latest tagged release. See the
[releases page](https://github.com/NasirA1991/rawm-control/releases) for the
current version.

## Requirements

- **Linux** with the `hidraw` subsystem and the usual udev tools.
- A desktop session on **X11 or Wayland**.
- For the tray: a StatusNotifierItem host. KDE Plasma, XFCE and most panels work
  directly; GNOME needs an AppIndicator/KStatusNotifierItem extension.
- The Flatpak requires the GNOME 50 runtime. Native and AppImage installs need
  the packages below.

### Python and GTK dependencies

RAWM Control requires Python **3.10 or newer** and the system GTK stack. These
are distribution packages, not PyPI dependencies.

| Distribution | Packages |
|---|---|
| Arch / CachyOS | `python python-gobject gtk4 libadwaita python-cairo python-dbus hicolor-icon-theme` |
| Debian / Ubuntu | `python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-cairo python3-dbus hicolor-icon-theme` |
| Fedora | `python3 python3-gobject gtk4 libadwaita python3-cairo python3-dbus hicolor-icon-theme` |

Package names can differ on derivatives. The app needs GTK 4, libadwaita,
PyGObject, pycairo and dbus-python at runtime.

## Arch / CachyOS (AUR)

Install with any AUR helper:

```bash
paru -S rawm-control       # latest tagged release
paru -S rawm-control-git   # latest main
```

The packages install:

- `/usr/bin/rawm-control` and `/usr/bin/rawmctl`;
- the application, desktop entry and icons;
- the per-product udev rule under `/usr/lib/udev/rules.d/`.

The udev rule is applied automatically, so no manual permission step is needed.
Update with your helper. `rawm-control-git` is a VCS package and is rebuilt when
the helper updates it.

## Flatpak

Download `rawm-control-VERSION-x86_64.flatpak` from the release page, then:

```bash
flatpak install --user ./rawm-control-*.flatpak
flatpak run io.github.rawmcontrol.RawmControl
```

The bundle contains the app and its `dbus-python` dependency, and uses the
GNOME 50 runtime (`org.gnome.Platform//50`); install that runtime first if
Flatpak reports it missing. The app is **not** distributed through Flathub. The
manifest grants `--device=all` so the sandbox can reach `/dev/hidraw*`; this is
broader than the native per-product udev rule.

The CLI is included in the sandbox:

```bash
flatpak run --command=rawmctl io.github.rawmcontrol.RawmControl status
```

Install a newer bundle to update. Remove the app with:

```bash
flatpak uninstall io.github.rawmcontrol.RawmControl
# add --delete-data to remove ~/.var/app/... settings as well
```

## AppImage

Download `rawm-control-VERSION-x86_64.AppImage`, then:

```bash
chmod +x rawm-control-*.AppImage
./rawm-control-*.AppImage
```

The AppImage is a lean bundle: it uses your host's Python 3.10+ and the GTK
packages listed above. It contains the GUI only. If you need `rawmctl` for
scripting, use the AUR/source package or the Flatpak.

If the AppImage cannot start, install the missing host packages and try again.

## From source

```bash
git clone https://github.com/NasirA1991/rawm-control.git
cd rawm-control
./rawm-control --demo          # preview without hardware access
sudo ./install.sh              # system install under /usr, with udev rule
```

For a per-user install without root:

```bash
./install.sh --user             # ~/.local, no udev rule
```

A user install still needs the udev rule for hardware access; the installer
prints the exact command. Run it from the checkout so `data/udev/` is available.

To build an Arch package locally:

```bash
makepkg -si
```

`install.sh` supports `PREFIX` and `DESTDIR` for packaging. See
[CONTRIBUTING.md](../CONTRIBUTING.md) for the test and release-artifact
commands.

## Permissions

The vendor HID collection is a `/dev/hidrawN` device. Native system packages
install a rule for the **known RAWM mouse and receiver product IDs**, not for
every device using vendor ID `1915`. Unknown products and keyboards are not
included.

If the app reports a permission error, the Device banner offers **Copy setup
command**. From a source checkout, the same command is:

```bash
sudo install -Dm644 data/udev/71-rawm-hid.rules \
  /usr/lib/udev/rules.d/71-rawm-hid.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
# unplug and reconnect the receiver
```

A user install does not run this step. The rule file is installed by the system
package; for a source or AppImage install, keep a copy of the file or use the
command from the app banner.

If you add a new product to `rawm_control/data/devices.json`, regenerate the
rule with:

```bash
python3 scripts/generate-udev-rules.py
```

Do not use a vendor-wide `1915` rule unless you understand that it grants raw
HID access to every device with that vendor ID. The generated per-product rule
is intentionally narrower.

## Verify a release

Each release publishes `SHA256SUMS` and keyless cosign bundles for the source
tarball, AppImage and Flatpak. Download the artifact you want plus
`SHA256SUMS`, then check it:

```bash
cd ~/Downloads
sha256sum -c --ignore-missing SHA256SUMS
```

`--ignore-missing` lets you verify only the files you downloaded; the release
also contains checksums for the other formats.

For a signature check, install [cosign](https://docs.sigstore.dev/cosign/verifying/verify/)
and run:

```bash
cosign verify-blob \
  --bundle rawm-control-VERSION.tar.gz.sigstore \
  --certificate-identity-regexp \
    'https://github\.com/NasirA1991/rawm-control/\.github/workflows/release\.yml@refs/tags/v.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  rawm-control-VERSION.tar.gz
```

Use the matching artifact and `.sigstore` bundle for the AppImage or Flatpak.
The bundles are optional for normal use; `SHA256SUMS` is the quick integrity
check.

## Update and uninstall

| Install | Update | Remove |
|---|---|---|
| AUR | `paru -Syu` (or your helper’s update command) | `paru -Rns rawm-control` |
| AUR git | helper rebuild/update | `paru -Rns rawm-control-git` |
| Flatpak | install a newer bundle | `flatpak uninstall io.github.rawmcontrol.RawmControl` |
| AppImage | replace the file | delete the file |
| Source, system | `git pull`, then `sudo ./install.sh` | `sudo ./uninstall.sh` |
| Source, user | `git pull`, then `./install.sh --user` | `./uninstall.sh --user` |

Manual uninstalls keep user settings in `~/.config/rawm-control`. AUR and
Flatpak removal follows the package manager’s normal rules for user data.

## Troubleshooting

See the [troubleshooting guide](TROUBLESHOOTING.md) for permission errors,
asleep receivers, tray hosts and startup problems. For a device that is not
recognised, generate a [device report](DEVICE_REPORTS.md).
