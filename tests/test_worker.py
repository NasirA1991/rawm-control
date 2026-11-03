"""Regression tests for connection lifecycle bugs in DeviceWorker."""

from __future__ import annotations

import unittest

from rawm_control.protocol import MouseState
from rawm_control.worker import DeviceWorker


class FakeDevice:
    def __init__(self, path: str, result):
        self.path = path
        self.result = result
        self.closed = False
        self.is_open = True

    def query(self, timeout: float = 1.4):
        return self.result

    def close(self) -> None:
        self.closed = True
        self.is_open = False


class WorkerLifecycleTest(unittest.TestCase):
    def make_worker(self):
        states = []
        links = []
        worker = DeviceWorker(
            lambda state, changed: states.append((state, changed)),
            lambda connected, error: links.append((connected, error)),
            refresh_seconds=3600,
        )
        return worker, states, links

    def test_receiver_metadata_survives_refresh(self):
        worker, states, _links = self.make_worker()
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

    def test_missing_node_after_misses_disconnects_without_nameerror(self):
        worker, _states, links = self.make_worker()
        path = "/tmp/rawm-control-node-that-does-not-exist"
        fake = FakeDevice(path, (None, []))
        worker._device = fake
        worker._query_misses = 7

        worker._perform_query()  # this used to raise NameError

        self.assertIsNone(worker._device)
        self.assertTrue(fake.closed)
        self.assertFalse(worker._via_receiver)
        self.assertEqual(links[-1][0], False)

    def test_disconnect_clears_receiver_metadata(self):
        worker, _states, _links = self.make_worker()
        worker._device = FakeDevice("/dev/hidraw-test", (MouseState(), []))
        worker._via_receiver = True
        worker._receiver_pid = 0x232B

        worker._disconnect("test")

        self.assertFalse(worker._via_receiver)
        self.assertIsNone(worker._receiver_pid)
        self.assertIsNone(worker._device)


if __name__ == "__main__":
    unittest.main()
