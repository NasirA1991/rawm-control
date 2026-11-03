#!/usr/bin/env bash
# Render the AUR -git PKGBUILD locally for a first-time AUR submission.
#
#   ./scripts/render-pkgbuild.sh [owner/repo] [output-dir]
#
# Defaults: origin remote's GitHub path, ./aur-build
set -euo pipefail
repo="${1:-}"
if [[ -z "$repo" ]]; then
    repo=$(git remote get-url origin 2>/dev/null | sed -E 's#.*github\.com[:/]##; s#\.git$##' || true)
fi
if [[ -z "$repo" ]]; then
    echo "usage: $0 <owner/repo> [output-dir]" >&2
    exit 2
fi
out="${2:-$PWD/aur-build}"
mkdir -p "$out/rawm-control-git"
sed "s|@REPO@|${repo}|g" packaging/aur/rawm-control-git/PKGBUILD.in > "$out/rawm-control-git/PKGBUILD"
(
    cd "$out/rawm-control-git"
    makepkg --printsrcinfo > .SRCINFO
)
echo "Rendered $out/rawm-control-git/{PKGBUILD,.SRCINFO} for ${repo}"
echo "Submit that directory at https://aur.archlinux.org/submit/"
