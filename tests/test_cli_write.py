"""CLI write-rebase tests with a fake transport."""

from __future__ import annotations

import unittest

from rawm_control import cli, protocol
from rawm_control.protocol import MouseState


class FakeDevice:
    def __init__(self, results):
        self.results = list(results)
        self.written = None

    def query(self, timeout=1.4):
        return self.results.pop(0)

    def set_state(self, state):
        self.written = state


class CliWriteTest(unittest.TestCase):
    def test_patch_is_rebased_on_fresh_state(self):
        initial = MouseState(
            product_id=0x2338,
            cpi=1600,
            motion_sync=0,
            rssi=-40,
            battery_levels=[2900, 3000, 3100, 3200, 3300],
            via_receiver=True,
            receiver_product_id=0x232B,
        )
        fresh = MouseState(product_id=0x2338, cpi=1600, motion_sync=1)
        dev = FakeDevice([(fresh, [])])

        cli._apply_changes(dev, initial, cpi=3200)

        self.assertIsNotNone(dev.written)
        self.assertEqual(dev.written.cpi, 3200)
        self.assertEqual(dev.written.motion_sync, 1)  # external change survives
        self.assertEqual(dev.written.rssi, -40)
        self.assertEqual(dev.written.battery_levels, [2900, 3000, 3100, 3200, 3300])
        self.assertTrue(dev.written.via_receiver)

    def test_no_response_aborts_write(self):
        dev = FakeDevice([(None, [])])
        with self.assertRaises(protocol.ProtocolError):
            cli._apply_changes(dev, MouseState(product_id=0x2338), cpi=800)
        self.assertIsNone(dev.written)


if __name__ == "__main__":
    unittest.main()
