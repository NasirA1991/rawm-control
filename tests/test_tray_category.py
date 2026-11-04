"""Tray category preference tests (no live SNI host needed)."""

from __future__ import annotations

import unittest

from rawm_control import config
from rawm_control.tray import Tray


class TrayCategoryTest(unittest.TestCase):
    def test_application_status_is_the_default(self):
        self.assertEqual(config.DEFAULT_TRAY_CATEGORY, "ApplicationStatus")
        self.assertEqual(config.DEFAULTS["tray_category"], "ApplicationStatus")
        self.assertIn("Hardware", dict(config.TRAY_CATEGORIES))

    def test_sni_property_uses_configured_category(self):
        tray = Tray.__new__(Tray)
        tray.category = "ApplicationStatus"
        tray.sni_status = "Passive"
        tray._status_text = "test"
        tray._icon = []
        props = tray._props()
        self.assertEqual(str(props["Category"]), "ApplicationStatus")
        self.assertEqual(str(props["Status"]), "Passive")


if __name__ == "__main__":
    unittest.main()
