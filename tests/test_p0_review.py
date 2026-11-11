"""Regression tests for the P0 safety/CLI/packaging review findings."""

from __future__ import annotations

import copy
import io
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rawm_control import cli, devices, tray
from rawm_control.protocol import (
    CMD_NOTIFY,
    Frame,
    MouseState,
    NOTIFY_BATTERY,
    NOTIFY_BATTERY_LEVELS,
    NOTIFY_SLEEP_TIME,
    apply_notifications,
    state_from_query,
)


class FakeCliDevice:
    def __init__(self):
        self.written = None
        self.closed = False

    def set_state(self, state):
        self.written = copy.deepcopy(state)

    def close(self):
        self.closed = True


class ReviewP0Test(unittest.TestCase):
    def run_cli(self, state, argv):
        dev = FakeCliDevice()
        out, err = io.StringIO(), io.StringIO()
        with patch.object(cli, "_open", return_value=(dev, state)), \
             redirect_stdout(out), redirect_stderr(err):
            try:
                code = cli.run(argv)
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue(), dev

    def test_dpi_out_of_range_is_rejected_without_writing(self):
        state = MouseState(product_id=0x2338)
        code, _out, err, dev = self.run_cli(state, ["dpi", "99999"])
        self.assertEqual(code, 2)
        self.assertIn("dpi must be between", err)
        self.assertIsNone(dev.written)
        self.assertTrue(dev.closed)

    def test_sleep_out_of_range_is_rejected_without_writing(self):
        state = MouseState(product_id=0x2338)
        code, _out, err, dev = self.run_cli(state, ["sleep", "31"])
        self.assertEqual(code, 2)
        self.assertIn("sleep must be between", err)
        self.assertIsNone(dev.written)
        self.assertTrue(dev.closed)

    def test_battery_less_model_omits_battery_from_status_and_json(self):
        knife = MouseState(product_id=0x2328, battery=255)
        self.assertFalse(devices.for_state(knife).battery)

        out = io.StringIO()
        with redirect_stdout(out):
            cli._print_status(knife)
        self.assertNotIn("battery", out.getvalue())

        data = cli._raw_json(knife)
        self.assertIsNone(data["battery"])
        self.assertEqual(data["battery_levels"], [])

    def test_battery_capable_model_still_reports_battery(self):
        state = MouseState(product_id=0x2338, battery=73)
        self.assertTrue(devices.for_state(state).battery)
        out = io.StringIO()
        with redirect_stdout(out):
            cli._print_status(state)
        self.assertIn("battery       73%", out.getvalue())

    def test_generated_udev_rule_is_per_product(self):
        text = devices.udev_rule_text()
        self.assertIn('ATTRS{idProduct}=="2338"', text)
        self.assertIn('ATTRS{idProduct}=="232b"', text)
        self.assertNotIn('ATTRS{idVendor}=="1915", TAG+=', text)
        source = Path("data/udev/71-rawm-hid.rules").read_text(encoding="utf-8")
        self.assertEqual(source, text)

    def test_udev_copy_command_contains_the_generated_rule(self):
        command = devices.udev_copy_command()
        self.assertIn("ATTRS{idProduct}==\"2338\"", command)
        self.assertIn("udevadm control --reload-rules", command)

    def test_untrusted_query_values_are_bounded(self):
        state = state_from_query(
            {
                "battery": 255,
                "cpi": -5,
                "polling": 99999,
                "lod": 9,
                "pm": 200,
                "st": 65535,
                "cpi_l": [99999, -1, 8000],
                "kd": [999] * 40,
                "ocs": [999] * 40,
            }
        )
        self.assertEqual(state.battery, 100)
        self.assertEqual(state.cpi, 0)
        self.assertEqual(state.polling_rate, 8000)
        self.assertEqual(state.lod, 3)
        self.assertEqual(state.power_mode, 3)
        self.assertEqual(state.sleep_time, 1800)
        self.assertEqual(state.cpi_levels[:3], [30000, 0, 8000])
        self.assertEqual(len(state.key_delay), 32)
        self.assertEqual(len(state.onboard_status), 32)
        self.assertTrue(all(x <= 255 for x in state.onboard_status))

    def test_untrusted_battery_calibration_is_ignored(self):
        state = MouseState(product_id=0x2338, battery_levels=[3000, 3100])
        frame = Frame(
            cmd=CMD_NOTIFY,
            size=4,
            subtype=NOTIFY_BATTERY_LEVELS,
            data=bytes([0x00, 0x00, 0xFF, 0xFF]),
        )
        updated, changed = apply_notifications(state, [frame])
        self.assertEqual(updated.battery_levels, [3000, 3100])
        self.assertNotIn("battery_levels", changed)

    def test_battery_less_tray_forces_mouse_style_and_omits_percent(self):
        item = tray.Tray.__new__(tray.Tray)
        item.style = "number"
        item.state = None
        item.connected = False
        item.caps = devices.for_product(0)
        item.sni_status = "Passive"
        item.polling_rates = []
        item._status_text = ""
        item.menu = SimpleNamespace(refresh=lambda: None)
        item._emit = lambda _signal: None
        item.NewStatus = lambda _status: None

        with patch.object(tray, "render_tray_icon_sizes", return_value={}) as render:
            item.update(MouseState(product_id=0x2328, battery=255), True)
        self.assertNotIn("255%", item._status_text)
        self.assertEqual(render.call_args.args[2], "mouse")

        with patch.object(tray, "render_tray_icon_sizes", return_value={}) as render:
            item.update(MouseState(product_id=0x2338, battery=73), True)
        self.assertIn("73%", item._status_text)
        self.assertEqual(render.call_args.args[2], "number")

    def test_battery_notification_is_bounded(self):
        state = MouseState(product_id=0x2338)
        frame = Frame(cmd=CMD_NOTIFY, size=2, subtype=NOTIFY_BATTERY, data=bytes([250, 0]))
        updated, _changed = apply_notifications(state, [frame])
        self.assertEqual(updated.battery, 100)

    def test_sleep_notification_is_bounded(self):
        state = MouseState(product_id=0x2338, sleep_time=300)
        frame = Frame(cmd=CMD_NOTIFY, size=3, subtype=NOTIFY_SLEEP_TIME, data=bytes([0xFF, 0xFF]))
        updated, changed = apply_notifications(state, [frame])
        self.assertEqual(updated.sleep_time, 1800)
        self.assertIn("sleep_time", changed)

    def test_source_entrypoint_works_without_gi(self):
        code = (
            "import sys; sys.modules['gi'] = None; "
            "from rawm_control.__main__ import main; "
            "raise SystemExit(main(['rawm-control', '--version']))"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("rawm-control", proc.stdout)


if __name__ == "__main__":
    unittest.main()
