#!/usr/bin/env bash
# Bump the version in config.py, pyproject.toml and the AppStream release entry.
#   ./scripts/bump-version.sh 0.2.0
set -euo pipefail
version="${1:?usage: $0 X.Y.Z}"
date_str="${2:-$(date +%F)}"
python3 - "$version" "$date_str" <<'PY'
import re
import sys
from pathlib import Path

version, date_str = sys.argv[1], sys.argv[2]

p = Path("rawm_control/config.py")
s = p.read_text()
s, n = re.subn(r'^VERSION = "[^"]+"', f'VERSION = "{version}"', s, flags=re.M)
assert n == 1, "VERSION line not found"
p.write_text(s)

p = Path("pyproject.toml")
s = p.read_text()
s, n = re.subn(r'^version = "[^"]+"', f'version = "{version}"', s, flags=re.M)
assert n == 1, "project version not found"
p.write_text(s)

# Sync the static base version shown on the AUR page.  The -git package's real
# installed version still comes from pkgver() (base.rN.gHASH).
for pkgbuild in ("PKGBUILD", "packaging/aur/rawm-control-git/PKGBUILD.in"):
    p = Path(pkgbuild)
    s = p.read_text()
    s, n = re.subn(r'^pkgver=.*$', f'pkgver={version}', s, flags=re.M)
    assert n == 1, f"pkgver not found in {pkgbuild}"
    p.write_text(s)

p = Path("data/io.github.rawmcontrol.RawmControl.metainfo.xml")
s = p.read_text()
entry = f'    <release version="{version}" date="{date_str}"/>\n'
s, n = re.subn(r'(<releases>\n)', r'\1' + entry.replace("\\", "\\\\"), s, count=1)
assert n == 1, "releases block not found"
p.write_text(s)
print(f"bumped to {version} ({date_str})")
PY
