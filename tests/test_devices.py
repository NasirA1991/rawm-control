"""Capability-profile validation regressions."""

from __future__ import annotations

import unittest

from rawm_control import devices
from rawm_control.protocol import MouseState


class PowerModeValidationTest(unittest.TestCase):
    def test_unmapped_power_mode_is_read_only(self):
        caps = devices.for_product(0x2328)
        self.assertTrue(caps.mouse)
        self.assertEqual(caps.power_modes, [])
        state = MouseState(product_id=0x2328)
        self.assertEqual(
            devices.validate_patch(state, {"power_mode": 1}),
            "power mode is not mapped for this model",
        )

    def test_mapped_power_mode_still_validates_range(self):
        caps = devices.for_product(0x2338)
        self.assertTrue(caps.power_modes)
        state = MouseState(product_id=0x2338)
        self.assertIsNone(devices.validate_patch(state, {"power_mode": 1}))
        self.assertEqual(
            devices.validate_patch(state, {"power_mode": len(caps.power_modes)}),
            "invalid power mode",
        )


if __name__ == "__main__":
    unittest.main()
