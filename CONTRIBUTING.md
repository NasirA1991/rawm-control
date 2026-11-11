# Contributing

Bug reports, device reports and pull requests are welcome. This project is
independent, small and hardware-facing: a focused change with a test is more
useful than a broad rewrite.

## Before you start

- **Bug:** include the app version, installation format, distribution, desktop
  session and the relevant log lines. See
  [troubleshooting](docs/TROUBLESHOOTING.md).
- **Unknown model:** generate a read-only
  [device report](docs/DEVICE_REPORTS.md) rather than guessing a capability
  profile.
- **Security issue:** use the [security policy](SECURITY.md), not a public
  issue.
- **Large feature:** open an issue first. Some vendor features are documented in
  [the protocol notes](docs/PROTOCOL.md) but are not implemented yet.

## Development setup

The test environment is the same on CI and locally. On Debian/Ubuntu:

```bash
sudo apt install python3-dbus python3-cairo python3-gi \
  gir1.2-gtk-4.0 gir1.2-adw-1 libgtk-4-1 libadwaita-1-0 \
  xvfb dbus-x11 desktop-file-utils appstream
```

Then run from a checkout:

```bash
git clone https://github.com/NasirA1991/rawm-control.git
cd rawm-control
./rawm-control --demo       # preview the UI without a mouse
python3 -m unittest discover -s tests -v
```

The normal suite does not require GTK to be running under a compositor, but the
UI tests need PyGObject and libadwaita installed. `xvfb` and `dbus-x11` are only
needed for the headless smoke check.

### Hardware tests

Hardware checks are opt-in:

```bash
RAWM_HW_TEST=1 python3 -m unittest tests.test_hardware -v
```

They query a real mouse and briefly change motion sync. The test restores the
original value in a `finally` block, but still writes to hardware. Do not run
them on a mouse you cannot afford to interrupt, and do not enable them in CI.

### Test matrix

| Check | Command |
|---|---|
| Unit and regression tests | `python3 -m unittest discover -s tests -v` |
| Byte-compile | `python3 -m compileall -q rawm_control` |
| Documentation links and device tables | `python3 scripts/check-docs.py` |
| Desktop metadata | `desktop-file-validate data/io.github.rawmcontrol.RawmControl.desktop` |
| AppStream metadata | `appstreamcli validate --no-net data/io.github.rawmcontrol.RawmControl.metainfo.xml` |
| Udev rule | `udevadm verify data/udev/71-rawm-hid.rules` |
| Workflow syntax | `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:1.7.7` |
| Headless demo launch | `dbus-run-session -- xvfb-run -a python3 -m rawm_control --demo --no-tray` |

The documentation checker also compares the tables and counts in
`docs/DEVICES.md` with `rawm_control/data/devices.json`; update both when adding
a model. Workflow syntax is not part of the Python suite; run the pinned
actionlint image locally when changing `.github/workflows/`.

The last command opens a window and waits for the app; close it with `Ctrl+Q`.
CI uses a bounded smoke test that launches the demo and quits it.

## Code layout

The full module and threading description is in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). The short version:

- `protocol.py` handles framing, CRC, discovery and the HID transport.
- `worker.py` owns the device thread and the rebase/validate/write/read-back
  path.
- `devices.py` and `rawm_control/data/devices.json` define per-model
  capabilities.
- `ui.py` contains GTK pages; `app.py` wires the worker, window and tray.
- `tray.py` exports the StatusNotifierItem and DBusMenu.
- `cli.py` and `rawm_control/__main__.py` provide the headless entry points.

`tools/` contains development helpers, not runtime modules:

- `tools/deob.js` rebuilds the web driver's string table and decoder calls.
- `tools/rawm_proto.py` is a protocol playground (scan, query, frame dump).
- `tools/tray_mockups.py` and `tools/tray_styles.py` render tray icons.
- `tools/capture-screenshots.sh` regenerates the README screenshots from demo
  mode; it needs Xvfb, `dbus-run-session` and ImageMagick.

Documentation checks live in `scripts/check-docs.py`; the udev rule generator is
`scripts/generate-udev-rules.py`.

## Change guidelines

- Keep writes safe: a setting must be rebased on a fresh query, validated
  against the model profile, and read back before it is reported as successful.
- Do not make unknown or keyboard products writable without evidence for their
  parameter layout.
- Add a test for every behaviour change. Protocol changes need fixtures and an
  update to [docs/PROTOCOL.md](docs/PROTOCOL.md).
- When adding a model to `rawm_control/data/devices.json`, also run
  `python3 scripts/generate-udev-rules.py` and update
  [docs/DEVICES.md](docs/DEVICES.md).
- Keep the unverified marker until the model has been tested on physical
  hardware.
- Avoid new runtime dependencies unless they are necessary and available in the
  distributions the project already supports.
- Update the documentation when behaviour, commands, paths or limitations change.
  Do not document functionality that is not implemented.

## Build release artifacts

```bash
version=$(python3 -c "from rawm_control.config import VERSION; print(VERSION)")
./packaging/appimage/build.sh "$version" dist
./packaging/flatpak/build.sh "$version" dist
```

The AppImage build downloads a pinned appimagetool release and verifies its
SHA-256. The Flatpak manifest needs the GNOME 50 runtime and SDK. Release
workflows also check the version, metadata, tests, checksums and keyless cosign
signatures; see [installation](docs/INSTALL.md#verify-a-release) for the
verification commands.

There is no separate changelog file: the GitHub release notes are the
user-facing changelog for each tagged version.

## Scope

The user-facing list of unimplemented features is in the
[README limitations section](README.md#limitations). The wire-level notes for
many of those features are in [docs/PROTOCOL.md](docs/PROTOCOL.md). They need UI
work, hardware verification and tests rather than documentation alone.

## Development disclosure

This project was built with AI assistance. Review generated changes with extra
care, and test hardware-affecting changes on a real device before merging. Only
the ER21Pro has been verified on physical hardware.
