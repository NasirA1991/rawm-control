"""Command line interface: scripting and quick checks without the GUI."""

from __future__ import annotations

import argparse
import json
import sys
import time

from . import config, devices, protocol
from .protocol import MouseState, RawmDevice, state_from_query


def _candidates():
    found = protocol.discover()
    found.sort(
        key=lambda d: (
            devices.for_product(d.product_id).receiver,
            "receiver" in (d.name or "").lower(),
        )
    )
    return found


def _open() -> tuple[RawmDevice, MouseState]:
    candidates = _candidates()
    if not candidates:
        raise protocol.DeviceNotFound("no RAWM vendor HID collection found")
    receiver_seen = False
    for info in candidates:
        caps = devices.for_product(info.product_id)
        dev = RawmDevice(info.path)
        dev.open()
        try:
            if caps.receiver:
                receiver_seen = True
                dev.query(timeout=1.0)  # identify the dongle itself
                dev.channel = 0  # ESB_CHANNEL_MOUSE
            state, _frames = dev.query(timeout=2.0)
        except protocol.ProtocolError:
            state = None
        if state is not None and not devices.for_product(state.product_id).receiver:
            if caps.receiver:
                state.via_receiver = True
                state.receiver_product_id = info.product_id
            return dev, state
        dev.close()
    if receiver_seen:
        raise protocol.ProtocolError(
            "A receiver is connected but the paired mouse is not answering. "
            "Turn the mouse on or move it, then retry."
        )
    raise protocol.ProtocolError("The mouse did not answer. Is it awake and paired?")


def _verify(dev: RawmDevice) -> MouseState | None:
    state, _ = dev.query(timeout=1.4)
    return state


def _print_status(state: MouseState) -> None:
    caps = devices.for_state(state)
    print(f"{caps.display_name}")
    print(f"  firmware      {state.firmware or 'unknown'}")
    print(f"  sensor        {state.sensor or caps.sensor or 'unknown'}")
    link = state.connection + (" via receiver" if state.via_receiver and not state.wired else "")
    print(f"  connection    {link}" + (" (charging)" if state.charging else ""))
    print(f"  battery       {state.battery}%")
    print(f"  polling       {state.polling_rate} Hz (max {devices.max_polling_rate(state)} Hz)")
    print(f"  dpi           {state.cpi}")
    print(f"  lod           {caps.lod_label(state.lod)}")
    print(f"  motion sync   {'on' if state.motion_sync else 'off'}")
    print(f"  angle snap    {'on' if state.angle_snapping else 'off'}")
    print(f"  ripple ctrl   {'on' if state.ripple_control else 'off'}")
    print(f"  angle tuning  {state.angle_tuning}°")
    if 0 <= state.power_mode < len(caps.power_modes):
        print(f"  power mode    {caps.power_modes[state.power_mode]}")
    print(f"  sleep timer   {state.sleep_time // 60} min")
    levels = [f"{v}" for v in state.cpi_levels if v]
    print(f"  dpi levels    {', '.join(levels) if levels else 'none'}")
    if state.rssi is not None:
        print(f"  rssi          {state.rssi} dBm")
    if state.surface_quality:
        print(f"  surface       {round(state.surface_quality * 100 / 255)}%")


def _raw_json(state: MouseState) -> dict:
    data = {}
    for key, value in vars(state).items():
        data[key] = value
    data["max_polling_rate"] = devices.max_polling_rate(state)
    data["effective_polling_rates"] = devices.effective_polling_rates(state)
    return data


def _parse_bool(value: str) -> bool:
    return value.lower() in ("1", "on", "true", "yes", "enable", "enabled")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rawm-control",
        description="Control RAWM mice over their vendor HID interface.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {config.VERSION}")
    sub = parser.add_subparsers(dest="command")

    status = sub.add_parser("status", help="show battery, polling rate and sensor settings")
    status.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    sub.add_parser("scan", help="list supported RAWM HID devices")
    sub.add_parser("caps", help="show capabilities of the connected model")

    polling = sub.add_parser("polling", help="get or set the polling rate in Hz")
    polling.add_argument("hz", nargs="?", type=int)

    for name, label in (
        ("motion-sync", "motion sync"),
        ("angle-snapping", "angle snapping"),
        ("ripple-control", "ripple control"),
    ):
        cmd = sub.add_parser(name, help=f"get or set {label}")
        cmd.add_argument("value", nargs="?", choices=["on", "off"])

    dpi = sub.add_parser("dpi", help="get or set the active CPI/DPI")
    dpi.add_argument("value", nargs="?", type=int)

    lod = sub.add_parser("lod", help="get or set lift-off distance (1-3)")
    lod.add_argument("value", nargs="?", type=int)

    power = sub.add_parser("power", help="get or set power mode (index or name)")
    power.add_argument("value", nargs="?")

    sleep = sub.add_parser("sleep", help="get or set the sleep timer in minutes")
    sleep.add_argument("minutes", nargs="?", type=int)

    return parser


def run(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "status"

    try:
        if command == "scan":
            found = protocol.discover()
            if not found:
                print("No RAWM vendor HID collection found.")
                return 1
            for info in found:
                caps = devices.for_product(info.product_id)
                kind = "receiver" if caps.receiver else ("mouse" if caps.mouse else "device")
                print(f"{info.path}  {info.product_id:04x}  {kind:8}  {caps.display_name}  {info.name}")
                if caps.receiver:
                    try:
                        dev = RawmDevice(info.path)
                        dev.open()
                        try:
                            dev.query(timeout=1.0)
                            dev.channel = 0
                            state, _ = dev.query(timeout=2.0)
                        finally:
                            dev.close()
                        if state is not None:
                            print(f"    \u2514\u2500 paired mouse: {state.device_name} ({state.product_id:04x}, "
                                  f"{state.battery}%, {state.polling_rate} Hz)")
                        else:
                            print("    \u2514\u2500 paired mouse: not answering (asleep?)")
                    except protocol.ProtocolError:
                        print("    \u2514\u2500 paired mouse: not answering (asleep?)")
            return 0

        dev, state = _open()
        caps = devices.for_state(state)
        try:
            if command == "status":
                if getattr(args, "json", False):
                    print(json.dumps(_raw_json(state), indent=2, default=str))
                else:
                    _print_status(state)
                return 0

            if command == "caps":
                print(json.dumps(
                    {
                        "name": caps.display_name,
                        "product_id": f"{caps.product_id:04x}",
                        "polling_rates": caps.polling_rates,
                        "max_polling_rate": devices.max_polling_rate(state),
                        "effective_polling_rates": devices.effective_polling_rates(state),
                        "cpi_range": list(caps.cpi_range),
                        "cpi_step": caps.cpi_step,
                        "power_modes": caps.power_modes,
                        "lod": caps.lod_names,
                        "angle_tuning": caps.angle_tuning,
                        "glass_mode": caps.glass_mode,
                        "battery": caps.battery,
                        "light": caps.light,
                    },
                    indent=2,
                ))
                return 0

            if command == "polling":
                if args.hz is None:
                    print(f"{state.polling_rate} Hz")
                    return 0
                maximum = devices.max_polling_rate(state)
                if args.hz < 50 or args.hz > maximum:
                    presets = ", ".join(str(x) for x in devices.effective_polling_rates(state))
                    parser.error(
                        f"supported on this link/power mode: up to {maximum} Hz "
                        f"(presets: {presets})"
                    )
                state.polling_rate = args.hz
                dev.set_state(state)
                new = _verify(dev)
                if new and new.polling_rate == args.hz:
                    print(f"polling rate set to {args.hz} Hz")
                    return 0
                print("device did not confirm the new polling rate", file=sys.stderr)
                return 2

            if command in ("motion-sync", "angle-snapping", "ripple-control"):
                attr = {
                    "motion-sync": "motion_sync",
                    "angle-snapping": "angle_snapping",
                    "ripple-control": "ripple_control",
                }[command]
                if args.value is None:
                    print("on" if getattr(state, attr) else "off")
                    return 0
                setattr(state, attr, 1 if args.value == "on" else 0)
                dev.set_state(state)
                new = _verify(dev)
                if new and getattr(new, attr) == getattr(state, attr):
                    print(f"{command}: {args.value}")
                    return 0
                print("device did not confirm the change", file=sys.stderr)
                return 2

            if command == "dpi":
                if args.value is None:
                    print(state.cpi)
                    return 0
                value = max(caps.cpi_range[0], min(caps.cpi_range[1], args.value))
                state.cpi = value
                dev.set_state(state)
                new = _verify(dev)
                if new and new.cpi == value:
                    print(f"dpi set to {value}")
                    return 0
                print("device did not confirm the new dpi", file=sys.stderr)
                return 2

            if command == "lod":
                if args.value is None:
                    print(state.lod)
                    return 0
                if not 1 <= args.value <= 3:
                    parser.error("lod must be 1, 2 or 3")
                state.lod = args.value
                dev.set_state(state)
                new = _verify(dev)
                if new and new.lod == args.value:
                    print(f"lod set to {args.value}")
                    return 0
                print("device did not confirm the new lod", file=sys.stderr)
                return 2

            if command == "power":
                modes = caps.power_modes or ["Office", "LP", "HP", "Gaming+"]
                if args.value is None:
                    print(modes[state.power_mode] if state.power_mode < len(modes) else state.power_mode)
                    return 0
                value = args.value
                if value.isdigit():
                    index = int(value)
                else:
                    matches = [i for i, name in enumerate(modes) if name.lower().startswith(value.lower())]
                    if not matches:
                        parser.error(f"power modes: {', '.join(modes)}")
                    index = matches[0]
                if not 0 <= index < len(modes):
                    parser.error(f"power modes: {', '.join(modes)}")
                state.power_mode = index
                dev.set_state(state)
                new = _verify(dev)
                if new and new.power_mode == index:
                    print(f"power mode set to {modes[index]}")
                    return 0
                print("device did not confirm the power mode", file=sys.stderr)
                return 2

            if command == "sleep":
                if args.minutes is None:
                    print(f"{state.sleep_time // 60} min")
                    return 0
                seconds = max(60, min(1800, args.minutes * 60))
                dev.set_sleep_time(seconds, crc=state.crc)
                time.sleep(0.4)
                new = _verify(dev)
                if new and abs(new.sleep_time - seconds) < 30:
                    print(f"sleep timer set to {seconds // 60} min")
                    return 0
                print("device did not confirm the sleep timer", file=sys.stderr)
                return 2

            parser.error(f"unknown command {command}")
            return 2
        finally:
            dev.close()
    except protocol.PermissionDenied as exc:
        print(f"Permission denied.\n{exc}", file=sys.stderr)
        return 3
    except protocol.DeviceNotFound as exc:
        print(f"No mouse found: {exc}", file=sys.stderr)
        return 1
    except protocol.ProtocolError as exc:
        print(f"Protocol error: {exc}", file=sys.stderr)
        return 2


CLI_COMMANDS = {
    "status",
    "scan",
    "caps",
    "polling",
    "motion-sync",
    "angle-snapping",
    "ripple-control",
    "dpi",
    "lod",
    "power",
    "sleep",
    "--cli",
}
