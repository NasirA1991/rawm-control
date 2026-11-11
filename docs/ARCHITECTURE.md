# Architecture

RAWM Control is a single desktop application, not a daemon. The GTK main loop
owns the window and tray; in hardware mode one worker thread owns the HID device
and all reads and writes. This keeps the UI responsive and gives every
configuration change a single place to enforce validation and read-back. Demo
mode uses an in-process simulated worker instead.

For the wire format, command numbers and CRC details, see
[PROTOCOL.md](PROTOCOL.md). This page is about the code structure and the write
path.

## Module map

| Module | Responsibility |
|---|---|
| `rawm_control/__main__.py` | Lazy entry point: dispatches CLI commands before importing GTK. |
| `rawm_control/app.py` | GApplication, window lifecycle, tray actions, autostart and idle callbacks. |
| `rawm_control/ui.py` | GTK4/libadwaita pages and widgets. |
| `rawm_control/worker.py` | Device thread: discovery, polling, patch queue, reconnection and read-back. |
| `rawm_control/protocol.py` | HID discovery, framing, CRC, query parsing and the device transport. |
| `rawm_control/devices.py` | Capability profiles, validation, polling limits and udev rule generation. |
| `rawm_control/data/devices.json` | Bundled product database used by `devices.py`. |
| `rawm_control/tray.py` | StatusNotifierItem and DBusMenu over raw DBus; cairo icon rendering. |
| `rawm_control/cli.py` | `rawmctl` commands and JSON/status output. |
| `rawm_control/diagnostics.py` | Local, redacted support reports. |
| `rawm_control/config.py` | App identity, version, preferences and autostart state. |

The GUI and CLI are separate entry points. `rawm-control` imports the GTK app;
`rawmctl` imports only the CLI and its dependencies. `__main__.py` chooses the
path before importing GTK, so `rawm-control status` also works without a display.

## Runtime flow

```text
                 discovery + query
rawm-control ───────────────────────► DeviceWorker thread
     ▲                                  │
     │ state / link / write callbacks   │ owns /dev/hidrawN
     │ (marshalled with GLib.idle_add)  │
     └──────────────────────────────────┘
                                      │
                                      ▼
                              protocol.FrameStream
                              CRC + 64-byte reports
```

1. `protocol.discover()` finds a vendor HID collection (`usage page 0xFF00`)
   and checks its report descriptor.
2. `DeviceWorker` opens the device, queries the mouse (or the receiver plus its
   paired mouse), parses the query into a `MouseState`, and publishes it.
3. The UI renders the state. Polling updates use the same state path.
4. A UI or tray action calls `DeviceWorker.submit()` with the intended state.
   The worker does not write the caller's snapshot directly.

## Write path

Every write follows the same sequence:

1. **Rebase** — query the device again and start from that fresh `MouseState`.
2. **Apply** — copy only the requested changes onto the fresh state.
3. **Validate** — `devices.validate_patch()` checks the change against the
   model's capability profile.
4. **Write** — encode the changed fields and send them through the protocol.
5. **Read back** — query again and compare the changed fields.
6. **Report** — emit success only if the read-back matches; otherwise report an
   unconfirmed write.

Runtime-only values such as RSSI and battery calibration are preserved when a
fresh state replaces the previous one. The CLI's `_apply_changes()` follows the
same rebase-and-validate pattern for one-shot commands.

Unknown PIDs and keyboard products are not writable. A receiver is writable only
after the app has identified a supported paired mouse behind it.

## Threading and locking

- The worker thread owns the file descriptor. The GTK main loop never performs
  blocking HID I/O.
- Worker callbacks are delivered to the app thread with `GLib.idle_add`.
- The worker's state snapshot is treated as immutable after publication; updates
  copy it before mutation so a UI callback cannot observe a half-applied change.
- A non-blocking `flock` on the hidraw file descriptor prevents two processes
  from configuring the same mouse at once. The GUI takes the lock only while a
  pending write or sleep update exists; the CLI takes it for write commands and
  releases it on close.
- A write lock is not a substitute for validation or read-back. It prevents
  concurrent writers; it does not make an unsupported model writable.

## Receivers

A receiver is a vendor HID collection that exposes a paired mouse as a virtual
client. The worker detects the receiver capability, opens the receiver, switches
to ESB channel 0 and wraps the mouse's reports in the receiver header. The
resulting state records `via_receiver` and the receiver PID. The UI and CLI show
the receiver path while retaining the mouse model.

If the receiver is present but the paired mouse does not answer, the worker
reports a link error instead of using placeholder battery or setting values.
This is why a connected receiver can still produce a “mouse asleep” banner.

## Tray

`tray.py` registers a StatusNotifierItem and DBusMenu directly. Icons are drawn
with cairo at 22, 32, 48 and 64 px; the tray does not depend on GTK's tray APIs.
The application owns the item name and exports menu actions. Link state controls
the SNI `Status` property, which is why the item becomes Active/Passive as the
mouse connects and disconnects.

Tray actions go through the same worker `submit()` path as the window. They do
not write HID reports directly.

## Tests

The suite is layered so most behaviour can be checked without a mouse:

| Layer | Examples |
|---|---|
| Protocol and state | framing, CRC, query parsing, bounds, notifications |
| Device logic | capability lookup, patch validation, udev generation |
| Worker | reconnection, copy-on-write state, dropped writes, lock behaviour |
| App/UI logic | state presentation, battery-less models, tray text |
| UI smoke | demo window launches and quits under Xvfb |
| Hardware | opt-in `RAWM_HW_TEST=1` query and motion-sync round trip |

Run the normal suite with:

```bash
python3 -m unittest discover -s tests -v
```

The hardware tests talk to a real mouse and briefly change motion sync. They
restore the original value in a `finally` block, but should still be run only
when you are prepared to test hardware.

## Extending the device database

1. Add the product to `rawm_control/data/devices.json` with its PID, capability
   flags, polling rates, CPI range and power modes.
2. Regenerate the per-product udev rule:
   `python3 scripts/generate-udev-rules.py`.
3. Add or update a test in `tests/` for any new capability combination.
4. If the query layout is new, document the evidence in
   [PROTOCOL.md](PROTOCOL.md) and add a regression fixture.
5. Test on real hardware before removing the unverified marker or claiming
   support in the documentation.

Keep the device database, protocol notes and tests consistent. The protocol
document is deliberately more detailed than the README; it is the reference for
anyone changing the wire format.
