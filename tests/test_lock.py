"""Cross-process write lock regression tests."""

from __future__ import annotations

import unittest

from rawm_control.protocol import DeviceBusy, RawmDevice


class DeviceLockTest(unittest.TestCase):
    def test_second_writer_is_rejected_then_lock_can_be_released(self):
        first = RawmDevice("/dev/null")
        second = RawmDevice("/dev/null")
        first.open()
        second.open()
        try:
            first.lock_exclusive()
            with self.assertRaises(DeviceBusy):
                second.lock_exclusive()
            first.close()
            second.lock_exclusive()
            second.unlock()
        finally:
            first.close()
            second.close()

    def test_closing_a_device_unlocks_it(self):
        first = RawmDevice("/dev/null")
        second = RawmDevice("/dev/null")
        first.open()
        second.open()
        first.lock_exclusive()
        first.close()
        try:
            second.lock_exclusive()
        finally:
            second.close()


if __name__ == "__main__":
    unittest.main()
