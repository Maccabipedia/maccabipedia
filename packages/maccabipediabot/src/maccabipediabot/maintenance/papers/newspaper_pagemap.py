"""Draw a scan's detected rules (blue) and a coordinate grid, to write a crop spec by eye.

    uv run python -m maccabipediabot.maintenance.papers.newspaper_pagemap scan.jpg map.jpg \
        [--step 100] [--region x0 y0 x1 y1]

Coordinates on the grid are original-scan pixels, the units a crop spec uses.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from maccabipediabot.maintenance.papers.newspaper_crop import load_scan, thin_rules


def page_map(orig: Image.Image, step: int, region: tuple[int, int, int, int] | None) -> Image.Image:
    img = orig.convert("RGB")
    dark = (np.asarray(img.convert("L")) < 140).astype(np.float32)
    draw = ImageDraw.Draw(img)
    for y, x0, x1 in thin_rules(dark):
        draw.line([(x0, y), (x1, y)], fill=(0, 90, 255), width=4)
    for x, y0, y1 in thin_rules(dark.T):
        draw.line([(x, y0), (x, y1)], fill=(0, 90, 255), width=4)
    x0, y0, x1, y1 = region or (0, 0, *img.size)
    part = img.crop((x0, y0, x1, y1))
    scale = min(1800 / part.width, 1800 / part.height, 3)
    view = part.resize((round(part.width * scale), round(part.height * scale)))
    d = ImageDraw.Draw(view)
    font = ImageFont.load_default(size=18)
    for x in range((x0 // step + 1) * step, x1, step):
        d.line([((x - x0) * scale, 0), ((x - x0) * scale, view.height)], fill=(255, 0, 160))
        d.text(((x - x0) * scale + 2, 2), str(x), fill=(200, 0, 120), font=font)
    for y in range((y0 // step + 1) * step, y1, step):
        d.line([(0, (y - y0) * scale), (view.width, (y - y0) * scale)], fill=(255, 0, 160))
        d.text((2, (y - y0) * scale + 2), str(y), fill=(200, 0, 120), font=font)
    return view


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("scan", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--step", type=int, default=100)
    p.add_argument("--region", type=int, nargs=4, metavar=("X0", "Y0", "X1", "Y1"))
    args = p.parse_args()
    page_map(load_scan(args.scan), args.step, tuple(args.region) if args.region else None).save(args.out, quality=85)
    print(args.out)


if __name__ == "__main__":
    main()
