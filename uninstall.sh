#!/usr/bin/env bash
# Remove a manual/system-wide RAWM Control install.
#   sudo ./uninstall.sh
# User settings in ~/.config/rawm-control are kept.
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "Run with sudo: sudo ./uninstall.sh" >&2
    exit 1
fi

PREFIX="${PREFIX:-/usr}"
LIBDIR="$PREFIX/lib/rawm-control"
BINDIR="$PREFIX/bin"
APPDIR="$PREFIX/share/applications"
METADIR="$PREFIX/share/metainfo"
ICONDIR="$PREFIX/share/icons/hicolor"
UDEVDIR="$PREFIX/lib/udev/rules.d"

rm -rf "$LIBDIR"
rm -f "$BINDIR/rawm-control" "$BINDIR/rawmctl"
rm -f "$APPDIR/io.github.rawmcontrol.RawmControl.desktop"
rm -f "$METADIR/io.github.rawmcontrol.RawmControl.metainfo.xml"
rm -f "$ICONDIR/scalable/apps/rawm-control.svg"
rm -f "$ICONDIR"/scalable/actions/rawm-*-symbolic.svg
rm -f "$ICONDIR/256x256/apps/rawm-control.png"
rm -f "$UDEVDIR/71-rawm-hid.rules"

# Files from an optional per-user install.
if [[ -n "${SUDO_USER:-}" ]]; then
    HOME_DIR="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
    rm -rf "$HOME_DIR/.local/lib/rawm-control"
    rm -f "$HOME_DIR/.local/bin/rawm-control" "$HOME_DIR/.local/bin/rawmctl"
    rm -f "$HOME_DIR/.local/share/applications/io.github.rawmcontrol.RawmControl.desktop"
    rm -f "$HOME_DIR/.local/share/metainfo/io.github.rawmcontrol.RawmControl.metainfo.xml"
    rm -f "$HOME_DIR/.local/share/icons/hicolor/scalable/apps/rawm-control.svg"
    rm -f "$HOME_DIR/.local/share/icons/hicolor/256x256/apps/rawm-control.png"
fi

command -v update-desktop-database >/dev/null && update-desktop-database "$APPDIR" >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$ICONDIR" >/dev/null 2>&1 || true
if command -v udevadm >/dev/null; then
    udevadm control --reload-rules >/dev/null 2>&1 || true
    udevadm trigger --subsystem-match=hidraw >/dev/null 2>&1 || true
fi

echo "RAWM Control manual install removed."
echo "Kept user settings in ~/.config/rawm-control."
echo "Refresh the KDE menu with: kbuildsycoca6 --noincremental"
