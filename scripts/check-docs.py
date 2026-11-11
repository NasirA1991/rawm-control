#!/usr/bin/env python3
"""Validate the documentation links, anchors, images and device tables.

This is intentionally dependency-free so it can run in CI and from a checkout
without installing a documentation toolchain. It checks local Markdown only;
external URLs are counted but not fetched.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC_DIR = ROOT / "docs"
DOC_FILES = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", ROOT / "SECURITY.md"]
DOC_FILES += sorted(DOC_DIR.rglob("*.md"))

_NUMBER_WORDS = {
    0: "zero",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
}


def _slug(text: str) -> str:
    """Approximate GitHub's heading anchor algorithm."""
    text = re.sub(r"[`*_~]", "", text).strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return text.replace(" ", "-")


def _headings(path: Path) -> list[str]:
    headings: list[str] = []
    seen: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if not match:
            continue
        base = _slug(match.group(2))
        count = seen.get(base, 0)
        headings.append(base if count == 0 else f"{base}-{count}")
        seen[base] = count + 1
    return headings


def _fenced_lines(path: Path) -> set[int]:
    """Line numbers inside fenced code blocks, including the fences."""
    inside = False
    fenced: set[int] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("```"):
            fenced.add(number)
            inside = not inside
        elif inside:
            fenced.add(number)
    return fenced


def _check_target(path: Path, target: str, errors: list[str]) -> str:
    target = target.strip()
    if target.startswith(("http://", "https://", "mailto:")):
        return "external"
    if target.startswith("#"):
        destination = path
        fragment = target[1:]
    else:
        path_part, _, fragment = target.partition("#")
        destination = (path.parent / path_part).resolve()
        if not destination.exists():
            errors.append(f"{path.relative_to(ROOT)}: missing {target}")
            return "local"
    if fragment:
        if destination.suffix.lower() != ".md":
            errors.append(f"{path.relative_to(ROOT)}: anchor on non-Markdown {target}")
            return "anchor"
        if fragment not in _headings(destination):
            errors.append(f"{path.relative_to(ROOT)}: missing anchor {target}")
        return "anchor"
    return "local"


def _check_links(path: Path, errors: list[str]) -> tuple[int, int, int]:
    text = path.read_text(encoding="utf-8")
    fenced = _fenced_lines(path)
    local = anchors = external = 0
    targets = [
        (match.start(), match.group(1))
        for match in re.finditer(r"!?\[[^\]]*\]\(([^)]+)\)", text)
    ]
    targets += [
        (match.start(), match.group(1))
        for match in re.finditer(r'(?:src|href)="([^"]+)"', text)
    ]
    for start, target in targets:
        if text.count("\n", 0, start) + 1 in fenced:
            continue
        kind = _check_target(path, target, errors)
        if kind == "external":
            external += 1
        elif kind == "anchor":
            anchors += 1
            local += 1
        else:
            local += 1
    return local, anchors, external


def _check_device_tables(errors: list[str]) -> None:
    sys.path.insert(0, str(ROOT))
    from rawm_control import devices

    mouse_ids = {pid for pid, caps in devices._DB.items() if caps.mouse and not caps.receiver and not caps.keyboard}
    receiver_ids = {pid for pid, caps in devices._DB.items() if caps.receiver}
    keyboard_ids = {pid for pid, caps in devices._DB.items() if caps.keyboard}

    path = DOC_DIR / "DEVICES.md"
    text = path.read_text(encoding="utf-8")
    normal = re.sub(r"\s+", " ", text)
    expected = (
        f"contains {len(mouse_ids)} mouse product IDs (collapsed into the 21 model rows below), "
        f"{_NUMBER_WORDS[len(receiver_ids)]} receiver dongles and "
        f"{_NUMBER_WORDS[len(keyboard_ids)]} keyboard products"
    )
    if expected not in normal:
        errors.append(f"docs/DEVICES.md: device-count sentence does not match {expected!r}")

    table_start = text.find("| Model | USB ID |")
    table_end = text.find("\n## Receivers", table_start)
    if table_start < 0 or table_end < 0:
        errors.append("docs/DEVICES.md: mouse table or Receivers section not found")
        return
    table_lines = [
        line for line in text[table_start:table_end].splitlines()
        if line.startswith("|") and not line.startswith("| Model") and not line.startswith("|---")
    ]
    table_ids = {
        int(pid, 16)
        for line in table_lines
        for pid in re.findall(r"([0-9a-f]{4})", line.split("|")[2].replace("1915:", ""))
    }
    if len(table_lines) != 21:
        errors.append(f"docs/DEVICES.md: expected 21 mouse rows, found {len(table_lines)}")
    if table_ids != mouse_ids:
        missing = ", ".join(f"{pid:04x}" for pid in sorted(mouse_ids - table_ids))
        extra = ", ".join(f"{pid:04x}" for pid in sorted(table_ids - mouse_ids))
        errors.append(f"docs/DEVICES.md: mouse ID table differs from devices.json (missing: {missing or 'none'}; extra: {extra or 'none'})")

    receivers_text = text[table_end : text.find("\n## Read-only products", table_end)]
    receiver_doc_ids = {int(pid, 16) for pid in re.findall(r"`([0-9a-fA-F]{4})`", receivers_text)}
    if receiver_doc_ids != receiver_ids:
        errors.append("docs/DEVICES.md: receiver PID list differs from devices.json")

    keyboard_start = text.find("## Read-only products")
    keyboard_end = text.find("\n## Safety", keyboard_start)
    keyboard_text = text[keyboard_start:keyboard_end] if keyboard_start >= 0 and keyboard_end >= 0 else ""
    keyboard_doc_ids = {int(pid, 16) for pid in re.findall(r"1915:([0-9a-fA-F]{4})", keyboard_text)}
    if keyboard_doc_ids != keyboard_ids:
        errors.append("docs/DEVICES.md: keyboard table differs from devices.json")


def main() -> int:
    if not DOC_FILES or not all(path.exists() for path in DOC_FILES):
        print("Documentation files are missing.", file=sys.stderr)
        return 1

    errors: list[str] = []
    local = anchors = external = 0
    for path in DOC_FILES:
        counts = _check_links(path, errors)
        local += counts[0]
        anchors += counts[1]
        external += counts[2]

    _check_device_tables(errors)

    print(f"Checked {len(DOC_FILES)} Markdown files: {local} local links, "
          f"{anchors} anchors, {external} external links.")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"{len(errors)} documentation error(s).", file=sys.stderr)
        return 1
    print("Documentation checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
