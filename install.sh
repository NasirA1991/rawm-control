#!/usr/bin/env bash
# Install RAWM Control.
#
#   sudo ./install.sh          # system-wide (/usr), installs the udev rule
#   ./install.sh --user        # per-user (~/.local), no root
#
# Packaging: DESTDIR=/tmp/pkg PREFIX=/usr ./install.sh
set -euo pipefail

PREFIX="${PREFIX:-/usr}"
DESTDIR="${DESTDIR:-}"
USER_INSTALL=0
for arg in "$@"; do
    case "$arg" in
        --user) USER_INSTALL=1 ;;
        -h|--help)
            sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

if [[ $USER_INSTALL -eq 1 ]]; then
    PREFIX="${HOME}/.local"
    echo "Installing to ${PREFIX} (user)"
fi

LIBDIR="${DESTDIR}${PREFIX}/lib/rawm-control"
BINDIR="${DESTDIR}${PREFIX}/bin"
APPDIR="${DESTDIR}${PREFIX}/share/applications"
ICONDIR="${DESTDIR}${PREFIX}/share/icons/hicolor"
METADIR="${DESTDIR}${PREFIX}/share/metainfo"
UDEVDIR="${DESTDIR}${PREFIX}/lib/udev/rules.d"

install -d "$LIBDIR" "$BINDIR" "$APPDIR" "$ICONDIR/scalable/apps" "$ICONDIR/scalable/actions" "$METADIR"
rm -rf "$LIBDIR/rawm_control" "$LIBDIR/data"
cp -r rawm_control "$LIBDIR/rawm_control"
cp -r data "$LIBDIR/data"
find "$LIBDIR" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$LIBDIR" -name '*.pyc' -delete
# sudo commonly resets umask to 077, which makes cp produce root-only files.
find "$LIBDIR" -type d -exec chmod 0755 {} +
find "$LIBDIR" -type f -exec chmod 0644 {} +

cat > "$BINDIR/rawm-control" <<LAUNCHER
#!/usr/bin/env python3
import sys
sys.path.insert(0, "${PREFIX}/lib/rawm-control")
from rawm_control.app import main
sys.exit(main())
LAUNCHER
chmod 0755 "$BINDIR/rawm-control"
ln -sf rawm-control "$BINDIR/rawmctl" 2>/dev/null || cp "$BINDIR/rawm-control" "$BINDIR/rawmctl"

install -m0644 data/icons/hicolor/scalable/apps/rawm-control.svg "$ICONDIR/scalable/apps/"
install -d "$ICONDIR/256x256/apps"
install -m0644 data/icons/rawm-control-256.png "$ICONDIR/256x256/apps/rawm-control.png"
install -m0644 data/icons/hicolor/scalable/actions/*.svg "$ICONDIR/scalable/actions/"
install -m0644 data/io.github.rawmcontrol.RawmControl.desktop "$APPDIR/"
install -m0644 data/io.github.rawmcontrol.RawmControl.metainfo.xml "$METADIR/"

if [[ $USER_INSTALL -eq 0 ]]; then
    install -d "$UDEVDIR"
    install -m0644 data/udev/71-rawm-hid.rules "$UDEVDIR/"
fi

if [[ -z "$DESTDIR" ]]; then
    command -v update-desktop-database >/dev/null && update-desktop-database "$APPDIR" || true
    command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$ICONDIR" 2>/dev/null || true
    if [[ $USER_INSTALL -eq 0 && $EUID -eq 0 ]]; then
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
    echo "NOTE: the udev rule was not installed (needs root)."
    echo "If the app reports 'permission denied', run:"
    echo "  sudo install -m644 data/udev/71-rawm-hid.rules /usr/lib/udev/rules.d/"
    echo "  sudo udevadm control --reload-rules && sudo udevadm trigger"
fi
