#!/usr/bin/env bash
# Build a lean AppImage: app code only, host provides GTK4/PyGObject.
#   ./packaging/appimage/build.sh VERSION [OUTDIR]
set -euo pipefail

version="${1:?usage: build.sh <version> [output-dir]}"
out="${2:-dist}"
root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"
mkdir -p "$out"

rm -rf AppDir
mkdir -p AppDir/usr/share/rawm-control
cp -r rawm_control data AppDir/usr/share/rawm-control/
find AppDir/usr/share/rawm-control -name '__pycache__' -type d -prune -exec rm -rf {} +
install -Dm755 packaging/appimage/AppRun AppDir/AppRun
install -Dm644 packaging/appimage/launcher.py AppDir/usr/share/rawm-control/launcher.py
install -Dm644 data/icons/rawm-control-256.png AppDir/rawm-control.png
install -Dm644 data/icons/hicolor/scalable/apps/rawm-control.svg AppDir/rawm-control.svg
install -Dm644 data/io.github.rawmcontrol.RawmControl.desktop AppDir/rawm-control.desktop
install -Dm644 data/io.github.rawmcontrol.RawmControl.desktop AppDir/usr/share/applications/rawm-control.desktop
install -Dm644 data/io.github.rawmcontrol.RawmControl.metainfo.xml AppDir/usr/share/metainfo/io.github.rawmcontrol.RawmControl.metainfo.xml
chmod -R a+rX AppDir

tool="${APPIMAGETOOL:-/tmp/appimagetool-1.9.1-x86_64.AppImage}"
if [[ -z "${APPIMAGETOOL:-}" ]]; then
    # Pinned release + checksum: never execute a floating "continuous" build.
    tool_version="1.9.1"
    sha256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
    if [[ ! -x "$tool" ]] || ! printf '%s  %s\n' "$sha256" "$tool" | sha256sum -c - >/dev/null 2>&1; then
        curl -fsSL "https://github.com/AppImage/appimagetool/releases/download/${tool_version}/appimagetool-x86_64.AppImage" -o "$tool"
        chmod +x "$tool"
    fi
    printf '%s  %s\n' "$sha256" "$tool" | sha256sum -c -
fi

ARCH=x86_64 "$tool" --appimage-extract-and-run "AppDir" "$out/rawm-control-${version}-x86_64.AppImage"
echo "built $out/rawm-control-${version}-x86_64.AppImage"
