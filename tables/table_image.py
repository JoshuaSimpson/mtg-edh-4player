#!/usr/bin/env python3
"""
Paint the 6-player table surface (build/6p/table.png) from the 4-player one.

    python3 tables/table_image.py build/6p

Reads build/6p/layout.json (written by `tables/build.py generate6p`) and the 4p
table image (TableURL in save.template.json, downloaded once into build/cache/).
Needs Pillow and numpy -- the Makefile runs this in a local .venv.

The 4p image is 9500 x 5600 px at ~110 px per world unit, centred on the table,
with one seat per quadrant: each seat's art (mat outline, land strip, deck /
graveyard / exile and commander icons) spans u = 0 .. 43.2 from the centre line
outward. For every 6p seat the matching 4p quadrant is cropped, split at
layout.cutU with a `shrink`-wide strip dropped (the mat's empty middle, so the
zones' narrower playmat still lines up with the outline), shifted exactly as
build.py shifted that seat's zones, recoloured for the new seats, and pasted
onto a felt board sized to the 6p board object.
"""

import json
import os
import sys
import urllib.request

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

SRC_PPU = 110.0  # 4p image pixels per world unit
OUT_PPU = 60.0  # 6p image pixels per world unit (keeps it under 8192 px wide)
FELT = (51, 51, 51)  # the 4p image's background
BORDER = (99, 83, 81)  # outline colour used by the mod's panels
BORDER_W = 0.3  # world units
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(os.path.dirname(HERE), "build", "cache")


def source_image(url: str) -> Image.Image:
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "table4p.png")
    if not os.path.exists(path):
        print(f"[6p] downloading 4p table image -> {path}")
        urllib.request.urlretrieve(url, path)
    return Image.open(path).convert("RGB")


def line_colour(arr: np.ndarray) -> np.ndarray:
    """The dominant non-background colour of a seat's art (its outline colour)."""
    px = arr.reshape(-1, 3).astype(float)
    far = px[np.abs(px - FELT).sum(axis=1) > 300]
    return far.mean(axis=0)


def recolour(arr: np.ndarray, target) -> np.ndarray:
    """Map the art's outline colour onto target, keeping the anti-aliasing: each
    pixel is projected onto the felt -> outline-colour line and re-expanded along
    felt -> target."""
    bg = np.array(FELT, float)
    src = line_colour(arr) - bg
    tgt = np.array([c * 255 for c in target], float) - bg
    d = arr.astype(float) - bg
    t = np.clip((d @ src) / (src @ src), 0, 1)[..., None]
    return np.clip(bg + t * tgt, 0, 255).astype(np.uint8)


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    out_dir = sys.argv[1]
    with open(os.path.join(out_dir, "layout.json"), encoding="utf-8") as f:
        layout = json.load(f)
    src = source_image(layout["sourceImage"])
    sw, sh = src.size
    scx, scy = sw / 2, sh / 2
    u_max = scx / SRC_PPU  # art extends to the image edge
    z_max = scy / SRC_PPU

    bx, bz = layout["boardHalfWidth"], layout["boardHalfDepth"]
    ow, oh = round(2 * bx * OUT_PPU), round(2 * bz * OUT_PPU)
    out = Image.new("RGB", (ow, oh), BORDER)
    b = round(BORDER_W * OUT_PPU)
    out.paste(Image.new("RGB", (ow - 2 * b, oh - 2 * b), FELT), (b, b))
    ocx, ocy = ow / 2, oh / 2

    cut, shrink = layout["cutU"], layout["shrink"]
    for seat in layout["seats"]:
        o = seat["outward"]
        # template quadrant's z side: the north row is the south row rotated, and
        # the rows keep their colour's side of the table
        zs = -1 if seat["template"] in ("White", "Red") else 1
        pieces = [(0.0, cut, seat["shift"] + shrink), (cut + shrink, u_max, seat["shift"])]
        for ua, ub, shift in pieces:
            # source crop (u -> world x -> px), no mirroring: seats are translated
            x0, x1 = sorted((o * ua, o * ub))
            box = (round(scx + x0 * SRC_PPU), 0 if zs > 0 else round(scy),
                   round(scx + x1 * SRC_PPU), round(scy) if zs > 0 else sh)
            crop = src.crop(box)
            if seat["recolor"]:
                crop = Image.fromarray(recolour(np.asarray(crop), seat["recolor"]))
            # destination
            dx0 = o * (ua + shift) if o > 0 else -(ub + shift)
            w = round((ub - ua) * OUT_PPU)
            h = round(z_max * OUT_PPU)
            crop = crop.resize((w, h), Image.LANCZOS)
            px = round(ocx + dx0 * OUT_PPU)
            py = round(ocy - h) if zs > 0 else round(ocy)
            out.paste(crop, (px, py))

    path = os.path.join(out_dir, "table.png")
    out.save(path, optimize=True)
    print(f"[6p] painted {ow} x {oh} table image -> {path}")


if __name__ == "__main__":
    main()
