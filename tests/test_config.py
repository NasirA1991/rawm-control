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


class PreferenceSanitisingTest(unittest.TestCase):
    def test_wrong_types_fall_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
                config.config_path().parent.mkdir(parents=True, exist_ok=True)
                config.config_path().write_text(
                    '{"start_hidden": "no", '
                    '"tray_icon_style": [], '
                    '"tray_category": {}, '
                    '"low_battery_notifications": "yes"}',
                    encoding="utf-8",
                )
                data = config.load()
        self.assertIs(data["start_hidden"], False)
        self.assertEqual(data["tray_icon_style"], "ring")
        self.assertEqual(data["tray_category"], config.DEFAULT_TRAY_CATEGORY)
        self.assertIs(data["low_battery_notifications"], True)

    def test_root_array_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
                config.config_path().parent.mkdir(parents=True, exist_ok=True)
                config.config_path().write_text("[]", encoding="utf-8")
                data = config.load()
        self.assertEqual(data, config.DEFAULTS)

    def test_save_writes_a_sanitised_object_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
                config.save({"tray_icon_style": [], "start_hidden": "no"})
                data = config.load()
                leftovers = [
                    p for p in config.config_dir().iterdir()
                    if p.name.startswith(".config.json.")
                ]
        self.assertEqual(data["tray_icon_style"], "ring")
        self.assertIs(data["start_hidden"], False)
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
