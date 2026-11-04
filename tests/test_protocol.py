"""Unit tests for the recovered protocol (no hardware required).

Run with:  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import struct
import unittest

from unittest.mock import patch

from rawm_control import devices, protocol
from rawm_control.protocol import (
    RawmDevice,
    CMD_QUERY,
    CONFIG_TYPE_MOUSE_PARAM,
    FrameStream,
    MouseState,
    ProtocolError,
    encode_event,
    encode_mouse_param,
    encode_mouse_param_frame,
    encode_query_frame,
    report_payloads,
    state_from_query,
)


class CrcTests(unittest.TestCase):
    def test_vectors_match_original_javascript(self):
        # Expected values were produced by the exact crc16_compute() shipped in
        # the RAWM HUB web driver and are masked to 16 bits like the firmware.
        self.assertEqual(protocol.crc16(b""), 0xFFFF)
        self.assertEqual(protocol.crc16(b"\x00"), 0xE1F0)
        self.assertEqual(protocol.crc16(b"\x01\x02\x03"), 0xADAD)
        self.assertEqual(
            protocol.crc16(bytes([0x01, 0x0B, 0x03, 0, 0, 0x92, 0x2F, 0xE9, 0x6A, 0, 0])),
            0xD918,
        )


class FramingTests(unittest.TestCase):
    def test_report_payload(self):
        payload = b"\xff\xff\xff\xff" + encode_event(0x0B, 0x17, b"\x64\x00")
        report = bytes([0x80 | len(payload)]) + payload
        report += b"\x00" * (64 - len(report))
        self.assertEqual(report_payloads(report), payload)

    def test_buffer_size_reports_are_ignored(self):
        report = bytes([0x40 | 0x12]) + b"\x00" * 63
        self.assertEqual(report_payloads(report), b"")
        self.assertEqual(report_payloads(bytes([0x00] * 64)), b"")

    def test_stream_reassembles_split_frames(self):
        stream = FrameStream()
        first = encode_event(0x0B, 0x17, b"\x64\x00")
        second = encode_event(0x0B, 0x0D, b"\x01")
        wire = b"\xff\xff\xff\xff" + first + b"\xff\xff\xff\xff" + second
        frames = []
        for cut in range(0, len(wire), 3):
            frames += stream.feed(wire[cut : cut + 3])
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0].cmd, 0x0B)
        self.assertEqual(frames[0].subtype, 0x17)
        self.assertEqual(frames[0].data, b"\x64\x00")
        self.assertEqual(frames[1].subtype, 0x0D)
        self.assertEqual(frames[1].data, b"\x01")

    def test_stream_skips_garbage_before_marker(self):
        stream = FrameStream()
        frame = encode_event(0x0B, 0x17, b"\x32\x00")
        frames = stream.feed(b"\x01\x02\x03\xff\xff\xff\xff" + frame)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].data, b"\x32\x00")

    def test_long_frame(self):
        stream = FrameStream()
        payload = b"{" + b"x" * 500 + b"}"
        data = payload[1:]
        frame = encode_event(0x02, payload[0], data)
        self.assertGreater(len(frame), 63)
        frames = stream.feed(b"\xff\xff\xff\xff" + frame)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].size, len(frame))


class EncodingTests(unittest.TestCase):
    def test_query_frame(self):
        frame = encode_query_frame()
        self.assertEqual(frame[0] & 0x0F, CMD_QUERY)
        self.assertEqual(frame[1], len(frame))
        self.assertEqual(frame[2], 3)  # OS_PC
        self.assertEqual(len(frame), 11)

    def test_param_layout(self):
        state = MouseState(
            cpi=1600,
            polling_rate=1000,
            cpi_levels=[400, 800, 1600, 3200, 0, 0, 0, 0],
            cpi_level_colors=[4, 2, 6, 4, 0, 0, 0, 0],
            lod=2,
            power_mode=2,
            motion_sync=1,
            angle_tuning=-5,
            angle_snapping=0,
            ripple_control=0,
            light=0x30,
            key_delay=[34, 34, 136, 136, 136, 136, 136],
            tx_output_power=8,
            auto_tx_power=1,
            onboard=0,
            onboard_status=[3, 130, 134, 132],
            battery_levels=protocol.DEFAULT_BATTERY_LEVELS,
            glass_mode_enabled=0,
        )
        data = encode_mouse_param(state)
        self.assertEqual(len(data), 82)
        self.assertEqual(struct.unpack_from("<H", data, 0)[0], 1600)
        self.assertEqual(struct.unpack_from("<H", data, 2)[0], 1000)
        self.assertEqual(data[4], 0x30)
        self.assertEqual(data[5], 8)  # level count
        self.assertEqual(struct.unpack_from("<H", data, 6)[0], 400)
        self.assertEqual(data[22], 0)  # onboard
        self.assertEqual(data[23], 2)  # power mode
        self.assertEqual(data[29], 2)  # LOD
        self.assertEqual(data[30], 7)  # key delay count
        self.assertEqual(data[38], 1)  # motion sync
        self.assertEqual(struct.unpack_from("<b", data, 39)[0], -5)
        self.assertEqual(data[42], 8)  # colour count
        self.assertEqual(data[51], 8)  # tx power
        self.assertEqual(data[52], 11)  # battery level count

    def test_param_crc_envelope(self):
        frame = encode_mouse_param_frame(MouseState(), crc=True)
        self.assertEqual(frame[2], protocol.CONFIG_TYPE_CRC)
        total = ((frame[0] << 4) & 0xF00) | frame[1]
        self.assertEqual(total, len(frame))
        self.assertEqual(frame[0] & 0x0F, protocol.CMD_CONFIG)

    def test_32bit_cpi_path(self):
        state = MouseState(cpi=70000, cpi_levels=[70000, 80000, 0, 0, 0, 0, 0, 0])
        data = encode_mouse_param(state)
        self.assertEqual(struct.unpack_from("<H", data, 0)[0], 0)  # 16-bit field unused
        self.assertEqual(data[5], 0)  # 16-bit level count is zero
        self.assertEqual(struct.unpack_from("<I", data, 8)[0], 70000)
        self.assertEqual(data[12], 8)
        self.assertEqual(struct.unpack_from("<I", data, 13)[0], 70000)


class StateTests(unittest.TestCase):
    def test_parse_query_document(self):
        doc = {
            "r": "G-1.0.0",
            "rc": 1,
            "dn": "ER21Pro",
            "pi": 0x2338,
            "vi": 0x1915,
            "battery": 87,
            "chr": 0,
            "cpi": 1600,
            "polling": 1000,
            "light": 48,
            "cpi_l": [400, 800, 1600, 0, 0, 0, 0, 0],
            "cpi_l_c": [4, 2, 6, 0, 0, 0, 0, 0],
            "lod": 2,
            "pm": 3,
            "ms": 1,
            "at": -12,
            "as": 1,
            "rctrl": 1,
            "kd": [8, 8, 8, 8, 8, 8, 8],
            "st": 300,
            "crc": 1,
            "gm": [0, 1],
            "ocn": 4,
            "ocs": [3, 130, 134, 132],
            "sst": "PAW3950",
        }
        state = state_from_query(doc)
        self.assertEqual(state.device_name, "ER21Pro")
        self.assertEqual(state.product_id, 0x2338)
        self.assertEqual(state.battery, 87)
        self.assertFalse(state.charging)
        self.assertEqual(state.angle_tuning, -12)
        self.assertEqual(state.power_mode_name, "Gaming+")
        self.assertTrue(state.crc)
        self.assertEqual(state.onboard_status, [3, 130, 134, 132])
        self.assertEqual(state.sensor, "PAW3950")

    def test_assist_notification_updates_surface_quality(self):
        from rawm_control.protocol import Frame, apply_notifications

        state = MouseState()
        frame = Frame(cmd=0x0B, size=6, subtype=0x03, data=b"\x8c\x00\x08")
        state, changed = apply_notifications(state, [frame])
        self.assertEqual(state.surface_quality, 0x8C)
        self.assertIn("surface_quality", changed)

    def test_capabilities(self):
        caps = devices.for_product(0x2338)
        self.assertEqual(caps.display_name, "ER21Pro")
        self.assertEqual(caps.polling_rates, [125, 250, 500, 1000])
        self.assertEqual(caps.cpi_range, (50, 30000))
        self.assertEqual(caps.cpi_step, 50)
        self.assertIn("Gaming+", caps.power_modes)
        self.assertEqual(caps.lod_label(2), "Medium (2)")

    def test_unknown_product_falls_back(self):
        caps = devices.for_product(0x9999)
        self.assertIn(1000, caps.polling_rates)
        self.assertFalse(caps.mouse)

    def test_partial_hid_writes_are_completed(self):
        dev = RawmDevice("/dev/null")
        dev.fd = 99
        written = []

        def short_write(_fd, view):
            chunk = bytes(view[:7])
            written.append(chunk)
            return len(chunk)

        with patch("rawm_control.protocol.os.write", side_effect=short_write):
            dev.write_frame(b"\x00" * 80)

        # 80 bytes + report headers become two 64-byte reports.
        self.assertEqual(sum(len(x) for x in written), 128)
        self.assertGreater(len(written), 2)

    def test_malformed_query_replies_are_protocol_errors(self):
        for doc in ([], {"cpi_l": ["bad"]}, {"kd": ["bad"]}, {"gm": []}, {"cpi_l": "bad"}):
            with self.subTest(doc=doc):
                with self.assertRaises(ProtocolError):
                    state_from_query(doc)


if __name__ == "__main__":
    unittest.main()
