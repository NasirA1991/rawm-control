"""Local preference reset tests (never touch the user's real config)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rawm_control import config


class PreferenceResetTest(unittest.TestCase):
    def test_reset_removes_only_config_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
                config.config_path().parent.mkdir(parents=True, exist_ok=True)
                config.config_path().write_text('{"tray_icon_style": "number"}', encoding="utf-8")
                autostart = Path(tmp) / "autostart" / "rawm-control.desktop"
                autostart.parent.mkdir(parents=True)
                autostart.write_text("keep me", encoding="utf-8")

                self.assertTrue(config.reset())
                self.assertFalse(config.config_path().exists())
                self.assertTrue(autostart.exists())

    def test_reset_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
                self.assertTrue(config.reset())
                self.assertTrue(config.reset())


if __name__ == "__main__":
    unittest.main()
