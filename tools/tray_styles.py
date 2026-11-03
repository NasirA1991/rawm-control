#!/usr/bin/env python3
"""Render the selectable tray-icon styles at real panel sizes."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cairo
from PIL import Image, ImageDraw, ImageFont

from rawm_control.config import TRAY_STYLES
from rawm_control.protocol import MouseState
from rawm_control.tray import render_tray_icon

DARK = (27, 30, 34)
LIGHT = (239, 241, 245)
SIZES = (32, 22, 16)


def font(size: int):
    for path in (
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def to_pil(pixels, w, h):
    out = bytearray(w * h * 4)
    for y in range(h):
        for x in range(w):
            a, r, g, b = pixels[(y * w + x) * 4 : (y * w + x) * 4 + 4]
            out[(y * w + x) * 4 : (y * w + x) * 4 + 4] = bytes((r, g, b, a))
    return Image.frombytes("RGBA", (w, h), bytes(out))


def icon(state, connected, style, size):
    pix = render_tray_icon(state, connected, style)[0]
    big = to_pil(pix[2], pix[0], pix[1])
    return big.resize((size, size), Image.LANCZOS)


def tile(bg, w, h, r=6):
    img = Image.new("RGBA", (w, h), bg + (255,))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=r, fill=255)
    img.putalpha(mask)
    return img


def main():
    col_w = 250
    width = 24 + col_w * len(TRAY_STYLES)
    height = 430
    sheet = Image.new("RGB", (width, height), (17, 19, 22))
    d = ImageDraw.Draw(sheet)
    d.text((16, 10), "Tray icon styles — real panel sizes, 87% battery", font=font(17), fill=(235, 238, 243))
    d.text((16, 33), "For a ~16 px panel icon, Number only is the most legible. Ring + mouse needs ~22 px or more.",
           font=font(11), fill=(150, 156, 166))

    for ci, (key, label) in enumerate(TRAY_STYLES):
        x = 16 + ci * col_w
        d.text((x, 58), label, font=font(14), fill=(230, 234, 240))

        # source
        src = icon(MouseState(battery=87), True, key, 64)
        t = tile(DARK, 76, 76, 8)
        t.alpha_composite(src, (6, 6))
        sheet.paste(t, (x, 80))
        d.text((x, 160), "64 px source", font=font(10), fill=(140, 146, 156))

        # actual sizes on dark
        for j, size in enumerate(SIZES):
            im = icon(MouseState(battery=87), True, key, size)
            t = tile(DARK, 40, 40, 6)
            t.alpha_composite(im, ((40 - size) // 2, (40 - size) // 2))
            sheet.paste(t, (x + j * 46, 184))
            d.text((x + j * 46 + 2, 226), f"{size}px", font=font(9), fill=(140, 146, 156))

        # 4x zoom of 16 px, dark and light
        for j, bg in enumerate((DARK, LIGHT)):
            im = icon(MouseState(battery=87), True, key, 16)
            z = im.resize((64, 64), Image.NEAREST)
            t = tile(bg, 72, 72, 8)
            t.alpha_composite(z, (4, 4))
            sheet.paste(t, (x + j * 78, 244))

        # states at 16 px, 4x
        for j, (battery, charging) in enumerate(((87, False), (12, False), (45, True))):
            im = icon(MouseState(battery=battery, charging=charging), True, key, 16)
            z = im.resize((48, 48), Image.NEAREST)
            t = tile(DARK, 54, 54, 6)
            t.alpha_composite(z, (3, 3))
            sheet.paste(t, (x + j * 58, 326))
        d.text((x, 388), "87%        12%        charging", font=font(9), fill=(140, 146, 156))

    out = Path("docs/screenshots/tray-styles.png")
    sheet.save(out)
    print("wrote", out, sheet.size)


if __name__ == "__main__":
    main()
