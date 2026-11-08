"""Tray DBusMenu event dispatch and ID-range regressions."""

from __future__ import annotations

import unittest

from rawm_control import config
from rawm_control.protocol import MouseState
from rawm_control.tray import (
    ID_CATEGORY_BASE,
    ID_DPI_BASE,
    ID_POLLING_BASE,
    ID_STYLE_BASE,
    TrayMenu,
)


class FakeTray:
    def __init__(self):
        self.polling_rates = [1000, 2000, 4000, 8000]
        self.state = MouseState(cpi_levels=[400, 800, 1600, 3200, 0, 0, 0, 0])
        self.polled = []
        self.selected = []
        self.styles = []
        self.categories = []
        self.on_polling = self.polled.append
        self.on_cpi = self.selected.append
        self.on_style_selected = self.styles.append
        self.on_category_selected = self.categories.append


class TrayMenuEventTest(unittest.TestCase):
    def menu(self, tray):
        menu = TrayMenu.__new__(TrayMenu)
        menu.tray = tray
        return menu

    def test_id_ranges_do_not_overlap(self):
        self.assertGreater(ID_DPI_BASE, ID_POLLING_BASE + 32)
        self.assertGreater(ID_STYLE_BASE, ID_DPI_BASE + 8)
        self.assertGreater(ID_CATEGORY_BASE, ID_STYLE_BASE + len(config.TRAY_STYLES))

    def test_polling_and_dpi_events_go_to_the_right_action(self):
        tray = FakeTray()
        menu = self.menu(tray)
        menu.Event(ID_POLLING_BASE + 3, "clicked", None, 0)
        menu.Event(ID_DPI_BASE + 2, "clicked", None, 0)
        self.assertEqual(tray.polled, [8000])
        self.assertEqual(tray.selected, [1600])

    def test_style_and_category_events(self):
        tray = FakeTray()
        menu = self.menu(tray)
        menu.Event(ID_STYLE_BASE + 1, "clicked", None, 0)
        menu.Event(ID_CATEGORY_BASE + 1, "clicked", None, 0)
        self.assertEqual(tray.styles, [config.TRAY_STYLES[1][0]])
        self.assertEqual(tray.categories, [config.TRAY_CATEGORIES[1][0]])


if __name__ == "__main__":
    unittest.main()
