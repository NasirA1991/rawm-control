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
install -Dm644 data/icons/hicolor/scalable/apps/rawm-control.svg AppDir/rawm-control.svg
install -Dm644 data/io.github.rawmcontrol.RawmControl.desktop AppDir/rawm-control.desktop
install -Dm644 data/io.github.rawmcontrol.RawmControl.metainfo.xml AppDir/usr/share/metainfo/io.github.rawmcontrol.RawmControl.metainfo.xml
chmod -R a+rX AppDir

tool="${APPIMAGETOOL:-/tmp/appimagetool-x86_64.AppImage}"
if [[ ! -x "$tool" ]]; then
    curl -fsSL "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage" -o "$tool"
    chmod +x "$tool"
fi

ARCH=x86_64 "$tool" --appimage-extract-and-run "AppDir" "$out/rawm-control-${version}-x86_64.AppImage"
echo "built $out/rawm-control-${version}-x86_64.AppImage"
