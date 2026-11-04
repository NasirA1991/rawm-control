"""Read-only, privacy-conscious device diagnostics for GitHub issues.

Nothing in this module opens a network connection.  Reports are written to a
local file for the user to review and attach to an issue manually.
"""

from __future__ import annotations

import json
import os
import platform
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config, devices, protocol

REPORT_URL = "https://github.com/NasirA1991/rawm-control/issues/new?template=device-report.yml"

# Device JSON uses these for the mouse's MAC / ESB address.  They are not
# needed for protocol support and should not end up in a public issue.
REDACT_KEYS = {
    "addr",
    "esb_addr",
    "esb_address",
    "mac",
    "mac_address",
    "serial",
    "serial_number",
    "sn",
    "uniq",
    "hid_uniq",
}

_IDENTITY_KEY_PARTS = ("serial", "mac", "addr", "uniq", "device_id", "uuid")
_HEX_ID_RE = re.compile(r"(?:0x)?[0-9a-fA-F]{12,64}\Z")

_MAC_RE = re.compile(r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\Z")


def redact(value: Any, key: str = "") -> Any:
    """Recursively replace MAC/serial-like values while keeping structure."""
    lower = key.lower()
    if lower in REDACT_KEYS or any(part in lower for part in _IDENTITY_KEY_PARTS):
        return f"<redacted: {len(str(value))} chars>"
    if isinstance(value, dict):
        return {k: redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, key) for v in value]
    if isinstance(value, tuple):
        return [redact(v, key) for v in value]
    if isinstance(value, str):
        text = value.strip()
        if _MAC_RE.fullmatch(text) or _HEX_ID_RE.fullmatch(text):
            return "<redacted: device identifier>"
    return value


def _read(path: str | Path) -> str:
    try:
        return Path(path).read_text(errors="replace").strip()
    except OSError:
        return ""


def _uevent(path: str | Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in _read(path).splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            if key.upper() in {"HID_UNIQ", "SERIAL", "UNIQ"}:
                value = "<redacted>"
            out[key] = value
    return out


def _descriptor_hex(path: str) -> str:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return ""
    chunks = [data[i : i + 16].hex(" ") for i in range(0, len(data), 16)]
    return "\n".join(chunks)


def _hid_details(hidraw_path: str) -> dict[str, Any]:
    name = Path(hidraw_path).name
    base = Path("/sys/class/hidraw") / name
    descriptor = _descriptor_hex(base / "device" / "report_descriptor")
    return {
        "hidraw": hidraw_path,
        "uevent": _uevent(base / "uevent"),
        "device_uevent": _uevent(base / "device" / "uevent"),
        "modalias": _read(base / "device" / "modalias"),
        "report_descriptor_hex": descriptor,
        "report_descriptor_bytes": len(bytes.fromhex(descriptor.replace("\n", " "))) if descriptor else 0,
    }


def _caps_dict(caps: devices.Capabilities) -> dict[str, Any]:
    return {
        "display_name": caps.display_name,
        "product_id": f"0x{caps.product_id:04x}",
        "receiver": caps.receiver,
        "mouse": caps.mouse,
        "polling_rates": list(caps.polling_rates),
        "boost_polling_rates": list(caps.boost_polling_rates or []),
        "polling_rate_max": caps.polling_rate_max,
        "cpi_range": list(caps.cpi_range),
        "cpi_step": caps.cpi_step,
        "power_modes": list(caps.power_modes),
        "lod_names": list(caps.lod_names),
        "angle_tuning": caps.angle_tuning,
        "glass_mode": caps.glass_mode,
        "battery": caps.battery,
        "light": caps.light,
    }


def _environment() -> dict[str, Any]:
    release: dict[str, str] = {}
    for line in _read("/etc/os-release").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            release[key] = value.strip('"')
    return {
        "app_version": config.VERSION,
        "python": platform.python_version(),
        "kernel": platform.release(),
        "architecture": platform.machine(),
        "platform": platform.platform(),
        "distribution": release.get("PRETTY_NAME") or release.get("NAME", ""),
        "session_type": os.environ.get("XDG_SESSION_TYPE", ""),
    }


def _query_one(info: protocol.HidrawDevice) -> dict[str, Any]:
    result: dict[str, Any] = {
        "hidraw": info.path,
        "hid_name": info.name,
        "product_id": f"0x{info.product_id:04x}",
        "interface": info.interface,
        "matched_profile": _caps_dict(devices.for_product(info.product_id)),
        "hid": _hid_details(info.path),
        "receiver_query": None,
        "mouse_query": None,
        "mouse_state": None,
        "effective_polling_rates": [],
        "max_polling_rate": None,
    }
    dev: protocol.RawmDevice | None = None
    try:
        dev = protocol.RawmDevice(info.path)
        dev.open()
        caps = devices.for_product(info.product_id)
        dongle_doc = None
        if caps.receiver:
            try:
                dongle_doc, _ = dev.query_document(timeout=1.0)
            except protocol.ProtocolError as exc:
                result["receiver_query_error"] = str(exc)
            dev.channel = 0  # ESB_CHANNEL_MOUSE
        mouse_doc, _frames = dev.query_document(timeout=2.0)
        if dongle_doc:
            result["receiver_query"] = redact(dongle_doc)
        if mouse_doc:
            state = protocol.state_from_query(mouse_doc)
            if caps.receiver:
                state.via_receiver = True
                state.receiver_product_id = info.product_id
            result["mouse_query"] = redact(mouse_doc)
            result["mouse_state"] = redact(vars(state))
            result["mouse_profile"] = _caps_dict(devices.for_state(state))
            result["effective_polling_rates"] = devices.effective_polling_rates(state)
            result["max_polling_rate"] = devices.max_polling_rate(state)
        else:
            result["error"] = "The device did not answer the read-only query."
    except protocol.PermissionDenied as exc:
        result["error"] = str(exc)
    except (protocol.ProtocolError, OSError) as exc:
        result["error"] = str(exc)
    finally:
        if dev is not None:
            dev.close()
    return result


def collect() -> dict[str, Any]:
    """Collect environment, HID descriptors and raw query documents."""
    infos = protocol.discover()
    infos.sort(key=lambda d: (devices.for_product(d.product_id).receiver, "receiver" in (d.name or "").lower()))
    data: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "privacy": "MAC/serial-like values are redacted. This report is generated locally; nothing is uploaded.",
        "environment": _environment(),
        "devices": [_query_one(info) for info in infos[:4]],
    }
    return data


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def render(data: dict[str, Any]) -> str:
    lines = [
        "# RAWM Control device report",
        "",
        f"Generated by RAWM Control {config.VERSION} at {data['generated_at']}.",
        "",
        "**Privacy:** this file was generated locally. It is not uploaded anywhere.",
        "MAC/serial-like values are redacted; review it before posting. The report",
        "contains no hostname, username, home path or serial number.",
        "",
        "## Environment",
        "```json",
        _json(data["environment"]),
        "```",
        "",
    ]
    if not data["devices"]:
        lines += [
            "## Device",
            "",
            "No RAWM vendor HID collection was found. Check the udev rule and that",
            "the mouse/receiver is connected, then generate the report again.",
            "",
        ]
    for index, dev in enumerate(data["devices"], 1):
        lines += [
            f"## Device {index}: {dev.get('hid_name', 'unknown')}",
            "",
            "```json",
            _json({k: v for k, v in dev.items() if k not in {"hid", "receiver_query", "mouse_query", "mouse_state"}}),
            "```",
            "",
        ]
        hid = dev.get("hid", {})
        lines += [
            "### HID report descriptor",
            "",
            f"`{hid.get('hidraw', '')}` · {hid.get('report_descriptor_bytes', 0)} bytes",
            "",
            "```text",
            hid.get("report_descriptor_hex", "") or "(unavailable)",
            "```",
            "",
        ]
        for key, title in (
            ("receiver_query", "Receiver query (dongle identity)"),
            ("mouse_query", "Mouse query (raw CMD_QUERY JSON)"),
            ("mouse_state", "RAWM Control state snapshot"),
        ):
            if dev.get(key):
                lines += [f"### {title}", "", "```json", _json(dev[key]), "```", ""]
        if dev.get("error"):
            lines += ["### Error", "", f"```text\n{dev['error']}\n```", ""]
    lines += [
        "## Notes (please fill in)",
        "",
        "- Mouse model written on the label:",
        "- Firmware shown by RAWM HUB / the app:",
        "- Connection: USB cable / own dongle / receiver model:",
        "- What works, and what is wrong or missing:",
        "",
        "## Submit",
        "",
        "Review this file, then attach it to a GitHub issue:",
        "",
        f"<{REPORT_URL}>",
        "",
        "Do not paste a report without reading it first.",
        "",
    ]
    return "\n".join(lines)


def default_filename() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"rawm-control-report-{stamp}.md"


def build_report() -> str:
    return render(collect())


def write_report(path: str | Path | None = None) -> Path:
    target = Path(path) if path else Path.cwd() / default_filename()
    target.parent.mkdir(parents=True, exist_ok=True)
    text = build_report()
    # Do not leave a world-readable protocol dump behind; write atomically.
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, target)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
    return target
