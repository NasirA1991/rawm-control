# Command-line interface

`rawmctl` controls the mouse without starting the GTK app. It is useful in
scripts, status bars, SSH sessions and small desktop shortcuts. It does not
import GTK or libadwaita, so it can run on a headless machine with the Python
and HID dependencies installed.

`rawmctl` is included in the AUR/source packages and in the Flatpak. The
AppImage contains the GUI only. In a Flatpak:

```bash
flatpak run --command=rawmctl io.github.rawmcontrol.RawmControl status
```

`rawmctl` does not need root when the udev rule is installed. See
[installation](INSTALL.md#permissions) if it reports a permission error.

## Quick checks

```bash
rawmctl                    # same as rawmctl status
rawmctl status
rawmctl status --json
rawmctl scan               # list RAWM vendor HID collections
rawmctl caps               # capabilities of the connected model as JSON
```

All of these commands are read-only.

## Commands

| Command | Without a value | With a value |
|---|---|---|
| `status` | Show battery, link, polling and sensor settings. | — |
| `scan` | List RAWM vendor HID collections (mouse, receiver or read-only keyboard). | — |
| `caps` | Print the model capability profile as JSON. | — |
| `report` | Write a local diagnostic report. | `-o FILE` sets the path; `--stdout` prints it. |
| `polling` | Print the current polling rate in Hz. | `rawmctl polling HZ` sets it. |
| `motion-sync` | Print `on` or `off`. | `rawmctl motion-sync on|off` |
| `angle-snapping` | Print `on` or `off`. | `rawmctl angle-snapping on|off` |
| `ripple-control` | Print `on` or `off`. | `rawmctl ripple-control on|off` |
| `dpi` | Print the active CPI/DPI. | `rawmctl dpi VALUE` sets the active value. |
| `lod` | Print the lift-off distance index. | `rawmctl lod 1|2|3` |
| `power` | Print the current power-mode name. | `rawmctl power INDEX` or an unambiguous name prefix. |
| `sleep` | Print the sleep timer in minutes. | `rawmctl sleep MINUTES` (1–30). |

Values are checked against the model's capability profile. Polling values above
the current link/power-mode limit and DPI values outside the model's range are
rejected instead of silently clamped. A model may expose only some of these
commands; `caps` shows its supported ranges and modes.

`dpi` changes the active resolution. The eight DPI levels are configured in the
GUI; `rawmctl` does not edit the level table.

`power` accepts a full name case-insensitively or an unambiguous prefix (for
example `HP`). Ambiguous or unknown names return an error. If a model has no
mapped power modes, `power` reports that instead of guessing an index.

## Examples

```bash
# Read the current settings as machine-readable JSON
rawmctl status --json

# Set a common desktop configuration
rawmctl polling 1000
rawmctl dpi 1600
rawmctl motion-sync on

# Return the mouse to a lower-power mode
rawmctl power Office
rawmctl sleep 10

# Capture a report for a support issue
rawmctl report -o ~/rawm-report.md
```

Setters first fetch a fresh state, apply only the requested fields, write the
result, and query the mouse again. If the read-back does not match, the command
exits non-zero and says that the device did not confirm the change. `sleep` uses
the dedicated sleep command rather than the full-state patch path, but still
reads back and verifies the result. The same write lock is used by the GUI, so
two configurators cannot write at the same time.

## JSON output

`rawmctl status --json` prints the full state as JSON, with MAC/ESB identifiers
removed by default. Use `--include-identifiers` only for local debugging; do not
paste that output into a public issue.

The diagnostic report is also local-only. It is written atomically with mode
`0600`, does not use the network, and is never uploaded automatically. See
[device reports](DEVICE_REPORTS.md) for its contents and privacy notes.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success, including a get command that printed a value. |
| `1` | No supported mouse found, or `scan` found no matching collection. |
| `2` | Protocol, validation, confirmation, busy-lock or argument error. |
| `3` | Permission denied while opening the HID device. |

A write that is not confirmed by the mouse is an error, even if the write
command itself completed. A busy device means another RAWM Control process or
`rawmctl` process currently holds the write lock; wait for it to finish or close
it, then retry.

## Troubleshooting

If `rawmctl` cannot find the mouse, check the receiver and wake the paired
mouse. The GUI shows a Retry banner in the same situation. For permission
problems and other failures, see the
[troubleshooting guide](TROUBLESHOOTING.md).
