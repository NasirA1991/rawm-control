"""Tray icon rendering tests (no DBus connection needed)."""

from __future__ import annotations

import unittest

from rawm_control.config import TRAY_STYLES
from rawm_control.protocol import MouseState
from rawm_control.tray import (
    ICON_SIZE,
    TRAY_ICON_SIZES,
    render_icon,
    render_mouse_icon,
    render_percent_icon,
    render_tray_icon,
    render_tray_icon_sizes,
)


class TrayIconTests(unittest.TestCase):
    def test_percent_icon_shape(self):
        state = MouseState(battery=87)
        width, height, pixels = render_percent_icon(state, True)[0]
        self.assertEqual((width, height), (ICON_SIZE, ICON_SIZE))
        self.assertEqual(len(pixels), ICON_SIZE * ICON_SIZE * 4)
        self.assertTrue(any(pixels), "icon should not be fully transparent")

    def test_percent_and_mouse_icons_differ(self):
        state = MouseState(battery=42)
        mouse = render_icon(state, True, show_percent=False)[0][2]
        percent = render_icon(state, True, show_percent=True)[0][2]
        self.assertNotEqual(mouse, percent)

    def test_disconnected_percent_icon(self):
        width, height, pixels = render_percent_icon(None, False)[0]
        self.assertEqual((width, height), (ICON_SIZE, ICON_SIZE))
        self.assertTrue(any(pixels))

    def test_every_style_renders(self):
        state = MouseState(battery=87)
        rendered = {}
        for key, _label in TRAY_STYLES:
            width, height, pixels = render_tray_icon(state, True, key)[0]
            self.assertEqual((width, height), (ICON_SIZE, ICON_SIZE), key)
            self.assertTrue(any(pixels), key)
            rendered[key] = pixels
        # every visible style should be visually distinct
        self.assertGreaterEqual(len(set(rendered.values())), len(TRAY_STYLES) - 1)

    def test_multiple_pixmap_sizes_are_emitted(self):
        state = MouseState(battery=87)
        items = render_tray_icon_sizes(state, True, "ring")
        self.assertEqual([(w, h) for w, h, _ in items], [(n, n) for n in TRAY_ICON_SIZES])
        self.assertTrue(all(pixels for _, _, pixels in items))

    def test_charging_bolt_changes_the_icon(self):
        normal = render_tray_icon_sizes(MouseState(battery=87, charging=False), True, "number")[0][2]
        charging = render_tray_icon_sizes(MouseState(battery=87, charging=True), True, "number")[0][2]
        self.assertNotEqual(normal, charging)

    def test_charging_and_low_battery_do_not_crash(self):
        for battery in (0, 12, 100):
            for charging in (False, True):
                state = MouseState(battery=battery, charging=charging)
                self.assertTrue(render_percent_icon(state, True)[0][2])

    def test_battery_less_mouse_icon_has_no_battery_column(self):
        full = render_mouse_icon(MouseState(battery=100), True, show_battery=False)[0][2]
        empty = render_mouse_icon(MouseState(battery=0), True, show_battery=False)[0][2]
        with_bar = render_mouse_icon(MouseState(battery=100), True, show_battery=True)[0][2]
        self.assertEqual(full, empty)
        self.assertNotEqual(full, with_bar)


if __name__ == "__main__":
    unittest.main()
