"""Small app-level regression tests that do not need a display."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from rawm_control.app import RawmApplication
from rawm_control.protocol import MouseState


class FakeWindow:
    def __init__(self):
        self.presented = False

    def present(self):
        self.presented = True

    def set_visible(self, _visible):
        pass


class AppActivationTest(unittest.TestCase):
    def make_app(self):
        app = RawmApplication.__new__(RawmApplication)
        app._activated_once = False
        app.start_hidden = True
        app.tray = object()
        app.window = FakeWindow()
        app._ensure_window = lambda: app.window
        return app

    def test_state_updates_do_not_reset_activation_flag(self):
        app = RawmApplication.__new__(RawmApplication)
        app.window = None
        app.tray = None
        app._low_battery_notified = False
        app._activated_once = True

        with patch("rawm_control.app.config.load", return_value={"low_battery_notifications": False}):
            app._apply_state(MouseState(battery=80), set())

        self.assertTrue(app._activated_once)

    def test_second_activation_reveals_hidden_tray_instance(self):
        app = self.make_app()
        # Simulate an earlier launch: the --tray window is hidden.
        app._activated_once = True
        app._on_activate(None)
        self.assertTrue(app.window.presented)


if __name__ == "__main__":
    unittest.main()
