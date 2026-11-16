"""Print the text lines of one column, to build ``highlight`` strokes for a crop spec.

    uv run python -m maccabipediabot.maintenance.papers.newspaper_lines scan.jpg x0 y0 x1 y1

The region is one column, in scan pixels. For each line it prints the ink box, a stroke
ready to paste into the spec, and the line's words as x ranges from left to right. Hebrew
reads right to left, so a stroke that starts mid-line takes its x1 from the gap just right
of the first Maccabi word, and one that ends mid-line takes its x0 from the gap after the
last one. Give each stroke the column's full width otherwise.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from maccabipediabot.maintenance.papers.newspaper_crop import load_scan

# A stroke reaches a little past the ink on both sides, like a hand-drawn one. It sits 1 px
# below the ink top (ascenders such as ל pull that top up) and 2 px below the ink bottom, so
# two marked lines keep a white gap between them.
_OVERSHOOT, _TOP, _BOTTOM = 5, 1, 2


def runs(flags: np.ndarray, bridge: int = 0) -> list[tuple[int, int]]:
    """Inclusive (start, end) runs of True, joining runs separated by at most ``bridge`` False."""
    found: list[list[int]] = []
    for i in np.flatnonzero(flags):
        if found and i - found[-1][1] <= bridge + 1:
            found[-1][1] = int(i)
        else:
            found.append([int(i), int(i)])
    return [(a, b) for a, b in found]


def text_lines(gray: np.ndarray, region: tuple[int, int, int, int], dark: int = 110,
               min_ink: int = 5) -> list[dict]:
    x0, y0, x1, y1 = region
    ink = gray[y0:y1, x0:x1] < dark
    lines = []
    for top, bottom in runs(ink.sum(axis=1) >= min_ink):
        if bottom - top < 3:
            continue  # a dash or a speck between lines
        cols = ink[top:bottom + 1].any(axis=0)
        words = runs(cols, bridge=max(2, (bottom - top) // 5))
        lines.append({
            "ink": [x0 + words[0][0], y0 + top, x0 + words[-1][1], y0 + bottom],
            "stroke": [x0 + words[0][0] - _OVERSHOOT, y0 + top + _TOP,
                       x0 + words[-1][1] + _OVERSHOOT, y0 + bottom + _BOTTOM],
            "words": [(x0 + a, x0 + b) for a, b in words],
        })
    return lines


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("scan", type=Path)
    p.add_argument("region", type=int, nargs=4, metavar=("X0", "Y0", "X1", "Y1"))
    p.add_argument("--dark", type=int, default=110, help="grey level below which a pixel is ink")
    args = p.parse_args(argv)
    gray = np.asarray(load_scan(args.scan).convert("L"), dtype=np.int32)
    for line in text_lines(gray, tuple(args.region), args.dark):
        print(f"ink {line['ink']}  stroke {line['stroke']}  words {line['words']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
