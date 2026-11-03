"""Hardware-in-the-loop checks.  Opt in with RAWM_HW_TEST=1.

This talks to the real mouse and briefly changes motion sync; it restores the
original value in a finally block.  Nothing else is modified.

    RAWM_HW_TEST=1 python3 -m unittest tests.test_hardware -v
"""

from __future__ import annotations

import os
import time
import unittest

from rawm_control import protocol

ENABLED = os.environ.get("RAWM_HW_TEST") == "1"


@unittest.skipUnless(ENABLED, "set RAWM_HW_TEST=1 to run against real hardware")
class HardwareTests(unittest.TestCase):
    def setUp(self):
        from rawm_control import cli

        try:
            self.device, self.state = cli._open()
        except protocol.ProtocolError as exc:
            self.skipTest(str(exc))

    def tearDown(self):
        if getattr(self, "device", None):
            self.device.close()

    def test_query(self):
        self.assertTrue(self.state.device_name)
        self.assertIn(self.state.battery, range(0, 101))
        self.assertGreater(self.state.cpi, 0)
        self.assertGreater(self.state.polling_rate, 0)
        self.assertTrue(self.state.sensor)

    def test_motion_sync_roundtrip(self):
        original = self.state.motion_sync
        target = 0 if original else 1
        try:
            self.state.motion_sync = target
            self.device.set_state(self.state)
            time.sleep(0.6)
            state, _ = self.device.query(timeout=2.0)
            self.assertIsNotNone(state)
            self.assertEqual(state.motion_sync, target)
        finally:
            self.state.motion_sync = original
            self.device.set_state(self.state)
            time.sleep(0.4)


if __name__ == "__main__":
    unittest.main()
