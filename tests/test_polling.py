"""Polling-rate negotiation tests (receiver boost tables, wired cap, power mode)."""

from __future__ import annotations

import unittest

from rawm_control import devices
from rawm_control.protocol import MouseState


def make_state(**kwargs) -> MouseState:
    state = MouseState(product_id=0x2338, polling_rate=1000, power_mode=2, via_receiver=False)
    for key, value in kwargs.items():
        setattr(state, key, value)
    return state


class PollingTests(unittest.TestCase):
    def test_receiver_advertises_boost_rates(self):
        caps = devices.for_product(0x232B)
        self.assertTrue(caps.receiver)
        self.assertEqual(caps.polling_rates, [])
        self.assertEqual(caps.boost_polling_rates, [2000, 4000, 8000])

    def test_direct_mouse_is_capped_at_its_own_table(self):
        state = make_state()
        self.assertEqual(devices.max_polling_rate(state), 1000)
        self.assertEqual(devices.effective_polling_rates(state), [125, 250, 500, 1000])

    def test_receiver_allows_8k(self):
        state = make_state(via_receiver=True, receiver_product_id=0x232B)
        self.assertEqual(devices.max_polling_rate(state), 8000)
        rates = devices.effective_polling_rates(state)
        for rate in (125, 250, 500, 1000, 2000, 4000, 8000):
            self.assertIn(rate, rates)

    def test_wired_flag_beats_receiver_boost(self):
        state = make_state(via_receiver=True, receiver_product_id=0x232B, wired=True)
        self.assertEqual(devices.max_polling_rate(state), 1000)
        self.assertNotIn(2000, devices.effective_polling_rates(state))

    def test_power_modes_cap_the_rate(self):
        office = make_state(via_receiver=True, receiver_product_id=0x232B, power_mode=0)
        self.assertEqual(devices.max_polling_rate(office), 125)
        low_power = make_state(via_receiver=True, receiver_product_id=0x232B, power_mode=1)
        self.assertEqual(devices.max_polling_rate(low_power), 1000)

    def test_model_specific_max(self):
        # G11Plus caps at 2 kHz even on an 8K receiver.
        state = make_state(
            product_id=0x2343, via_receiver=True, receiver_product_id=0x232B
        )
        self.assertEqual(devices.max_polling_rate(state), 2000)

    def test_current_rate_stays_visible_when_out_of_range(self):
        state = make_state(via_receiver=True, receiver_product_id=0x232B, power_mode=0, polling_rate=4000)
        rates = devices.effective_polling_rates(state)
        self.assertIn(125, rates)
        self.assertIn(4000, rates)
        self.assertNotIn(8000, rates)

    def test_32_bit_param_accepts_8000(self):
        state = make_state(polling_rate=8000)
        from rawm_control.protocol import encode_mouse_param
        import struct

        data = encode_mouse_param(state)
        self.assertEqual(struct.unpack_from("<H", data, 2)[0], 8000)


if __name__ == "__main__":
    unittest.main()
