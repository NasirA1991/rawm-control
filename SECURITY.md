# Security policy

RAWM Control is a local desktop utility that talks to a mouse over
`/dev/hidraw*`. It has no accounts, backend service or telemetry. This policy
explains how to report a problem and what the app does with device data.

## Supported versions

Security fixes target the latest tagged release. Before 1.0, older releases are
not maintained separately. Check the
[releases page](https://github.com/NasirA1991/rawm-control/releases) for the
current version and release notes.

## Report a vulnerability

Please use GitHub's private vulnerability reporting:

**https://github.com/NasirA1991/rawm-control/security/advisories/new**

Do not open a public issue for a vulnerability that could put users at risk.
Include:

- the affected version and installation format (AUR, Flatpak, AppImage or
  source);
- the distribution and desktop session;
- steps to reproduce, or a minimal proof of concept;
- the impact you believe is possible;
- any relevant logs with MAC/ESB addresses, serial numbers and other
  identifiers removed.

You will get an acknowledgement when the report is reviewed. Please allow time
for a fix and a coordinated disclosure before publishing details.

## Security model

- **Local HID access.** The app reads and writes the vendor HID collection. On
  native installs, a udev rule grants access only to the known RAWM mouse and
  receiver product IDs. Unknown and keyboard products are read-only. The
  Flatpak uses `--device=all`, which is broader than the native rule.
- **Settings writes.** Mouse settings are firmware-managed. The app rebases each
  change on a fresh query, validates it against the model profile, writes only
  changed fields and reads the result back. There is no generic factory reset
  and no firmware update/DFU support.
- **No network service.** The app does not upload telemetry, settings or device
  reports. Diagnostic reports are written locally and are only shared if the
  user chooses to attach one to an issue.
- **Report contents.** Reports are created atomically with mode `0600`. They
  redact MAC/ESB addresses and serial-like values and do not collect the
  hostname, username or home directory path. Review a report before sharing it;
  it can still contain model, firmware and descriptor details.
- **No privileged helper.** The app does not run a root daemon. Permission is
  granted through udev or the Flatpak sandbox.

This is a small independent project and has not received a formal security
audit. Do not treat the statements above as a guarantee against every bug.

## Out of scope

- Vulnerabilities in GTK, libadwaita, Flatpak, the GNOME runtime or other
  third-party components. Report those to their maintainers.
- Problems that require an attacker to already have local code execution or
  physical access to the machine.
- Deliberately unsafe changes made by a user with direct access to the HID
  device or the ability to edit the system udev rules.

If you are unsure whether something is in scope, report it privately and
describe the impact; it is better to ask than to publish an exploitable issue.
