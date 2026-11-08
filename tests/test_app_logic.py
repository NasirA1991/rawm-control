"""Small app-level regression tests that do not need a display."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from rawm_control import app as app_module
from rawm_control.app import RawmApplication
from rawm_control.protocol import MouseState


class FakeWindow:
    def __init__(self):
        self.presented = False
        self.visible = True

    def present(self):
        self.presented = True

    def set_visible(self, visible):
        self.visible = visible


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

    def test_first_close_shows_one_time_background_hint(self):
        app = RawmApplication.__new__(RawmApplication)
        app.window = FakeWindow()
        app.tray = object()
        app._quitting = False
        notifications = []
        app.send_notification = lambda key, note: notifications.append(key)

        with patch("rawm_control.app.config.load", return_value={"close_hint_shown": False}),              patch("rawm_control.app.config.mark_close_hint_shown") as mark:
            self.assertTrue(app._on_close_request(None))

        self.assertFalse(app.window.visible)
        self.assertEqual(notifications, ["close-hint"])
        mark.assert_called_once()

    def test_second_close_does_not_repeat_hint(self):
        app = RawmApplication.__new__(RawmApplication)
        app.window = FakeWindow()
        app.tray = object()
        app._quitting = False
        notifications = []
        app.send_notification = lambda key, note: notifications.append(key)

        with patch("rawm_control.app.config.load", return_value={"close_hint_shown": True}),              patch("rawm_control.app.config.mark_close_hint_shown") as mark:
            self.assertTrue(app._on_close_request(None))

        self.assertEqual(notifications, [])
        mark.assert_not_called()

    def test_unknown_gui_subcommand_is_rejected_without_starting_gtk(self):
        with redirect_stderr(io.StringIO()) as err:
            self.assertEqual(app_module.main(["rawm-control", "definitely-not-a-command"]), 2)
        self.assertIn("unknown command", err.getvalue())

    def test_second_activation_reveals_hidden_tray_instance(self):
        app = self.make_app()
        # Simulate an earlier launch: the --tray window is hidden.
        app._activated_once = True
        app._on_activate(None)
        self.assertTrue(app.window.presented)


if __name__ == "__main__":
    unittest.main()
