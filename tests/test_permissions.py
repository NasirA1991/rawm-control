"""Discovery filtering, permission state and installer-script regressions."""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from rawm_control import devices, protocol
from rawm_control.worker import DeviceWorker, LinkStatus


class DiscoveryTests(unittest.TestCase):
    def _discover(self, uevents, descriptors):
        def fake_open(path, *_args, **_kwargs):
            path = str(path)
            for suffix, data in descriptors.items():
                if path.endswith(suffix):
                    return io.BytesIO(data)
            raise OSError(path)

        with patch.object(protocol.os, "listdir", return_value=list(uevents)), \
             patch.object(protocol, "_read_uevent", side_effect=lambda p: uevents[os.path.basename(p)]), \
             patch("builtins.open", side_effect=fake_open):
            return protocol.discover()

    def test_discovery_requires_known_vendor_and_product(self):
        uevents = {
            "hidraw0": {"HID_ID": "0003:00001915:00002338"},
            "hidraw1": {"HID_ID": "0003:00001234:00002338"},
            "hidraw2": {"HID_ID": "0003:00001915:00009999"},
            "hidraw3": {"HID_ID": "0003:00001915:00002328"},
        }
        descriptors = {
            "hidraw0/device/report_descriptor": b"\x06\x00\xff",
            "hidraw1/device/report_descriptor": b"\x06\x00\xff",
            "hidraw2/device/report_descriptor": b"\x06\x00\xff",
            "hidraw3/device/report_descriptor": b"\x06\x00\x01",
        }
        found = self._discover(uevents, descriptors)
        self.assertEqual([d.product_id for d in found], [0x2338])
        self.assertEqual(found[0].path, "/dev/hidraw0")

    def test_unknown_1915_product_is_not_treated_as_a_mouse(self):
        found = self._discover(
            {"hidraw0": {"HID_ID": "0003:00001915:00009999"}},
            {"hidraw0/device/report_descriptor": b"\x06\x00\xff"},
        )
        self.assertEqual(found, [])


class PermissionStateTests(unittest.TestCase):
    def test_permission_denied_is_distinct_from_no_device(self):
        statuses = []
        worker = DeviceWorker(
            lambda _state, _changed: None,
            lambda _connected, _error: statuses.append(worker.link_status),
            refresh_seconds=3600,
        )
        with patch.object(worker, "_pick_device", return_value=None):
            self.assertFalse(worker._connect())
        self.assertEqual(worker.link_status, LinkStatus.NO_DEVICE)

        info = protocol.HidrawDevice(path="/dev/hidraw-test", name="test", product_id=0x2338)
        denied = Mock()
        denied.open.side_effect = protocol.PermissionDenied("permission denied")
        with patch.object(worker, "_pick_device", return_value=info), \
             patch("rawm_control.worker.RawmDevice", return_value=denied):
            self.assertFalse(worker._connect())
        self.assertEqual(worker.link_status, LinkStatus.PERMISSION_DENIED)
        self.assertEqual(statuses[-1], LinkStatus.PERMISSION_DENIED)

    def test_flatpak_detection(self):
        with patch("rawm_control.devices.os.path.exists", return_value=True):
            self.assertTrue(devices.is_flatpak())
        with patch("rawm_control.devices.os.path.exists", return_value=False):
            self.assertFalse(devices.is_flatpak())

    def test_copy_command_uses_rule_path_not_embedded_rule_text(self):
        command = devices.udev_copy_command("/tmp/a rule.rules")
        self.assertIn("'/tmp/a rule.rules'", command)
        self.assertIn("/etc/udev/rules.d/71-rawm-hid.rules", command)
        self.assertNotIn("ATTRS{idProduct}", command)


class InstallerScriptTests(unittest.TestCase):
    root = Path(__file__).resolve().parent.parent

    def run_script(self, *args, env=None):
        return subprocess.run(
            [str(self.root / "install.sh"), *args],
            capture_output=True,
            text=True,
            env={**os.environ, **(env or {})},
            timeout=30,
        )

    def test_system_install_refuses_non_root(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "System install needs root: sudo ./install.sh (or ./install.sh --user)",
            result.stderr,
        )

    def test_help_lists_every_install_mode(self):
        result = self.run_script("--help")
        self.assertEqual(result.returncode, 0)
        for flag in ("--user", "--udev-only", "--skip-deps", "DESTDIR"):
            self.assertIn(flag, result.stdout)

    def test_udev_only_rejects_user_mode(self):
        result = self.run_script("--udev-only", "--user")
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot be combined", result.stderr)

    def test_udev_only_refuses_non_root(self):
        result = self.run_script("--udev-only")
        self.assertEqual(result.returncode, 1)
        self.assertIn("sudo ./install.sh --udev-only", result.stderr)

    def test_destdir_staging_skips_dependencies_and_installs_binaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_script(env={"DESTDIR": tmp, "PREFIX": "/usr"})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(Path(tmp, "usr/bin/rawm-control").is_file())
            self.assertTrue(Path(tmp, "usr/bin/rawmctl").is_file())
            self.assertTrue(Path(tmp, "usr/lib/udev/rules.d/71-rawm-hid.rules").is_file())

    def test_user_install_and_custom_prefix_uninstall(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"HOME": tmp}
            result = self.run_script("--user", "--skip-deps", env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("sudo ./install.sh --udev-only", result.stdout)
            installed = Path(tmp, ".local/bin/rawm-control")
            self.assertTrue(installed.is_file())
            result = subprocess.run(
                [str(self.root / "uninstall.sh"), "--user"],
                capture_output=True,
                text=True,
                env={**os.environ, **env},
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(installed.exists())

    def test_uninstall_help(self):
        result = subprocess.run(
            [str(self.root / "uninstall.sh"), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--user", result.stdout)
        self.assertIn("PREFIX", result.stdout)

    def test_custom_prefix_uninstall_removes_installed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp, "opt/rawm")
            for rel in (
                "lib/rawm-control/rawm_control/__init__.py",
                "bin/rawm-control",
                "bin/rawmctl",
                "share/applications/io.github.rawmcontrol.RawmControl.desktop",
                "share/metainfo/io.github.rawmcontrol.RawmControl.metainfo.xml",
                "share/icons/hicolor/scalable/apps/rawm-control.svg",
                "lib/udev/rules.d/71-rawm-hid.rules",
            ):
                target = prefix / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("x")
            result = subprocess.run(
                [str(self.root / "uninstall.sh")],
                capture_output=True,
                text=True,
                env={**os.environ, "PREFIX": str(prefix)},
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(Path(prefix, "bin/rawm-control").exists())
            self.assertFalse(Path(prefix, "lib/rawm-control").exists())
            self.assertFalse(Path(prefix, "lib/udev/rules.d/71-rawm-hid.rules").exists())


if __name__ == "__main__":
    unittest.main()
