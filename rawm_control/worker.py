"""Background HID worker: owns the device, coalesces writes, emits UI state."""

from __future__ import annotations

import copy
import logging
import os
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)

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
WriteCallback = Callable[[bool, str], None]


class DeviceWorker:
    """Runs on its own thread; callbacks fire on that thread.

    GUI users must marshal callbacks back to the main loop (GLib.idle_add).
    """

    def __init__(
        self,
        on_state: StateCallback,
        on_link: LinkCallback,
        refresh_seconds: float = 30.0,
        on_write: WriteCallback | None = None,
    ) -> None:
        self.on_state = on_state
        self.on_link = on_link
        self.on_write = on_write
        self.refresh_seconds = refresh_seconds
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._pending_patch: dict | None = None
        self._pending_sleep: int | None = None
        self._pending_confirm: dict | None = None
        self._pending_sleep_confirm: int | None = None
        self._baseline_state: MouseState | None = None
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
        self._busy_notified = False

    # -- public API --------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="rawm-hid", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._wake.set()
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

    def submit(self, state: MouseState) -> bool:
        """Queue only changed fields; the worker rebases them on a fresh query.

        This prevents a stale UI snapshot from overwriting settings changed by
        a physical button, another tool, or the vendor web driver.
        """
        with self._lock:
            current = self._state
            patch = {}
            for name in devices.WRITE_FIELDS:
                value = getattr(state, name, None)
                if getattr(current, name, None) != value:
                    patch[name] = copy.deepcopy(value)
            if not patch:
                return False
            if self._pending_patch is None:
                self._pending_patch = {}
            self._pending_patch.update(patch)
            return True

    def submit_sleep_time(self, seconds: int) -> None:
        with self._lock:
            self._pending_sleep = int(seconds)

    @property
    def has_baseline(self) -> bool:
        with self._lock:
            return self._baseline_state is not None

    def restore_baseline(self) -> bool:
        """Restore the snapshot taken when this mouse connected.

        This is a normal, verified patch write; it is not a factory reset.
        """
        with self._lock:
            baseline = copy.deepcopy(self._baseline_state)
            current = copy.deepcopy(self._state)
        if baseline is None:
            return False
        queued = self.submit(baseline)
        if baseline.sleep_time != current.sleep_time:
            self.submit_sleep_time(baseline.sleep_time)
            queued = True
        if not queued:
            self._emit_write(True, "Already at detected settings")
        return True

    def refresh(self) -> None:
        with self._lock:
            self._force_query = True
        self._wake.set()

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
            logger.exception("State callback failed")

    def _emit_link(self, connected: bool, error: str | None = None) -> None:
        self._connected = connected
        try:
            self.on_link(connected, error)
        except Exception:
            logger.exception("Link callback failed")

    def _emit_write(self, ok: bool, message: str) -> None:
        if self.on_write is None:
            return
        try:
            self.on_write(ok, message)
        except Exception:
            logger.exception("Write callback failed")

    def _pick_device(self):
        """Prefer a directly-connected mouse over a receiver dongle."""
        candidates = [
            d
            for d in discover()
            if devices.for_product(d.product_id).mouse
            or devices.for_product(d.product_id).receiver
        ]
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
        frames: list[Frame] = []
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

        # The dongle's paired device must itself be a known mouse.  This
        # prevents a keyboard or an unknown vendor device from being exposed
        # as a writable mouse.
        state_caps = devices.for_product(state.product_id)
        if not state_caps.mouse:
            device.close()
            self._emit_link(
                False,
                "This RAWM device is not a supported mouse. Configuration is "
                "read-only; use `rawmctl report` to submit its data.",
            )
            return False

        self._device = device
        self._last_error = None
        self._warned_permission = False
        self._via_receiver = caps.receiver
        self._receiver_pid = info.product_id if caps.receiver else None
        state.via_receiver = caps.receiver
        state.receiver_product_id = self._receiver_pid
        apply_notifications(state, frames)
        with self._lock:
            self._state = state
        self._baseline_state = copy.deepcopy(state)
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
        self._via_receiver = False
        self._receiver_pid = None
        self._query_misses = 0
        self._baseline_state = None
        dropped = (
            self._pending_confirm is not None
            or self._pending_sleep_confirm is not None
            or self._pending_patch is not None
            or self._pending_sleep is not None
        )
        if self._pending_confirm is not None or self._pending_sleep_confirm is not None:
            self._pending_confirm = None
            self._pending_sleep_confirm = None
            self._emit_write(False, "Device disconnected before confirming the change")
        elif dropped:
            self._emit_write(False, "Device disconnected before the change was sent")
        with self._lock:
            self._state = MouseState()
            self._pending_patch = None
            self._pending_sleep = None
        self._emit_link(False, reason)

    def _preserve_runtime_fields(self, fresh: MouseState) -> MouseState:
        """Carry connection metadata and runtime-only values across queries.

        Notifications are applied *after* this method so a calibration or RSSI
        frame received during the query wins over the previous snapshot.
        """
        with self._lock:
            previous = self._state
        fresh.via_receiver = self._via_receiver
        fresh.receiver_product_id = self._receiver_pid
        fresh.battery_levels = previous.battery_levels or fresh.battery_levels
        fresh.rssi = previous.rssi
        fresh.surface_quality = previous.surface_quality
        return fresh

    def _perform_query(self, requested: bool = False) -> None:
        device = self._device
        if device is None:
            return
        try:
            state, frames = device.query(timeout=1.4, base=self.state)
        except ProtocolError as exc:
            self._disconnect(str(exc))
            return
        document = getattr(device, "last_document", None)
        if state is None:
            # A sleeping mouse simply does not answer. Keep the last known
            # state alive; only give up if reads/writes fail or the node goes.
            self._query_misses += 1
            if self._pending_confirm is not None or self._pending_sleep_confirm is not None:
                self._pending_confirm = None
                self._pending_sleep_confirm = None
                self._emit_write(False, "Mouse did not answer the confirmation query")
            # A user-requested refresh should fail fast.  For the background
            # poll, allow one transient miss but do not keep a stale battery
            # reading forever after the mouse is switched off.
            threshold = 1 if requested else 2
            if self._query_misses >= threshold:
                self._disconnect(
                    "Mouse is not responding. Turn it on or move it, then press Retry."
                )
            return
        self._query_misses = 0
        # Receiver metadata and runtime-only values belong to the connection,
        # not to the JSON query result.  Apply them first so notifications that
        # arrived in the same read batch can still update battery calibration,
        # RSSI and surface quality.
        state = self._preserve_runtime_fields(state)
        _, notified = apply_notifications(state, frames)
        if self._pending_confirm is not None:
            expected = self._pending_confirm
            self._pending_confirm = None
            ok = all(
                (
                    not isinstance(document, dict)
                    or name in notified
                    or protocol.query_field_present(document, name)
                )
                and protocol.values_match(name, getattr(state, name, None), value)
                for name, value in expected.items()
            )
            self._emit_write(
                ok,
                "Saved to mouse" if ok else "Mouse did not confirm the requested change",
            )
        if self._pending_sleep_confirm is not None:
            expected_sleep = self._pending_sleep_confirm
            self._pending_sleep_confirm = None
            present = (
                not isinstance(document, dict)
                or "sleep_time" in notified
                or protocol.query_field_present(document, "sleep_time")
            )
            ok = present and abs(state.sleep_time - expected_sleep) < 30
            self._emit_write(
                ok,
                "Sleep timer saved" if ok else "Mouse did not confirm the sleep timer",
            )
        with self._lock:
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
            pending_patch = self._pending_patch
            pending_sleep = self._pending_sleep
            force = self._force_query
            want_rssi = self._read_rssi
            self._pending_patch = None
            self._pending_sleep = None
            self._force_query = False
            self._read_rssi = False

        lock_held = False
        if pending_patch is not None or pending_sleep is not None:
            try:
                device.lock_exclusive()
                lock_held = True
                self._busy_notified = False
            except protocol.DeviceBusy as exc:
                # Do not lose the edit just because another process is
                # configuring the mouse.  Put it back, preserving anything the
                # user queued while we were blocked, and retry shortly.
                with self._lock:
                    if pending_patch is not None:
                        merged = dict(pending_patch)
                        if self._pending_patch:
                            merged.update(self._pending_patch)
                        self._pending_patch = merged
                    if pending_sleep is not None and self._pending_sleep is None:
                        self._pending_sleep = pending_sleep
                if not self._busy_notified:
                    self._busy_notified = True
                    self._emit_write(False, str(exc))
                self._stop.wait(0.25)
                return
        else:
            self._busy_notified = False

        try:
            if pending_patch is not None:
                # Rebase the user's intent onto a fresh complete snapshot.
                fresh, frames = device.query(timeout=1.4, base=self.state)
                if fresh is None:
                    self._emit_write(False, "Mouse did not answer; change not saved")
                    return
                # Preserve first, then let notifications win.
                fresh = self._preserve_runtime_fields(fresh)
                apply_notifications(fresh, frames)
                error = devices.validate_patch(fresh, pending_patch)
                if error:
                    self._emit_write(False, f"Change rejected: {error}")
                    return
                for name, value in pending_patch.items():
                    setattr(fresh, name, copy.deepcopy(value))
                device.set_state(fresh)
                with self._lock:
                    self._state = copy.deepcopy(fresh)
                self._pending_confirm = copy.deepcopy(pending_patch)
                self._confirm_at = time.monotonic() + 0.4
                self._emit_state(set())
            if pending_sleep is not None:
                device.set_sleep_time(pending_sleep, crc=self.state.crc)
                with self._lock:
                    state = copy.deepcopy(self._state)
                    state.sleep_time = pending_sleep
                    self._state = state
                self._pending_sleep_confirm = pending_sleep
                self._confirm_at = time.monotonic() + 0.4
            if want_rssi:
                device.read_rssi(crc=self.state.crc)
        except ProtocolError as exc:
            if pending_patch is not None or pending_sleep is not None:
                self._emit_write(False, f"Write failed: {exc}")
            self._disconnect(str(exc))
            return
        finally:
            if lock_held:
                device.unlock()

        # Block on the fd instead of waking every ~170 ms.  0.5 s still gives
        # prompt notification handling while keeping an idle tray almost free.
        if not device.read_ready(0.5):
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
            self._perform_query(requested=force)

    def _consume(self, frames: list[Frame]) -> None:
        with self._lock:
            state = copy.deepcopy(self._state)
        changed: set[str] = set()
        for frame in frames:
            if frame.cmd == CMD_QUERY_RESULT:
                try:
                    import json

                    new = state_from_query(json.loads(frame.payload.rstrip(b"\x00")), state)
                except (ValueError, UnicodeDecodeError, ProtocolError):
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
                try:
                    connected = self._connect()
                except Exception as exc:
                    # _connect() must never kill the worker thread.  Most
                    # transport errors are ProtocolError, but a platform or
                    # sysfs failure can still surface as OSError.
                    logger.exception("Connection attempt failed")
                    if self._device is not None:
                        self._device.close()
                        self._device = None
                    self._emit_link(False, f"Connection error: {exc}")
                    connected = False
                if connected:
                    backoff = 0.5
                    continue
                self._wake.wait(backoff)
                self._wake.clear()
                backoff = min(backoff * 1.6, 3.0)
                continue
            try:
                self._loop_connected()
            except Exception as exc:  # never let a firmware quirk kill the worker
                logger.exception("Worker loop failed; reconnecting")
                self._disconnect(f"worker error: {exc}")
                self._stop.wait(1.0)
                continue
            self._stop.wait(0.01)
        self._disconnect(None)


class DemoWorker:
    """In-memory stand-in used by ``--demo`` for UI work and screenshots."""

    def __init__(self, on_state: StateCallback, on_link: LinkCallback, refresh_seconds: float = 30.0, on_write: WriteCallback | None = None) -> None:
        self.on_state = on_state
        self.on_link = on_link
        self.on_write = on_write
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
        self._baseline_state = copy.deepcopy(self._state)
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
        # DemoWorker has no thread to stop; keep this as a safe no-op.
        self._stop.set()

    def submit(self, state: MouseState) -> bool:
        self._state = copy.deepcopy(state)
        self.on_state(copy.deepcopy(self._state), set())
        if self.on_write is not None:
            self.on_write(True, "Saved to mouse (demo)")
        return True

    @property
    def has_baseline(self) -> bool:
        return self._baseline_state is not None

    def restore_baseline(self) -> bool:
        if self._baseline_state is None:
            return False
        self._state = copy.deepcopy(self._baseline_state)
        self.on_state(copy.deepcopy(self._state), set())
        if self.on_write is not None:
            self.on_write(True, "Restored detected settings (demo)")
        return True

    def submit_sleep_time(self, seconds: int) -> None:
        self._state.sleep_time = seconds
        self.on_state(copy.deepcopy(self._state), {"sleep_time"})
        if self.on_write is not None:
            self.on_write(True, "Sleep timer saved (demo)")

    def refresh(self) -> None:
        self.on_state(copy.deepcopy(self._state), set())

    def request_rssi(self) -> None:
        return None
