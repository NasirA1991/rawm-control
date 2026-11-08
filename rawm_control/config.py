"""Small JSON preferences store + autostart helper."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

APP_ID = "io.github.rawmcontrol.RawmControl"
APP_NAME = "RAWM Control"
VERSION = "0.1.13"


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "rawm-control"


def config_path() -> Path:
    return config_dir() / "config.json"


TRAY_STYLES = [
    ("ring", "Ring + mouse"),
    ("number", "Number only"),
    ("battery", "Battery + number"),
    ("sidecar", "Mouse + number"),
    ("mouse", "Mouse only"),
]
DEFAULT_TRAY_STYLE = "ring"

# SNI category hints. Plasma groups ApplicationStatus on the left side of the
# third-party tray entries and Hardware with the system hardware icons.
TRAY_CATEGORIES = [
    ("ApplicationStatus", "Application status (left group)"),
    ("Hardware", "Hardware"),
]
DEFAULT_TRAY_CATEGORY = "ApplicationStatus"

DEFAULTS = {
    "start_hidden": False,
    "low_battery_notifications": True,
    "tray_percent": True,
    "tray_icon_style": DEFAULT_TRAY_STYLE,
    "tray_category": DEFAULT_TRAY_CATEGORY,
    "close_hint_shown": False,
}


def load() -> dict:
    data = dict(DEFAULTS)
    path = config_path()
    try:
        data.update(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        logger.warning("Could not read preferences from %s: %s", path, exc)
    return data


def save(data: dict) -> None:
    path = config_path()
    try:
        config_dir().mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not save preferences to %s: %s", path, exc)


def mark_close_hint_shown() -> bool:
    data = load()
    data["close_hint_shown"] = True
    save(data)
    return True


def reset() -> bool:
    """Remove only local app preferences; leaves autostart and the mouse alone."""
    try:
        config_path().unlink()
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def autostart_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "autostart" / "rawm-control.desktop"


AUTOSTART_CONTENT = """[Desktop Entry]
Type=Application
Name=RAWM Control
Comment=Configure RAWM mice and show battery in the tray
Exec=rawm-control --tray
Icon=rawm-control
Terminal=false
Categories=Settings;HardwareSettings;
X-GNOME-Autostart-enabled=true
"""


def is_autostart_enabled() -> bool:
    return autostart_path().exists()


def set_autostart(enabled: bool) -> bool:
    path = autostart_path()
    try:
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(AUTOSTART_CONTENT, encoding="utf-8")
        elif path.exists():
            path.unlink()
        return True
    except OSError:
        return False
