# Troubleshooting

Start with the state check:

```bash
rawmctl status
rawmctl scan
```

`status` shows the model, link, battery and current settings. `scan` lists the
RAWM HID collections the app can see. For a problem report, also include the
output of:

```bash
RAWM_CONTROL_LOG=DEBUG rawm-control 2>~/rawm-control.log
```

The log can contain device paths and identifiers. Review it before sharing.

## Permission denied

The app needs read/write access to the vendor `/dev/hidrawN` collection. Check
the device permissions:

```bash
ls -l /dev/hidraw*
```

Native system installs and the AUR packages install a per-product udev rule. If
you installed with `--user`, or you are running the AppImage, install the rule
once and reconnect the receiver:

```bash
sudo install -Dm644 data/udev/71-rawm-hid.rules \
  /usr/lib/udev/rules.d/71-rawm-hid.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Run that from a source checkout, or use **Copy setup command** in the Device
banner. The rule is deliberately limited to known RAWM mouse and receiver PIDs.
See [permissions](INSTALL.md#permissions) for details.

The Flatpak does not use the host udev rule; its manifest grants device access
through `--device=all`.

## Mouse not found, or shown as asleep

- Wake the mouse and move it.
- Check that the receiver is connected and the mouse is paired to it.
- If the receiver is listed but the mouse is not answering, the app shows a
  Retry banner. Wake the mouse, then retry.
- Try a direct cable or another USB port if the receiver is not detected at all.
- The tray battery can lag briefly after the mouse sleeps; use Refresh in the
  window for an immediate update. The background poll disconnects after two
  missed replies rather than showing stale values forever.

A receiver can still be detected while the paired mouse is asleep. That is not a
crash; it is the app refusing to invent settings it could not read.

## Settings do not stick

- Close **RAWM HUB**, another RAWM Control window, and any other tool that may
  be writing to the mouse. Only one writer is allowed at a time.
- Wait for the write to finish. The app rebases the change on a fresh query and
  reads it back; a disconnection or sleep during that window is reported as an
  unconfirmed change.
- Check whether the current power mode limits the requested polling rate. The
  Performance page shows the effective limit; `rawmctl caps` exposes the
  capability profile.
- If the model is marked **UNVERIFIED MODEL**, its parameter mapping has not
  been confirmed on physical hardware. Send a
  [device report](DEVICE_REPORTS.md) rather than assuming a UI bug.

There is no generic factory reset. **Restore detected settings** returns to the
snapshot read when the mouse connected, which is not the same as the factory
parameter block.

## Tray problems

- **No icon on GNOME:** install an AppIndicator/KStatusNotifierItem extension.
  GNOME does not provide a tray host by default.
- **The icon disappears when the mouse is off:** this is intentional. The tray
  item reports **Passive** when no mouse is connected, so hosts configured to
  show relevant items only can hide it. It becomes **Active** on connection.
- **Category change did not apply on KDE:** the *Tray category* setting
  re-registers the item, but some Plasma versions need a panel/session restart
  before the new category is reflected.
- **Left click opens the wrong thing:** some AppIndicator hosts always open the
  menu on primary click. That is a host limitation, not a separate mouse
  binding.

## AppImage or Flatpak startup

**AppImage:** install the host dependencies listed in
[installation](INSTALL.md#appimage). The AppImage is intentionally lean and does
not bundle GTK. It also has no `rawmctl`; use the Flatpak or a native install if
you need the CLI.

**Flatpak:** start it with the application ID rather than by running the bundle
directly:

```bash
flatpak run io.github.rawmcontrol.RawmControl
```

The Flatpak grants broad device access through `--device=all`. If the sandbox
cannot see the receiver, check that the bundle was installed and run with that
manifest, not an older local build.

## CLI failures

| Output | Meaning |
|---|---|
| `No mouse found` | No supported collection was discovered, or the mouse is asleep. |
| `A receiver is connected but the paired mouse is not answering` | Wake the mouse and retry. |
| `Permission denied` | Install the udev rule and reconnect the device. |
| `Device busy` | Another RAWM Control or `rawmctl` process is writing. Wait or close it. |
| `did not confirm` | The write was sent but read-back did not match; retry after waking the mouse. |

See the [CLI reference](CLI.md#exit-codes) for exit codes and JSON privacy.

## Mouse feel and polling

Input consistency depends on the whole link: receiver placement, USB port,
surface, battery level and system load can all matter. If the pointer feels
inconsistent, close games, screen recorders and other heavy background capture
software, then retest before changing mouse settings. The Performance page shows
the polling rate the mouse reports. An 8000 Hz setting is only effective when
the receiver and power mode support it.

## Reporting a problem

- **App bug:** open a regular GitHub issue with the app version, distribution,
  desktop session and the relevant log lines.
- **Unknown or unverified model:** use the
  [device report guide](DEVICE_REPORTS.md).
- **Security issue:** follow the [security policy](../SECURITY.md), not a public
  issue.

Please remove MAC/ESB addresses, serial numbers and other identifiers from
pasted logs and reports.
