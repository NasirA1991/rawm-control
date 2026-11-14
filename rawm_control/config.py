"""Small JSON preferences store + autostart helper."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

APP_ID = "io.github.rawmcontrol.RawmControl"
APP_NAME = "RAWM Control"
VERSION = "0.1.15"


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


def _sanitize(data: dict) -> dict:
    """Return a complete, correctly typed preference dictionary."""
    clean = dict(DEFAULTS)
    if not isinstance(data, dict):
        return clean
    for key in (
        "start_hidden",
        "low_battery_notifications",
        "tray_percent",
        "close_hint_shown",
    ):
        value = data.get(key, DEFAULTS[key])
        if isinstance(value, bool):
            clean[key] = value
    style = data.get("tray_icon_style")
    if not isinstance(style, str) or style not in dict(TRAY_STYLES):
        style = "ring" if clean["tray_percent"] else "mouse"
    clean["tray_icon_style"] = style
    category = data.get("tray_category")
    if not isinstance(category, str) or category not in dict(TRAY_CATEGORIES):
        category = DEFAULT_TRAY_CATEGORY
    clean["tray_category"] = category
    return clean


def load() -> dict:
    path = config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return dict(DEFAULTS)
    except (OSError, ValueError) as exc:
        logger.warning("Could not read preferences from %s: %s", path, exc)
        return dict(DEFAULTS)
    if not isinstance(raw, dict):
        logger.warning("Ignoring preferences in %s: expected a JSON object", path)
        return dict(DEFAULTS)
    return _sanitize(raw)


def save(data: dict) -> None:
    path = config_path()
    payload = _sanitize(data)
    tmp_name: str | None = None
    try:
        config_dir().mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, indent=2) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
        tmp_name = None
    except OSError as exc:
        logger.warning("Could not save preferences to %s: %s", path, exc)
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


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
