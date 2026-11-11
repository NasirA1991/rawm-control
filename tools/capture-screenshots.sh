#!/usr/bin/env bash
# Regenerate the four main-window screenshots from demo mode.
#
# Requirements: Python 3 with the project dependencies, Xvfb, dbus-run-session,
# ImageMagick (import + magick/convert). Run from anywhere:
#
#   tools/capture-screenshots.sh [OUTPUT_DIR]
#
# The default output is docs/screenshots. The demo window is positioned at
# 0,0 in a bare Xvfb session and cropped to the documented 980x760 size.

set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
out_dir=${1:-"$root/docs/screenshots"}
pages=(device performance dpi lighting)

for command in xvfb-run dbus-run-session import; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "missing required command: $command" >&2
    exit 1
  fi
done
if command -v magick >/dev/null 2>&1; then
  image_tool=magick
elif command -v convert >/dev/null 2>&1; then
  image_tool=convert
else
  echo "missing ImageMagick (magick or convert)" >&2
  exit 1
fi

mkdir -p "$out_dir"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

cd "$root"
for page in "${pages[@]}"; do
  raw="$tmp/$page.png"
  dest="$out_dir/$page.png"
  echo "capturing $page"
  if ! timeout 30 xvfb-run -a -s "-screen 0 1200x900x24" bash -c '
    set -e
    page=$1
    raw=$2
    log=$3
    dbus-run-session -- bash -c "
      GDK_BACKEND=x11 python3 -m rawm_control --demo --no-tray --page \"$page\" >\"$log\" 2>&1 &
      app_pid=\$!
      trap \"kill \$app_pid 2>/dev/null || true\" EXIT
      sleep 5
      import -window root \"$raw\"
      kill \$app_pid 2>/dev/null || true
      wait \$app_pid 2>/dev/null || true
    "
  ' _ "$page" "$raw" "$tmp/$page.log" 2>"$tmp/$page.err"; then
    cat "$tmp/$page.err" >&2
    exit 1
  fi
  "$image_tool" "$raw" -crop 980x760+0+0 +repage "$dest"
  dimensions=$("$image_tool" identify -format "%wx%h" "$dest")
  if [[ "$dimensions" != "980x760" ]]; then
    echo "unexpected screenshot size for $page: $dimensions" >&2
    exit 1
  fi
done

echo "wrote ${#pages[@]} screenshots to $out_dir"
