#!/usr/bin/env python3
"""Render tray-icon design mockups (A-F) for review.

Writes docs/screenshots/tray-mockups.png.  Each column shows:
  * the 64x64 source pixmap
  * 22px panel-size renders on dark and light panels
  * 4x nearest-neighbour zoom of the 22px renders
  * 87% / 12% / charging states at 22px (2x)
"""
from __future__ import annotations

import math
from pathlib import Path

import cairo
from PIL import Image, ImageDraw, ImageFont

ICON = 64
GREEN = (0.28, 0.84, 0.46)
YELLOW = (0.98, 0.74, 0.18)
RED = (0.95, 0.32, 0.32)
BLUE = (0.35, 0.72, 1.0)
WHITE = (1.0, 1.0, 1.0)
INK = (0.03, 0.04, 0.07)
DARK_BG = (27, 30, 34)
LIGHT_BG = (239, 241, 245)

FONT_PATHS = [
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/gnu-free/FreeSansBold.ttf",
]


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_PATHS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def accent_for(battery: int, charging: bool) -> tuple[float, float, float]:
    if charging:
        return BLUE
    if battery > 40:
        return GREEN
    if battery > 20:
        return YELLOW
    return RED


def rounded(ctx, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    ctx.close_path()


def mouse_body(ctx, x, y, w, h, stroke=3.2, alpha=0.95):
    ctx.set_line_width(stroke)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.set_source_rgba(*WHITE, alpha)
    rounded(ctx, x, y, w, h, w * 0.36)
    ctx.stroke()


def wheel(ctx, x, y, w=6, h=9, color=WHITE, alpha=0.9):
    ctx.set_source_rgba(*color, alpha)
    rounded(ctx, x, y, w, h, w / 2)
    ctx.fill()


def text(ctx, value, cx, cy, size, color=WHITE, outline=INK, outline_w=3.0):
    ctx.select_font_face("DejaVu Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(size)
    ext = ctx.text_extents(value)
    x = cx - ext.width / 2 - ext.x_bearing
    y = cy - ext.height / 2 - ext.y_bearing
    ctx.move_to(x, y)
    ctx.text_path(value)
    ctx.set_line_width(outline_w)
    ctx.set_source_rgba(*outline, 0.92)
    ctx.stroke_preserve()
    ctx.set_source_rgba(*color, 1.0)
    ctx.fill()


def new_surface(w=ICON, h=ICON):
    return cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)


# ---------------------------------------------------------------- variants
def variant_a(battery, charging, pct=True):
    """A: mouse outline, big percentage on the body."""
    s = new_surface()
    c = cairo.Context(s)
    accent = accent_for(battery, charging)
    mouse_body(c, 13, 5, 38, 54)
    c.set_line_width(2)
    c.set_source_rgba(*WHITE, 0.7)
    c.move_to(14, 22)
    c.line_to(50, 22)
    c.stroke()
    wheel(c, 29, 11)
    text(c, str(battery), 32, 40, 26, accent if not charging else BLUE)
    return s


def variant_b(battery, charging, pct=True):
    """B: mouse silhouette filled like a battery gauge, number on top."""
    s = new_surface()
    c = cairo.Context(s)
    accent = accent_for(battery, charging)
    # gauge fill clipped to the body; dark base keeps it readable on light panels
    c.save()
    rounded(c, 13, 5, 38, 54, 14)
    c.clip()
    c.set_source_rgba(*INK, 0.72)
    c.rectangle(13, 5, 38, 54)
    c.fill()
    fill_h = 50 * battery / 100
    c.set_source_rgba(*accent, 0.62)
    c.rectangle(13, 59 - fill_h, 38, fill_h)
    c.fill()
    c.restore()
    mouse_body(c, 13, 5, 38, 54)
    c.set_line_width(2)
    c.set_source_rgba(*WHITE, 0.7)
    c.move_to(14, 22)
    c.line_to(50, 22)
    c.stroke()
    wheel(c, 29, 11)
    text(c, str(battery), 32, 40, 26)
    return s


def variant_c(battery, charging, pct=True):
    """C: mouse plus a separate round badge in the corner."""
    s = new_surface()
    c = cairo.Context(s)
    accent = accent_for(battery, charging)
    mouse_body(c, 5, 4, 34, 54, stroke=3)
    c.set_line_width(1.8)
    c.set_source_rgba(*WHITE, 0.65)
    c.move_to(6, 20)
    c.line_to(38, 20)
    c.stroke()
    wheel(c, 17, 10, 5, 8)
    c.set_source_rgba(*accent, 1.0)
    c.arc(46, 44, 14.5, 0, 2 * math.pi)
    c.fill_preserve()
    c.set_line_width(2)
    c.set_source_rgba(*INK, 0.9)
    c.stroke()
    text(c, str(battery), 46, 44.5, 15, WHITE, INK, 2.2)
    return s


def variant_d(battery, charging, pct=True):
    """D: narrow mouse glyph + large number beside it."""
    s = new_surface()
    c = cairo.Context(s)
    accent = accent_for(battery, charging)
    mouse_body(c, 3, 6, 27, 52, stroke=2.8)
    c.set_line_width(1.6)
    c.set_source_rgba(*WHITE, 0.6)
    c.move_to(4, 21)
    c.line_to(29, 21)
    c.stroke()
    wheel(c, 13, 11, 5, 8)
    text(c, str(battery), 47, 32, 29, accent if not charging else BLUE, INK, 3.2)
    return s


def variant_e(battery, charging, pct=True):
    """E: circular battery ring around a small mouse."""
    s = new_surface()
    c = cairo.Context(s)
    accent = accent_for(battery, charging)
    cx = cy = 32
    r = 27
    c.set_line_width(4.6)
    c.set_line_cap(cairo.LINE_CAP_ROUND)
    c.set_source_rgba(1, 1, 1, 0.16)
    c.arc(cx, cy, r, 0, 2 * math.pi)
    c.stroke()
    c.set_source_rgba(*accent, 0.95)
    c.arc(cx, cy, r, -math.pi / 2, -math.pi / 2 + 2 * math.pi * battery / 100)
    c.stroke()
    mouse_body(c, 17, 12, 30, 40, stroke=2.4)
    c.set_line_width(1.4)
    c.set_source_rgba(*WHITE, 0.6)
    c.move_to(18, 26)
    c.line_to(46, 26)
    c.stroke()
    text(c, str(battery), 32, 39, 18, WHITE, INK, 2.6)
    return s


def variant_f(battery, charging, pct=True):
    """F: wide icon, mouse + 87% (only useful if the host keeps aspect ratio)."""
    s = new_surface(96, 48)
    c = cairo.Context(s)
    accent = accent_for(battery, charging)
    mouse_body(c, 4, 3, 32, 42, stroke=2.6)
    c.set_line_width(1.6)
    c.set_source_rgba(*WHITE, 0.65)
    c.move_to(5, 17)
    c.line_to(35, 17)
    c.stroke()
    wheel(c, 17, 9, 5, 7)
    text(c, str(battery), 58, 22, 26, accent if not charging else BLUE, INK, 3.0)
    c.select_font_face("DejaVu Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    c.set_font_size(13)
    c.set_source_rgba(*WHITE, 0.9)
    c.move_to(80, 28)
    c.show_text("%")
    return s


def variant_g(battery, charging, pct=True):
    """G: dark mouse body, coloured percentage — readable on light and dark."""
    s = new_surface()
    c = cairo.Context(s)
    accent = accent_for(battery, charging)
    c.set_line_width(3.2)
    c.set_line_join(cairo.LINE_JOIN_ROUND)
    rounded(c, 13, 5, 38, 54, 14)
    c.set_source_rgba(0.055, 0.065, 0.09, 0.94)
    c.fill_preserve()
    c.set_source_rgba(*WHITE, 0.95)
    c.stroke()
    c.set_line_width(2)
    c.set_source_rgba(*WHITE, 0.72)
    c.move_to(14, 22)
    c.line_to(50, 22)
    c.stroke()
    wheel(c, 29, 11)
    text(c, str(battery), 32, 40, 26, accent if not charging else BLUE, INK, 2.4)
    return s


VARIANTS = [
    ("A", "Number on body", variant_a),
    ("B", "Battery fill body", variant_b),
    ("C", "Corner badge", variant_c),
    ("D", "Number beside mouse", variant_d),
    ("E", "Battery ring", variant_e),
    ("F", "Wide, mouse + 87%", variant_f),
    ("G", "Dark body, % only", variant_g),
]


# ---------------------------------------------------------------- helpers
def cairo_to_pil(surface: cairo.ImageSurface) -> Image.Image:
    w, h = surface.get_width(), surface.get_height()
    surface.flush()
    data = bytes(surface.get_data())
    stride = surface.get_stride()
    out = bytearray(w * h * 4)
    for y in range(h):
        row = data[y * stride : y * stride + w * 4]
        for x in range(w):
            b, g, r, a = row[x * 4 : x * 4 + 4]
            out[(y * w + x) * 4 : (y * w + x) * 4 + 4] = bytes((r, g, b, a))
    return Image.frombytes("RGBA", (w, h), bytes(out))


def scaled(icon: Image.Image, size: int) -> Image.Image:
    if icon.width == icon.height:
        return icon.resize((size, size), Image.LANCZOS)
    # preserve aspect ratio, fit height
    w = round(icon.width * size / icon.height)
    return icon.resize((w, size), Image.LANCZOS)


def tile(bg, w, h, radius=8):
    img = Image.new("RGBA", (w, h), bg + (255,))
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    img.putalpha(mask)
    return img


def main():
    columns = len(VARIANTS)
    col_w = 214
    width = columns * col_w + 24
    height = 470
    sheet = Image.new("RGB", (width, height), (18, 20, 23))
    draw = ImageDraw.Draw(sheet)

    draw.text((16, 10), "RAWM Control — tray icon mockups (mouse + battery %)", font=font(18), fill=(235, 238, 243))
    draw.text((16, 34), "Each column: 64 px source, 22 px panel size (dark/light), 4x zoom, then 87% / 12% / charging at 22 px.",
              font=font(11), fill=(150, 156, 166))

    for ci, (letter, name, fn) in enumerate(VARIANTS):
        x = 16 + ci * col_w
        draw.text((x, 62), f"{letter}  {name}", font=font(13), fill=(230, 234, 240))

        big = cairo_to_pil(fn(87, False))
        # 64px source on a dark tile
        dark = tile(DARK_BG, 116, 84)
        big64 = big if big.width == 64 else big.resize((64, 64), Image.LANCZOS)
        dark.alpha_composite(big64, ((116 - 64) // 2, (84 - 64) // 2))
        sheet.paste(dark, (x, 84))
        draw.text((x + 6, 170), "64 px source", font=font(10), fill=(140, 146, 156))

        small = scaled(big, 22)
        # 22px on dark and light tiles
        for j, bg in enumerate((DARK_BG, LIGHT_BG)):
            t = tile(bg, 46, 40, 7)
            if small.width > 46:
                small = small.resize((46, 22), Image.LANCZOS)
            t.alpha_composite(small, ((46 - small.width) // 2, (40 - small.height) // 2))
            sheet.paste(t, (x + j * 54, 192))
        draw.text((x + 4, 234), "22 px dark / light", font=font(10), fill=(140, 146, 156))

        # 4x zoom
        for j, bg in enumerate((DARK_BG, LIGHT_BG)):
            t = tile(bg, 96, 96, 8)
            z = small.resize((small.width * 4, small.height * 4), Image.NEAREST)
            t.alpha_composite(z, ((96 - z.width) // 2, (96 - z.height) // 2))
            sheet.paste(t, (x + j * 104, 252))
        draw.text((x + 4, 350), "4x zoom (pixel-accurate)", font=font(10), fill=(140, 146, 156))

        # states at 22px, 2x
        states = [(87, False), (12, False), (45, True)]
        for j, (battery, charging) in enumerate(states):
            icon = scaled(cairo_to_pil(fn(battery, charging)), 22)
            z = icon.resize((icon.width * 2, icon.height * 2), Image.NEAREST)
            t = tile(DARK_BG, 64, 48, 6)
            t.alpha_composite(z, ((64 - z.width) // 2, (48 - z.height) // 2))
            sheet.paste(t, (x + j * 68, 372))
        draw.text((x + 4, 424), "87%      12%      charging", font=font(9), fill=(140, 146, 156))

    out = Path("docs/screenshots/tray-mockups.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print("wrote", out, sheet.size)


if __name__ == "__main__":
    main()
