"""Generate the food_environment exposome sprite sheet (128x32, 4 frames).

Pixel-art in the house palette (cyan/navy/teal/white + one warm amber
accent for produce), matching the family style: a static motif plus a
bright dot travelling along a faint arc across the 4 frames.

Motif: a market basket of produce (healthy-food access).

Run: .venv/bin/python scripts/gen_food_sprite.py
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
LEAF = (120, 214, 170, 255)  # soft green produce accent


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
    """Basket + produce. `bob` shifts produce up by 1px on some frames."""
    # base platform / ground shadow
    rect(img, 8, 29, 23, 29, NAVY)
    rect(img, 10, 30, 21, 30, DEEP)

    # basket rim
    rect(img, 8, 20, 23, 21, TEAL)
    rect(img, 8, 20, 23, 20, CYAN)  # rim highlight
    # basket body (tapered look via side insets on lower rows)
    rect(img, 9, 22, 22, 28, TEAL)
    rect(img, 10, 28, 21, 28, NAVY)  # bottom shade
    # weave verticals
    for x in (11, 14, 17, 20):
        rect(img, x, 22, x, 27, NAVY)
    # weave horizontal
    rect(img, 9, 25, 22, 25, DEEP)

    by = -bob  # produce vertical offset
    # produce poking above the rim
    # left leafy sprig (green)
    rect(img, 10, 16 + by, 11, 19 + by, LEAF)
    px(img, 9, 18 + by, LEAF)
    px(img, 12, 15 + by, LEAF)
    # center fruit (cyan/white)
    rect(img, 13, 15 + by, 17, 19 + by, CYAN)
    rect(img, 13, 15 + by, 14, 16 + by, WHITE)  # highlight
    px(img, 15, 14 + by, NAVY)  # stem
    # right fruit (warm amber → reads as "food")
    rect(img, 18, 16 + by, 21, 19 + by, AMBER)
    px(img, 18, 16 + by, WHITE)


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
    out = Path("webapp/public/sprites/exposomes/food_environment.png")
    sheet = build()
    sheet.save(out)
    print(f"Wrote {out} ({sheet.size[0]}x{sheet.size[1]})")
    # upscaled preview
    prev = Path("/tmp/_food_sprite_preview.png")
    sheet.resize((sheet.width * 6, sheet.height * 6), Image.NEAREST).save(prev)
    print(f"Preview {prev}")


if __name__ == "__main__":
    main()
