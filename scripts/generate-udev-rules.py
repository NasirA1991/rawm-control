#!/usr/bin/env python3
"""Regenerate data/udev/71-rawm-hid.rules from the capability database."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rawm_control import devices  # noqa: E402


def main() -> int:
    target = ROOT / "data" / "udev" / "71-rawm-hid.rules"
    target.write_text(devices.udev_rule_text(), encoding="utf-8")
    print(f"Wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
