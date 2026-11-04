"""Regression tests for connection lifecycle bugs in DeviceWorker."""

from __future__ import annotations

import unittest

from unittest.mock import patch

from rawm_control.protocol import CMD_QUERY_RESULT, Frame, HidrawDevice, MouseState
from rawm_control.worker import DeviceWorker


class FakeDevice:
    def __init__(self, path: str, result=None, results=None):
        self.path = path
        self.result = result
        self.results = list(results or [])
        self.closed = False
        self.is_open = True
        self.written = []

    def query(self, timeout: float = 1.4):
        if self.results:
            return self.results.pop(0)
        return self.result

    def set_state(self, state):
        self.written.append(state)

    def read_ready(self, timeout: float = 0.0):
        return False

    def drain(self, timeout: float = 0.0):
        return []

    def close(self) -> None:
        self.closed = True
        self.is_open = False


class WorkerLifecycleTest(unittest.TestCase):
    def make_worker(self):
        states = []
        links = []
        writes = []
        worker = DeviceWorker(
            lambda state, changed: states.append((state, changed)),
            lambda connected, error: links.append((connected, error)),
            refresh_seconds=3600,
            on_write=lambda ok, message: writes.append((ok, message)),
        )
        return worker, states, links, writes

    def test_receiver_metadata_survives_refresh(self):
        worker, states, _links, _writes = self.make_worker()
        mouse = MouseState(
            device_name="ER21Pro",
            product_id=0x2338,
            polling_rate=1000,
        )
        worker._device = FakeDevice("/dev/hidraw-test", (mouse, []))
        worker._via_receiver = True
        worker._receiver_pid = 0x232B
        worker._state = mouse

        worker._perform_query()

        state = worker.state
        self.assertTrue(state.via_receiver)
        self.assertEqual(state.receiver_product_id, 0x232B)
        self.assertEqual(state.product_id, 0x2338)
        self.assertTrue(states)

    def test_user_refresh_disconnects_immediately_on_miss(self):
        worker, _states, links, _writes = self.make_worker()
        fake = FakeDevice("/dev/null", result=(None, []))
        worker._device = fake
        worker._perform_query(requested=True)
        self.assertIsNone(worker._device)
        self.assertTrue(fake.closed)
        self.assertFalse(links[-1][0])

    def test_periodic_poll_tolerates_one_miss_then_disconnects(self):
        worker, _states, links, _writes = self.make_worker()
        fake = FakeDevice("/dev/null", result=(None, []))
        worker._device = fake
        worker._perform_query()
        self.assertIsNotNone(worker._device)
        worker._perform_query()
        self.assertIsNone(worker._device)
        self.assertFalse(links[-1][0])

    def test_missing_node_after_misses_disconnects_without_nameerror(self):
        worker, _states, links, _writes = self.make_worker()
        path = "/tmp/rawm-control-node-that-does-not-exist"
        fake = FakeDevice(path, (None, []))
        worker._device = fake
        worker._query_misses = 7

        worker._perform_query()  # this used to raise NameError

        self.assertIsNone(worker._device)
        self.assertTrue(fake.closed)
        self.assertFalse(worker._via_receiver)
        self.assertEqual(links[-1][0], False)

    def test_write_rebases_patch_on_fresh_state_and_confirms(self):
        worker, _states, _links, writes = self.make_worker()
        old = MouseState(product_id=0x2338, cpi=1600, motion_sync=0)
        fresh = MouseState(product_id=0x2338, cpi=1600, motion_sync=1)
        confirmed = MouseState(product_id=0x2338, cpi=3200, motion_sync=1)
        fake = FakeDevice("/dev/null", result=(confirmed, []), results=[(fresh, [])])
        worker._device = fake
        worker._state = old
        worker._last_query = 0

        wanted = MouseState(product_id=0x2338, cpi=3200, motion_sync=0)
        worker.submit(wanted)
        worker._loop_connected()

        self.assertEqual(len(fake.written), 1)
        self.assertEqual(fake.written[0].cpi, 3200)
        # An external motion-sync change must survive the CPI patch.
        self.assertEqual(fake.written[0].motion_sync, 1)

        worker._perform_query()
        self.assertEqual(writes[-1][0], True)

    def test_pick_device_skips_keyboard(self):
        keyboard = HidrawDevice(path="/dev/null", name="AK60", product_id=0x2345)
        mouse = HidrawDevice(path="/dev/null", name="ER21Pro", product_id=0x2338)
        worker, _states, _links, _writes = self.make_worker()
        with patch("rawm_control.worker.discover", return_value=[keyboard, mouse]):
            self.assertEqual(worker._pick_device().product_id, 0x2338)
        with patch("rawm_control.worker.discover", return_value=[keyboard]):
            self.assertIsNone(worker._pick_device())

    def test_capability_matrix_rejects_unsupported_writes(self):
        from rawm_control import devices

        for caps in devices.all_capabilities():
            if not caps.mouse:
                continue
            state = MouseState(product_id=caps.product_id)
            if not caps.angle_tuning:
                self.assertIsNotNone(devices.validate_patch(state, {"angle_tuning": 5}))
            if not caps.glass_mode:
                self.assertIsNotNone(devices.validate_patch(state, {"glass_mode_enabled": 1}))

    def test_unknown_and_keyboard_are_not_writable(self):
        from rawm_control import devices

        self.assertFalse(devices.for_product(0xDEAD).mouse)
        self.assertFalse(devices.for_product(0x2345).mouse)  # AK60 keyboard
        self.assertTrue(devices.for_product(0x2338).mouse)
        self.assertIsNotNone(devices.validate_patch(MouseState(product_id=0xDEAD), {"cpi": 1600}))
        self.assertIsNotNone(devices.validate_patch(MouseState(product_id=0x2345), {"cpi": 1600}))

    def test_restore_baseline_queues_only_changed_fields(self):
        worker, _states, _links, _writes = self.make_worker()
        worker._state = MouseState(product_id=0x2338, cpi=3200, sleep_time=600)
        worker._baseline_state = MouseState(product_id=0x2338, cpi=1600, sleep_time=300)

        self.assertTrue(worker.has_baseline)
        self.assertTrue(worker.restore_baseline())
        self.assertEqual(worker._pending_patch["cpi"], 1600)
        self.assertEqual(worker._pending_sleep, 300)

    def test_restore_without_baseline_is_rejected(self):
        worker, _states, _links, _writes = self.make_worker()
        self.assertFalse(worker.has_baseline)
        self.assertFalse(worker.restore_baseline())

    def test_malformed_query_frame_does_not_escape_consume(self):
        worker, _states, _links, _writes = self.make_worker()
        worker._state = MouseState(product_id=0x2338)
        frame = Frame(cmd=CMD_QUERY_RESULT, size=4, subtype=0, data=b"[]")
        worker._consume([frame])
        self.assertEqual(worker.state.product_id, 0x2338)

    def test_disconnect_clears_receiver_metadata(self):
        worker, _states, _links, _writes = self.make_worker()
        worker._device = FakeDevice("/dev/hidraw-test", (MouseState(), []))
        worker._via_receiver = True
        worker._receiver_pid = 0x232B

        worker._disconnect("test")

        self.assertFalse(worker._via_receiver)
        self.assertIsNone(worker._receiver_pid)
        self.assertIsNone(worker._device)


if __name__ == "__main__":
    unittest.main()
