#!/usr/bin/env bash
# Remove a manual RAWM Control install.
#
#   sudo ./uninstall.sh          # system-wide (/usr)
#   ./uninstall.sh --user        # per-user (~/.local)
#   PREFIX=/opt/rawm ./uninstall.sh
#                                # custom prefix
#
# User settings in ~/.config/rawm-control are kept.
set -euo pipefail

USER_MODE=0
while (($#)); do
    case "$1" in
        --user) USER_MODE=1 ;;
        -h|--help)
            cat <<'EOF'
Remove a manual RAWM Control install.

Usage:
  sudo ./uninstall.sh          Remove a /usr system install and its udev rules
  ./uninstall.sh --user        Remove a ~/.local user install
  PREFIX=/opt/rawm ./uninstall.sh
                               Remove a custom-prefix install

Options:
  --user    Remove the per-user install under ~/.local.
  -h, --help
            Show this help.

Environment:
  PREFIX    Install prefix (default: /usr for system installs).

Missing files are ignored. User settings in ~/.config/rawm-control are kept.
EOF
            exit 0
            ;;
        *) echo "Unknown option: $1" >&2; echo "Try --help." >&2; exit 2 ;;
    esac
    shift
done

if [[ $USER_MODE -eq 1 ]]; then
    if [[ ${EUID} -eq 0 ]]; then
        echo "Run --user without sudo." >&2
        exit 1
    fi
    PREFIX="${HOME}/.local"
else
    PREFIX="${PREFIX:-/usr}"
    if [[ "$PREFIX" == "/usr" && ${EUID} -ne 0 ]]; then
        echo "Run with sudo, or use ./uninstall.sh --user." >&2
        exit 1
    fi
fi

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

if [[ $USER_MODE -eq 0 && ${EUID} -eq 0 ]]; then
    rm -f /etc/udev/rules.d/71-rawm-hid.rules
fi

# Files from an optional per-user install made alongside a system install.
if [[ $USER_MODE -eq 0 && -n "${SUDO_USER:-}" ]]; then
    HOME_DIR="$(getent passwd "$SUDO_USER" | cut -d: -f6 || true)"
    if [[ -n "$HOME_DIR" ]]; then
        rm -rf "$HOME_DIR/.local/lib/rawm-control"
        rm -f "$HOME_DIR/.local/bin/rawm-control" "$HOME_DIR/.local/bin/rawmctl"
        rm -f "$HOME_DIR/.local/share/applications/io.github.rawmcontrol.RawmControl.desktop"
        rm -f "$HOME_DIR/.local/share/metainfo/io.github.rawmcontrol.RawmControl.metainfo.xml"
        rm -f "$HOME_DIR/.local/share/icons/hicolor/scalable/apps/rawm-control.svg"
        rm -f "$HOME_DIR"/.local/share/icons/hicolor/scalable/actions/rawm-*-symbolic.svg
        rm -f "$HOME_DIR/.local/share/icons/hicolor/256x256/apps/rawm-control.png"
        if command -v update-desktop-database >/dev/null; then
            sudo -u "$SUDO_USER" update-desktop-database \
                "$HOME_DIR/.local/share/applications" >/dev/null 2>&1 || true
        fi
        if command -v gtk-update-icon-cache >/dev/null; then
            sudo -u "$SUDO_USER" gtk-update-icon-cache -q -t \
                "$HOME_DIR/.local/share/icons/hicolor" >/dev/null 2>&1 || true
        fi
    fi
fi

if command -v update-desktop-database >/dev/null; then
    update-desktop-database "$APPDIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null; then
    gtk-update-icon-cache -q -t "$ICONDIR" >/dev/null 2>&1 || true
fi
if [[ $USER_MODE -eq 0 && ${EUID} -eq 0 ]]; then
    if command -v udevadm >/dev/null; then
        udevadm control --reload-rules >/dev/null 2>&1 || true
        udevadm trigger --subsystem-match=hidraw >/dev/null 2>&1 || true
    fi
fi

echo "RAWM Control manual install removed."
echo "Kept user settings in ~/.config/rawm-control."
if [[ $USER_MODE -eq 1 ]]; then
    echo "Refresh the KDE menu with: kbuildsycoca6 --noincremental"
fi
