"""End-to-end CLI command paths with a fake HID device."""

from __future__ import annotations

import copy
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from rawm_control import cli, devices
from rawm_control.protocol import MouseState


class FakeDevice:
    def __init__(self, results):
        self.results = list(results)
        self.written = None
        self.closed = False

    def query(self, timeout=1.4, base=None):
        return self.results.pop(0)

    def set_state(self, state):
        self.written = copy.deepcopy(state)

    def close(self):
        self.closed = True


class CliRunTest(unittest.TestCase):
    def run_with(self, state, results, argv):
        dev = FakeDevice(results)
        out, err = io.StringIO(), io.StringIO()
        with patch.object(cli, "_open", return_value=(dev, state)), \
             redirect_stdout(out), redirect_stderr(err):
            code = cli.run(argv)
        return code, out.getvalue(), err.getvalue(), dev

    def test_boolean_setters_confirm_the_requested_value(self):
        cases = [
            ("motion-sync", "motion_sync"),
            ("angle-snapping", "angle_snapping"),
            ("ripple-control", "ripple_control"),
        ]
        for command, attr in cases:
            with self.subTest(command=command):
                initial = MouseState(product_id=0x2338)
                fresh = copy.deepcopy(initial)
                confirmed = copy.deepcopy(initial)
                setattr(confirmed, attr, 1)
                code, out, _err, dev = self.run_with(
                    initial, [(fresh, []), (confirmed, [])], [command, "on"]
                )
                self.assertEqual(code, 0)
                self.assertEqual(getattr(dev.written, attr), 1)
                self.assertIn(f"{command}: on", out)
                self.assertTrue(dev.closed)

    def test_boolean_setter_reports_unconfirmed_write(self):
        initial = MouseState(product_id=0x2338)
        fresh = copy.deepcopy(initial)
        unconfirmed = copy.deepcopy(initial)
        code, _out, err, dev = self.run_with(
            initial, [(fresh, []), (unconfirmed, [])], ["motion-sync", "on"]
        )
        self.assertEqual(code, 2)
        self.assertIn("did not confirm", err)
        self.assertTrue(dev.closed)

    def test_unmapped_power_mode_is_rejected(self):
        state = MouseState(product_id=0x2328)
        self.assertEqual(devices.for_product(0x2328).power_modes, [])
        code, _out, err, dev = self.run_with(state, [], ["power", "1"])
        self.assertEqual(code, 2)
        self.assertIn("not mapped", err)
        self.assertIsNone(dev.written)
        self.assertTrue(dev.closed)

    def test_power_mode_lowers_polling_when_needed(self):
        state = MouseState(
            product_id=0x2338,
            power_mode=3,
            polling_rate=8000,
            via_receiver=True,
            receiver_product_id=0x232B,
        )
        fresh = copy.deepcopy(state)
        confirmed = copy.deepcopy(state)
        confirmed.power_mode = 0
        confirmed.polling_rate = 125

        code, out, _err, dev = self.run_with(
            state, [(fresh, []), (confirmed, [])], ["power", "office"]
        )

        self.assertEqual(code, 0)
        self.assertEqual(dev.written.power_mode, 0)
        self.assertEqual(dev.written.polling_rate, 125)
        self.assertIn("polling rate lowered", out)

    def test_cli_help_does_not_enter_gui(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(["help"]), 0)
        self.assertIn("status", out.getvalue())
        self.assertIn("usage: rawmctl", out.getvalue())

    def test_unknown_command_is_an_argparse_error(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            cli.main(["definitely-not-a-command"])
        self.assertEqual(exc.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
