"""Keep release-visible version strings in sync."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from rawm_control import config

ROOT = Path(__file__).resolve().parent.parent


class VersionConsistencyTest(unittest.TestCase):
    def test_every_version_source_matches(self):
        version = config.VERSION
        pyproject = (ROOT / "pyproject.toml").read_text()
        match = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), version)

        metainfo = (ROOT / "data/io.github.rawmcontrol.RawmControl.metainfo.xml").read_text()
        releases = re.findall(r'<release version="([^"]+)"', metainfo)
        self.assertEqual(releases[0], version)

        for path in (
            ROOT / "PKGBUILD",
            ROOT / "packaging/aur/rawm-control-git/PKGBUILD.in",
        ):
            text = path.read_text()
            match = re.search(r"^pkgver=(.+)$", text, re.MULTILINE)
            self.assertIsNotNone(match, path)
            self.assertEqual(match.group(1).strip(), version, path)


if __name__ == "__main__":
    unittest.main()
