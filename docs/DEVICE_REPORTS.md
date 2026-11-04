# Device reports: help add support for another RAWM mouse

Only the **ER21Pro** (direct and through an HS Receiver) has been tested on
physical hardware. The rest of the device table comes from the vendor's
capability database and the shared protocol. If you have another RAWM model,
a read-only report is the most useful thing you can send.

## Privacy first

The report is generated **locally** and is **never uploaded automatically**.
There is no telemetry and no network code in this feature. You get a Markdown
file, can read it, and choose whether to attach it to a GitHub issue.

The generator redacts:

- MAC / ESB addresses (`addr`, `esb_addr`, `mac_address`)
- serial-like values (`serial`, `sn`, `uniq`, `HID_UNIQ`)
- hostname, username and home paths (the report does not include them)

Review the file before posting anyway. If anything sensitive slipped through,
remove it before attaching.

## What it collects

- app version, Python, kernel, distro name and session type
- the vendor HID report descriptor
- `/sys/class/hidraw` uevent/modalias for the collection
- the raw `CMD_QUERY` JSON from the dongle and/or mouse
- the matched capability profile and effective polling rates
- a snapshot of the current settings state
- filler notes for you to describe what works and what does not

This is enough to add a new PID/capability profile and to inspect an unknown
query layout. No configuration writes are performed.

## Generate it

GUI:

1. Open **Device**.
2. Scroll to **Diagnostics → Save device report**.
3. Choose a location, then review the `.md` file.

CLI (same report):

```bash
rawmctl report
# or explicitly:
rawmctl report -o ~/rawm-report.md
# print to stdout:
rawmctl report --stdout
```

If the mouse is asleep, the report still captures the receiver/dongle identity;
wake the mouse and regenerate for the full mouse query.

## Submit it

Open a **Device support report** issue:

https://github.com/NasirA1991/rawm-control/issues/new?template=device-report.yml

Fill in the model/PID and symptoms, then attach the report file to the issue
(drag it into the comment box) or paste it inside a details block. Please do not
open a report containing unredacted serial numbers or MAC addresses.

## Manual fallback

If `rawmctl report` cannot find the device at all, include the output of:

```bash
lsusb -d 1915:
sudo udevadm info --attribute-walk --name=/dev/hidrawN
```

and the model name/PID from the label or RAWM HUB. That is less useful than the
report, but still enough to identify what to add.
