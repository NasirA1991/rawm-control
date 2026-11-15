#!/usr/bin/env bash
# Install RAWM Control.
#
#   sudo ./install.sh          # system-wide (/usr), installs the udev rule
#   ./install.sh --user        # per-user (~/.local), no root
#   sudo ./install.sh --udev-only  # install only the udev rule
#
# Packaging: DESTDIR=/tmp/pkg PREFIX=/usr ./install.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${PREFIX:-/usr}"
DESTDIR="${DESTDIR:-}"
USER_INSTALL=0
UDEV_ONLY=0
SKIP_DEPS=0

usage() {
    cat <<'EOF'
Install RAWM Control from this checkout.

Usage:
  sudo ./install.sh                 System install under /usr (installs udev rule)
  ./install.sh --user               Per-user install under ~/.local
  sudo ./install.sh --udev-only     Install only /etc/udev/rules.d/71-rawm-hid.rules
  DESTDIR=/tmp/pkg PREFIX=/usr ./install.sh
                                    Stage an install for packaging

Options:
  --user        Install under ~/.local without root; does not install a udev rule.
  --udev-only   Install only the udev rule in /etc and reload udev. Needs root.
  --skip-deps   Skip the Python/GTK dependency check.
  -h, --help    Show this help.

Environment:
  PREFIX        Install prefix (default: /usr).
  DESTDIR       Staging root for packages; skips root, dependency and udev steps.
EOF
}

while (($#)); do
    case "$1" in
        --user) USER_INSTALL=1 ;;
        --udev-only) UDEV_ONLY=1 ;;
        --skip-deps) SKIP_DEPS=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; echo "Try --help." >&2; exit 2 ;;
    esac
    shift
done

if [[ $UDEV_ONLY -eq 1 ]]; then
    if [[ $USER_INSTALL -eq 1 ]]; then
        echo "--udev-only cannot be combined with --user." >&2
        exit 2
    fi
    if [[ -n "$DESTDIR" ]]; then
        echo "--udev-only does not support DESTDIR." >&2
        exit 2
    fi
    if [[ ${EUID} -ne 0 ]]; then
        echo "Run with sudo: sudo ./install.sh --udev-only" >&2
        exit 1
    fi
    RULE="$ROOT/data/udev/71-rawm-hid.rules"
    if [[ ! -f "$RULE" ]]; then
        echo "Missing $RULE" >&2
        exit 1
    fi
    install -Dm644 "$RULE" /etc/udev/rules.d/71-rawm-hid.rules
    udevadm control --reload-rules
    udevadm trigger --subsystem-match=hidraw
    echo "Replug the mouse or receiver."
    exit 0
fi

if [[ $USER_INSTALL -eq 1 ]]; then
    if [[ ${EUID} -eq 0 ]]; then
        echo "Run --user without sudo." >&2
        exit 1
    fi
    PREFIX="${HOME}/.local"
    echo "Installing to ${PREFIX} (user)"
elif [[ -z "$DESTDIR" && ${EUID} -ne 0 ]]; then
    echo "System install needs root: sudo ./install.sh (or ./install.sh --user)" >&2
    exit 1
fi

dependency_hint() {
    local id=""
    local like=""
    if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        id="${ID:-}"
        like="${ID_LIKE:-}"
    fi
    case " ${id} ${like} " in
        *arch*)
            echo "sudo pacman -S --needed python python-gobject gtk4 libadwaita python-cairo python-dbus hicolor-icon-theme"
            ;;
        *debian*|*ubuntu*)
            echo "sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-cairo python3-dbus hicolor-icon-theme"
            ;;
        *fedora*)
            echo "sudo dnf install python3 python3-gobject gtk4 libadwaita python3-cairo python3-dbus hicolor-icon-theme"
            ;;
        *opensuse*|*suse*)
            echo "sudo zypper install python3 python3-gobject gtk4 libadwaita-1-0 python3-cairo python3-dbus-python hicolor-icon-theme"
            ;;
        *)
            echo "python3 (>=3.10), GTK4, libadwaita, PyGObject, pycairo, dbus-python and hicolor-icon-theme"
            ;;
    esac
}

check_dependencies() {
    if [[ $SKIP_DEPS -eq 1 || -n "$DESTDIR" ]]; then
        return 0
    fi
    if ! command -v python3 >/dev/null 2>&1; then
        echo "Python 3.10+ is required." >&2
        echo "Install: $(dependency_hint)" >&2
        exit 1
    fi
    if ! python3 - <<'PY'
import sys

if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 or newer is required")

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: F401,E402

import cairo  # noqa: F401
import dbus  # noqa: F401
PY
    then
        echo "Missing Python or GTK dependencies." >&2
        echo "Install: $(dependency_hint)" >&2
        exit 1
    fi
}

check_dependencies

LIBDIR="${DESTDIR}${PREFIX}/lib/rawm-control"
BINDIR="${DESTDIR}${PREFIX}/bin"
APPDIR="${DESTDIR}${PREFIX}/share/applications"
ICONDIR="${DESTDIR}${PREFIX}/share/icons/hicolor"
METADIR="${DESTDIR}${PREFIX}/share/metainfo"
UDEVDIR="${DESTDIR}${PREFIX}/lib/udev/rules.d"

install -d "$LIBDIR" "$BINDIR" "$APPDIR" "$ICONDIR/scalable/apps" \
    "$ICONDIR/scalable/actions" "$ICONDIR/256x256/apps" "$METADIR"
rm -rf "$LIBDIR/rawm_control" "$LIBDIR/data"
cp -r "$ROOT/rawm_control" "$LIBDIR/rawm_control"
cp -r "$ROOT/data" "$LIBDIR/data"
find "$LIBDIR" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$LIBDIR" -name '*.pyc' -delete
# sudo commonly resets umask to 077, which makes cp produce root-only files.
find "$LIBDIR" -type d -exec chmod 0755 {} +
find "$LIBDIR" -type f -exec chmod 0644 {} +

cat > "$BINDIR/rawm-control" <<LAUNCHER
#!/usr/bin/env python3
import sys
sys.path.insert(0, "${PREFIX}/lib/rawm-control")
from rawm_control.__main__ import main
sys.exit(main())
LAUNCHER
chmod 0755 "$BINDIR/rawm-control"
cat > "$BINDIR/rawmctl" <<LAUNCHER
#!/usr/bin/env python3
import sys
sys.path.insert(0, "${PREFIX}/lib/rawm-control")
from rawm_control.cli import main
sys.exit(main())
LAUNCHER
chmod 0755 "$BINDIR/rawmctl"

install -m0644 "$ROOT/data/icons/hicolor/scalable/apps/rawm-control.svg" "$ICONDIR/scalable/apps/"
install -m0644 "$ROOT/data/icons/rawm-control-256.png" "$ICONDIR/256x256/apps/rawm-control.png"
install -m0644 "$ROOT"/data/icons/hicolor/scalable/actions/*.svg "$ICONDIR/scalable/actions/"
install -m0644 "$ROOT/data/io.github.rawmcontrol.RawmControl.desktop" "$APPDIR/"
install -m0644 "$ROOT/data/io.github.rawmcontrol.RawmControl.metainfo.xml" "$METADIR/"

if [[ $USER_INSTALL -eq 0 ]]; then
    install -d "$UDEVDIR"
    install -m0644 "$ROOT/data/udev/71-rawm-hid.rules" "$UDEVDIR/"
fi

if [[ -z "$DESTDIR" ]]; then
    if command -v update-desktop-database >/dev/null; then
        update-desktop-database "$APPDIR" >/dev/null 2>&1 || true
    fi
    if command -v gtk-update-icon-cache >/dev/null; then
        gtk-update-icon-cache -q -t "$ICONDIR" >/dev/null 2>&1 || true
    fi
    if [[ $USER_INSTALL -eq 0 && ${EUID} -eq 0 ]]; then
        udevadm control --reload-rules 2>/dev/null || true
        udevadm trigger --subsystem-match=hidraw 2>/dev/null || true
    fi
fi

echo
echo "RAWM Control installed."
echo "  run:      rawm-control"
echo "  tray:     rawm-control --tray"
echo "  CLI:      rawmctl status"
if [[ $USER_INSTALL -eq 1 ]]; then
    echo
    echo "One-time permission step: sudo ./install.sh --udev-only"
fi
