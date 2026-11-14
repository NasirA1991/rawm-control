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
        state = MouseState(product_id=0x2338, polling_rate=125)
        self.assertIsNone(devices.validate_patch(state, {"power_mode": 1}))
        self.assertEqual(
            devices.validate_patch(state, {"power_mode": len(caps.power_modes)}),
            "invalid power mode",
        )

    def test_lp_caps_two_mode_receiver_mouse_at_1000(self):
        state = MouseState(
            product_id=0x2343,
            power_mode=0,
            polling_rate=2000,
            via_receiver=True,
            receiver_product_id=0x232B,
        )
        self.assertEqual(devices.max_polling_rate(state), 1000)

    def test_power_and_polling_are_validated_as_one_patch(self):
        state = MouseState(
            product_id=0x2338,
            power_mode=0,
            polling_rate=125,
            via_receiver=True,
            receiver_product_id=0x232B,
        )
        self.assertIsNone(
            devices.validate_patch(
                state, {"power_mode": 3, "polling_rate": 8000}
            )
        )
        state.power_mode = 3
        state.polling_rate = 8000
        self.assertIsNotNone(
            devices.validate_patch(
                state, {"power_mode": 0, "polling_rate": 8000}
            )
        )

    def test_power_change_cannot_leave_polling_above_the_new_cap(self):
        state = MouseState(
            product_id=0x2338,
            power_mode=3,
            polling_rate=8000,
            via_receiver=True,
            receiver_product_id=0x232B,
        )
        self.assertIsNotNone(devices.validate_patch(state, {"power_mode": 0}))


if __name__ == "__main__":
    unittest.main()
