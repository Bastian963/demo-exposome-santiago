"""Generate the food_insecurity exposome sprite sheet (128x32, 4 frames).

Pixel-art in the house palette (cyan/navy/teal/white + one warm amber
accent), matching the family style: a static motif plus a bright dot
travelling along a faint arc across the 4 frames.

Motif: a dinner plate with cutlery and a small, dwindling portion
(household food insecurity) — distinct from the food_environment
market basket (retail access).

Run: .venv/bin/python scripts/gen_food_insecurity_sprite.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

W = H = 32
FRAMES = 4

TRANSP = (0, 0, 0, 0)
CYAN = (115, 239, 247, 255)
CYAN_DIM = (115, 239, 247, 160)
WHITE = (230, 238, 247, 255)
NAVY = (45, 57, 93, 255)
TEAL = (45, 128, 160, 255)
DEEP = (20, 27, 49, 255)
AMBER = (242, 140, 56, 255)


def px(img, x, y, c):
    if 0 <= x < W and 0 <= y < H:
        img.putpixel((x, y), c)


def rect(img, x0, y0, x1, y1, c):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            px(img, x, y, c)


def arc_points():
    """Shallow parabola from (7,13) to (24,13), peak near y=7."""
    pts = []
    x0, x1 = 7, 24
    for x in range(x0, x1 + 1):
        t = (x - (x0 + x1) / 2) / ((x1 - x0) / 2)  # -1..1
        y = round(7 + 6 * t * t)  # peak 7, ends ~13
        pts.append((x, y))
    return pts


def draw_static(img, bob):
    """Plate + cutlery + small portion. `bob` lifts the portion 1px."""
    # table edge / ground shadow
    rect(img, 6, 29, 25, 29, NAVY)
    rect(img, 8, 30, 23, 30, DEEP)

    # plate (wide ellipse-ish, drawn as stacked rects)
    rect(img, 9, 25, 22, 25, CYAN)      # rim highlight
    rect(img, 8, 26, 23, 27, TEAL)      # plate body
    rect(img, 9, 28, 22, 28, NAVY)      # underside shade
    # plate well (inner shadow)
    rect(img, 11, 26, 20, 26, DEEP)

    by = -bob  # portion vertical offset
    # small portion sitting on the plate (amber, deliberately modest)
    rect(img, 14, 22 + by, 17, 24 + by, AMBER)
    px(img, 14, 22 + by, WHITE)  # highlight
    px(img, 18, 24 + by, AMBER)  # crumb

    # fork (left of plate)
    rect(img, 4, 20, 4, 27, TEAL)
    px(img, 3, 19, CYAN)
    px(img, 4, 19, CYAN)
    px(img, 5, 19, CYAN)
    px(img, 3, 20, TEAL)
    px(img, 5, 20, TEAL)

    # knife (right of plate)
    rect(img, 27, 20, 27, 27, TEAL)
    rect(img, 26, 19, 27, 21, CYAN)


def build():
    sheet = Image.new("RGBA", (W * FRAMES, H), TRANSP)
    pts = arc_points()
    # dot travels across the arc; pick 4 evenly-spaced positions
    positions = [pts[int(k * (len(pts) - 1) / (FRAMES - 1))] for k in range(FRAMES)]
    for f in range(FRAMES):
        frame = Image.new("RGBA", (W, H), TRANSP)
        # faint arc
        for (x, y) in pts:
            px(frame, x, y, CYAN_DIM)
        bob = 1 if f in (1, 3) else 0
        draw_static(frame, bob)
        # bright travelling dot (2x2) at this frame's arc position
        dx, dy = positions[f]
        rect(frame, dx, dy - 1, dx + 1, dy, WHITE)
        sheet.paste(frame, (f * W, 0), frame)
    return sheet


def main():
    out = Path("webapp/public/sprites/exposomes/food_insecurity.png")
    sheet = build()
    sheet.save(out)
    print(f"Wrote {out} ({sheet.size[0]}x{sheet.size[1]})")
    # upscaled preview
    prev = Path("/tmp/_food_insecurity_sprite_preview.png")
    sheet.resize((sheet.width * 6, sheet.height * 6), Image.NEAREST).save(prev)
    print(f"Preview {prev}")


if __name__ == "__main__":
    main()
