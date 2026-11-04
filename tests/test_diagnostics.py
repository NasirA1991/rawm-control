"""Unit tests for the privacy-conscious device report."""

from __future__ import annotations

import unittest

from rawm_control import diagnostics


class RedactionTest(unittest.TestCase):
    def test_redacts_identity_fields_recursively(self):
        data = {
            "addr": "AA:BB:CC:DD:EE:FF",
            "product_id": 0x2338,
            "nested": {"esb_addr": "01:02:03:04:05:06", "serial": "abc"},
            "plain_mac": "11:22:33:44:55:66",
            "keep": "ER21Pro",
        }
        out = diagnostics.redact(data)
        self.assertNotIn("AA:BB", str(out))
        self.assertNotIn("01:02", str(out))
        self.assertNotIn("abc", str(out))
        self.assertNotIn("11:22", str(out))
        self.assertEqual(out["product_id"], 0x2338)
        self.assertEqual(out["keep"], "ER21Pro")

    def test_render_without_device_includes_privacy_notice(self):
        text = diagnostics.render(
            {
                "generated_at": "2026-01-01T00:00:00+00:00",
                "environment": {"app_version": "test"},
                "devices": [],
            }
        )
        self.assertIn("not uploaded anywhere", text)
        self.assertIn("No RAWM vendor HID collection", text)
        self.assertIn("device-report.yml", text)


if __name__ == "__main__":
    unittest.main()
