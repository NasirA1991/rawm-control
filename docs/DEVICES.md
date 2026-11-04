# Supported devices

RAWM Control speaks the vendor HID protocol shared by the current RAWM family.
The capability table comes from the vendor's device database.

**Hardware verification is limited to the ER21Pro** (`1915:2338`, PAW3950),
both directly and through a RAWM HS Receiver (`1915:232b`). Other entries use
the same protocol and capability data but have not been tested on physical
units. If you have one, please send a
[read-only device report](DEVICE_REPORTS.md) so support can be confirmed.

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
“With 8K receiver” is what the vendor driver adds from a compatible dongle.
The effective maximum also depends on the power mode: **Office = 125 Hz,
LP = 1000 Hz**, while HP/Gaming+ allow the table maximum.

## Receivers

A dongle such as the RAWM HS Receiver (`1915:232b`) describes itself on the
direct link; the paired mouse is a virtual client on ESB channel 0. RAWM Control
wraps packets in the extended-channel header, queries the mouse through the
dongle, and writes settings back the same way. If the mouse is asleep, the app
shows a Retry banner instead of inventing values.

## Safety

- Unknown PIDs are **read-only diagnostics**. They are not opened as writable
  mice because the parameter layout is not verified.
- Keyboards and other non-mouse RAWM products are filtered out for the same
  reason.
- Configuration writes are changed fields only, rebased on a fresh query and
  read back before success is reported.
- **Restore detected settings** reverts to the snapshot read when the mouse
  connected. This is not a factory reset.
- A generic factory reset is not offered because the app does not know each
  model's factory parameter block.

Use `rawmctl scan` to list devices and `rawmctl report` for a read-only support
report.
