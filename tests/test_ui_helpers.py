"""Pure-ish helpers for combo refresh and edit debouncing."""

from __future__ import annotations

import unittest

from gi.repository import GLib

from rawm_control.protocol import MouseState
from rawm_control.ui import MainWindow, _set_combo_labels


class FakeModel:
    def __init__(self, labels):
        self.labels = list(labels)

    def get_n_items(self):
        return len(self.labels)

    def get_string(self, index):
        return self.labels[index]


class FakeCombo:
    def __init__(self, labels=None):
        self.model = FakeModel(labels or [])
        self.replaced = 0

    def get_model(self):
        return self.model

    def set_model(self, model):
        self.replaced += 1
        self.model = model


class UiHelperTest(unittest.TestCase):
    def test_combo_is_not_rebuilt_for_identical_labels(self):
        combo = FakeCombo(["1000 Hz", "2000 Hz"])
        _set_combo_labels(combo, ["1000 Hz", "2000 Hz"])
        self.assertEqual(combo.replaced, 0)

    def test_combo_is_rebuilt_when_labels_change(self):
        combo = FakeCombo(["1000 Hz"])
        _set_combo_labels(combo, ["1000 Hz", "2000 Hz"])
        self.assertEqual(combo.replaced, 1)

    def test_edit_debounce_writes_once(self):
        window = MainWindow.__new__(MainWindow)
        window._edit_timer = 0
        window._state = MouseState(product_id=0x2338)
        writes = []
        window._write = lambda state, toast=None: writes.append(state)

        window._schedule_write()
        window._schedule_write()

        loop = GLib.MainLoop()
        GLib.timeout_add(400, loop.quit)
        loop.run()

        self.assertEqual(len(writes), 1)


if __name__ == "__main__":
    unittest.main()
