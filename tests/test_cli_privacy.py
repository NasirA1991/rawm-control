"""Privacy and write-safety tests that need no hardware."""

from __future__ import annotations

import json
import unittest

from rawm_control.cli import _raw_json
from rawm_control.protocol import MouseState


class CliPrivacyTest(unittest.TestCase):
    def test_json_status_is_redacted_by_default(self):
        state = MouseState(
            product_id=0x2338,
            mac_address="AA:BB:CC:DD:EE:FF",
            esb_address="392bf4bc05f0b15df8f9fafbfcfdfeff",
        )
        text = json.dumps(_raw_json(state), default=str)
        self.assertNotIn("AA:BB", text)
        self.assertNotIn("392bf4bc", text)
        self.assertIn("redacted", text)

    def test_include_identifiers_is_explicit(self):
        state = MouseState(
            product_id=0x2338,
            mac_address="AA:BB:CC:DD:EE:FF",
            esb_address="392bf4bc05f0b15df8f9fafbfcfdfeff",
        )
        data = _raw_json(state, include_identifiers=True)
        self.assertEqual(data["mac_address"], "AA:BB:CC:DD:EE:FF")
        self.assertEqual(data["esb_address"], "392bf4bc05f0b15df8f9fafbfcfdfeff")


if __name__ == "__main__":
    unittest.main()
