"""Background HID worker: owns the device, coalesces writes, emits UI state."""

from __future__ import annotations

import copy
import os
import threading
import time
from typing import Callable

from . import devices, protocol
from .protocol import (
    CMD_QUERY_RESULT,
    Frame,
    MouseState,
    ProtocolError,
    RawmDevice,
    apply_notifications,
    discover,
    state_from_query,
)

StateCallback = Callable[[MouseState, set[str]], None]
LinkCallback = Callable[[bool, str | None], None]


class DeviceWorker:
    """Runs on its own thread; callbacks fire on that thread.

    GUI users must marshal callbacks back to the main loop (GLib.idle_add).
    """

    def __init__(
        self,
        on_state: StateCallback,
        on_link: LinkCallback,
        refresh_seconds: float = 30.0,
    ) -> None:
        self.on_state = on_state
        self.on_link = on_link
        self.refresh_seconds = refresh_seconds
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._pending_state: MouseState | None = None
        self._pending_sleep: int | None = None
        self._force_query = False
        self._read_rssi = False
        self._state = MouseState()
        self._device: RawmDevice | None = None
        self._connected = False
        self._last_error: str | None = None
        self._last_query = 0.0
        self._confirm_at = 0.0
        self._query_misses = 0
        self._via_receiver = False
        self._receiver_pid: int | None = None
        self._warned_permission = False

    # -- public API --------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="rawm-hid", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout)

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def state(self) -> MouseState:
        with self._lock:
            return copy.deepcopy(self._state)

    @property
    def device_path(self) -> str | None:
        return self._device.path if self._device else None

    @property
    def capabilities(self) -> devices.Capabilities:
        return devices.for_state(self.state)

    def submit(self, state: MouseState) -> None:
        """Queue a full parameter-block write (last write wins)."""
        with self._lock:
            self._pending_state = copy.deepcopy(state)

    def submit_sleep_time(self, seconds: int) -> None:
        with self._lock:
            self._pending_sleep = int(seconds)

    def refresh(self) -> None:
        with self._lock:
            self._force_query = True

    def request_rssi(self) -> None:
        with self._lock:
            self._read_rssi = True

    # -- internals ---------------------------------------------------------
    def _emit_state(self, changed: set[str] | None = None) -> None:
        with self._lock:
            snapshot = copy.deepcopy(self._state)
        try:
            self.on_state(snapshot, changed or set())
        except Exception:  # a UI callback must never kill the worker
            pass

    def _emit_link(self, connected: bool, error: str | None = None) -> None:
        self._connected = connected
        try:
            self.on_link(connected, error)
        except Exception:
            pass

    def _pick_device(self):
        """Prefer a directly-connected mouse over a receiver dongle."""
        candidates = discover()
        if not candidates:
            return None
        candidates.sort(
            key=lambda d: (
                devices.for_product(d.product_id).receiver,
                "receiver" in (d.name or "").lower(),
            )
        )
        return candidates[0]

    def _connect(self) -> bool:
        info = self._pick_device()
        if info is None:
            return False
        device = RawmDevice(info.path)
        try:
            device.open()
        except protocol.PermissionDenied as exc:
            if not self._warned_permission:
                self._warned_permission = True
                self._emit_link(False, str(exc))
            return False
        except ProtocolError as exc:
            self._emit_link(False, str(exc))
            return False

        caps = devices.for_product(info.product_id)
        state = None
        frames = []
        last_error: str | None = None

        if caps.receiver:
            # The dongle itself only describes the dongle.  The paired mouse is
            # a "virtual client" on ESB channel 0 (ESB_CHANNEL_MOUSE).
            try:
                device.query(timeout=1.0)
            except ProtocolError:
                pass
            device.channel = 0
            for _attempt in range(3):
                try:
                    state, frames = device.query(timeout=2.0)
                except ProtocolError as exc:
                    last_error = str(exc)
                    state = None
                    frames = []
                if state is not None and not devices.for_product(state.product_id).receiver:
                    break
                state = None
                time.sleep(0.35)
            if state is None:
                device.close()
                self._emit_link(
                    False,
                    "Receiver connected, but the paired mouse is asleep. "
                    "Turn the mouse on or move it, then press Retry.",
                )
                return False
        else:
            for _attempt in range(3):
                try:
                    state, frames = device.query(timeout=1.4)
                except ProtocolError as exc:
                    last_error = str(exc)
                    state = None
                    frames = []
                if state is not None:
                    break
                time.sleep(0.25)

        if state is None:
            device.close()
            self._emit_link(False, last_error or "mouse did not answer the query")
            return False

        self._device = device
        self._last_error = None
        self._warned_permission = False
        self._via_receiver = caps.receiver
        self._receiver_pid = info.product_id if caps.receiver else None
        state.via_receiver = caps.receiver
        state.receiver_product_id = self._receiver_pid
        with self._lock:
            self._state = state
        apply_notifications(state, frames)
        self._emit_link(True, None)
        self._emit_state(set())
        self._last_query = time.monotonic()
        try:
            device.read_rssi(crc=state.crc)
        except ProtocolError:
            pass
        return True

    def _disconnect(self, reason: str | None = None) -> None:
        if self._device is not None:
            self._device.close()
        self._device = None
        with self._lock:
            self._state = MouseState()
            self._pending_state = None
        self._emit_link(False, reason)

    def _perform_query(self) -> None:
        assert self._device is not None
        try:
            state, frames = self._device.query(timeout=1.4)
        except ProtocolError as exc:
            self._disconnect(str(exc))
            return
        if state is None:
            # A sleeping mouse simply does not answer. Keep the last known
            # state alive; only give up if reads/writes fail or the node goes.
            self._query_misses += 1
            if self._query_misses >= 8 and not os.path.exists(device.path):
                self._disconnect("device disappeared")
            return
        self._query_misses = 0
        self._via_receiver = False
        self._receiver_pid: int | None = None
        apply_notifications(state, frames)
        with self._lock:
            previous = self._state
            # keep values only the notifications know about
            state.battery_levels = previous.battery_levels or state.battery_levels
            state.rssi = previous.rssi
            state.via_receiver = self._via_receiver
            state.receiver_product_id = self._receiver_pid
            self._state = state
        self._last_query = time.monotonic()
        self._emit_state(set())

    def _loop_connected(self) -> None:
        assert self._device is not None
        device = self._device
        if not os.path.exists(device.path):
            self._disconnect("device unplugged")
            return

        with self._lock:
            pending_state = self._pending_state
            pending_sleep = self._pending_sleep
            force = self._force_query
            want_rssi = self._read_rssi
            self._pending_state = None
            self._pending_sleep = None
            self._force_query = False
            self._read_rssi = False

        try:
            if pending_state is not None:
                device.set_state(pending_state)
                with self._lock:
                    self._state = copy.deepcopy(pending_state)
                self._confirm_at = time.monotonic() + 0.4
            if pending_sleep is not None:
                device.set_sleep_time(pending_sleep, crc=self.state.crc)
                with self._lock:
                    self._state.sleep_time = pending_sleep
                self._confirm_at = time.monotonic() + 0.4
            if want_rssi:
                device.read_rssi(crc=self.state.crc)
        except ProtocolError as exc:
            self._disconnect(str(exc))
            return

        if not device.read_ready(0.15):
            pass
        else:
            try:
                frames = device.drain(0.05)
            except ProtocolError as exc:
                self._disconnect(str(exc))
                return
            if frames:
                self._consume(frames)

        now = time.monotonic()
        if self._confirm_at and now >= self._confirm_at:
            self._confirm_at = 0.0
            self._perform_query()
            return
        if force or now - self._last_query >= self.refresh_seconds:
            self._perform_query()

    def _consume(self, frames: list[Frame]) -> None:
        with self._lock:
            state = self._state
        changed: set[str] = set()
        for frame in frames:
            if frame.cmd == CMD_QUERY_RESULT:
                try:
                    import json

                    new = state_from_query(json.loads(frame.payload.rstrip(b"\x00")), state)
                except (ValueError, UnicodeDecodeError):
                    continue
                state = new
                changed.update({"all"})
                self._last_query = time.monotonic()
            else:
                state, more = apply_notifications(state, [frame])
                changed |= more
        with self._lock:
            self._state = state
        if changed:
            self._emit_state(changed)

    def _run(self) -> None:
        backoff = 0.5
        while not self._stop.is_set():
            if self._device is None or not self._device.is_open:
                if self._connect():
                    backoff = 0.5
                    continue
                self._stop.wait(backoff)
                backoff = min(backoff * 1.6, 3.0)
                continue
            self._loop_connected()
            self._stop.wait(0.02)
        self._disconnect(None)


class DemoWorker:
    """In-memory stand-in used by ``--demo`` for UI work and screenshots."""

    def __init__(self, on_state: StateCallback, on_link: LinkCallback, refresh_seconds: float = 30.0) -> None:
        self.on_state = on_state
        self.on_link = on_link
        self.refresh_seconds = refresh_seconds
        self._connected = True
        self._state = MouseState(
            device_name="ER21Pro",
            product_id=0x2338,
            firmware="G-1.0.0",
            firmware_code=1,
            sensor="PAW3950",
            battery=87,
            charging=False,
            wired=False,
            via_receiver=True,
            receiver_product_id=0x232B,
            cpi=1600,
            cpi_levels=[400, 800, 1600, 3200, 0, 0, 0, 0],
            cpi_level_colors=[4, 2, 6, 4, 0, 0, 0, 0],
            polling_rate=8000,
            lod=2,
            power_mode=2,
            motion_sync=1,
            angle_tuning=0,
            angle_snapping=0,
            ripple_control=1,
            light=0x30,
            key_delay=[34, 34, 136, 136, 136, 136, 136],
            sleep_time=300,
            tx_output_power=8,
            auto_tx_power=1,
            onboard=0,
            onboard_count=4,
            onboard_status=[3, 130, 134, 132],
            crc=True,
            esb_address="392bf4bc05f0b15df8f9fafbfcfdfeff",
            rssi=-42,
        )
        self._started = False
        self._stop = threading.Event()

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def state(self) -> MouseState:
        return copy.deepcopy(self._state)

    @property
    def device_path(self) -> str | None:
        return None

    @property
    def capabilities(self):
        return devices.for_state(self._state)

    def start(self) -> None:
        self._started = True
        self.on_link(True, None)
        self.on_state(copy.deepcopy(self._state), set())

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()

    def submit(self, state: MouseState) -> None:
        self._state = copy.deepcopy(state)
        self.on_state(copy.deepcopy(self._state), set())

    def submit_sleep_time(self, seconds: int) -> None:
        self._state.sleep_time = seconds
        self.on_state(copy.deepcopy(self._state), {"sleep_time"})

    def refresh(self) -> None:
        self.on_state(copy.deepcopy(self._state), set())

    def request_rssi(self) -> None:
        return None
