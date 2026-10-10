"""Build a newspaper crop from a spec, and check every cut edge against the page.

Choosing what to keep is done by eye; this module makes the rest exact and checkable.

A spec (JSON), all coordinates in ORIGINAL scan pixels:

    {"width": W, "height": H,
     "pieces": [{"box": [x0, y0, x1, y1], "at": [x, y],
                 "blank": [[x0, y0, x1, y1], ...]}],       # relative to the piece
     "wipe": [[[x, y], [x, y], ...]]}                       # polygons, e.g. a slanted rule

``pieces`` are pasted onto a white canvas (stack columns that wrap around another story);
``blank`` paints a neighbouring story white; ``wipe`` paints a polygon white.

The edge check finds the page's thin rules (solid or dotted: dark along their length,
light a few px to either side) and reports each cut edge:

* ``cuts_ink``  — ink on the cut line that continues 2 px to both sides: a letter or a
  photo is cut. Tested before trusting a nearby rule, since a cut 20 px above a rule
  can still slice the line just above it. Must be fixed or explained.
* ``on_rule``   — the edge runs along a rule.
* ``off_rule``  — a blank edge in plain gutter: it can hide whole lines of the article
  without cutting a letter, so read what it covers.
* ``gutter``    — a kept edge in clean gutter.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

_WINDOW, _SIDE, _MIN_LEN, _SNAP = 41, 6, 160, 30
_DARK = 140
_INK_LIMIT = 0.01
# One cut letter on a long edge is a small share but still a cut: a stroke is 3+ px wide.
_INK_MIN_PIXELS = 3
_CROSS_PAD = 6  # px either side of a crossing rule that are not counted as cut ink


@dataclass(frozen=True)
class EdgeResult:
    label: str
    verdict: str          # cuts_ink | on_rule | off_rule | gutter
    position: int
    span: tuple[int, int]
    ink: float

    def __str__(self) -> str:
        return f"{self.label:22} {self.verdict:8} at {self.position} span {self.span[0]}-{self.span[1]} ink {self.ink:.1%}"


def load_spec(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


class CropSpecError(ValueError):
    """The spec would drop or duplicate part of the page."""


def validate_spec(size: tuple[int, int], spec: dict) -> None:
    width, height = size
    placed = []
    for i, piece in enumerate(spec["pieces"]):
        x0, y0, x1, y1 = piece["box"]
        if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
            raise CropSpecError(f"piece {i} box {piece['box']} is outside the {width}x{height} scan")
        ax, ay = piece.get("at", (0, 0))
        target = (ax, ay, ax + x1 - x0, ay + y1 - y0)
        if target[0] < 0 or target[1] < 0 or target[2] > spec["width"] or target[3] > spec["height"]:
            raise CropSpecError(f"piece {i} lands at {target}, outside the {spec['width']}x{spec['height']} "
                                f"canvas: part of it would be lost")
        for j, other in enumerate(placed):
            if target[0] < other[2] and other[0] < target[2] and target[1] < other[3] and other[1] < target[3]:
                raise CropSpecError(f"pieces {j} and {i} overlap on the canvas")
        placed.append(target)


def compose(orig: Image.Image, spec: dict) -> Image.Image:
    validate_spec(orig.size, spec)
    orig = orig.convert("RGB")
    canvas = Image.new("RGB", (spec["width"], spec["height"]), "white")
    for piece in spec["pieces"]:
        part = orig.crop(tuple(piece["box"]))
        draw = ImageDraw.Draw(part)
        for rect in piece.get("blank", []):
            draw.rectangle(rect, fill="white")
        canvas.paste(part, tuple(piece.get("at", (0, 0))))
    for polygon in spec.get("wipe", []):
        for piece in spec["pieces"]:
            x0, y0, x1, y1 = piece["box"]
            ax, ay = piece.get("at", (0, 0))
            mask = Image.new("L", (x1 - x0, y1 - y0), 0)
            ImageDraw.Draw(mask).polygon([(x - x0, y - y0) for x, y in polygon], fill=255)
            canvas.paste("white", (ax, ay), mask)
    return canvas


def thin_rules(dark: np.ndarray) -> list[tuple[int, int, int]]:
    """Rows of ``dark`` holding a thin horizontal rule, as (y, x0, x1)."""
    kernel = np.ones(_WINDOW) / _WINDOW
    frac = np.apply_along_axis(lambda r: np.convolve(r, kernel, mode="same"), 1, dark)
    line = (frac > 0.33) & (np.maximum(np.roll(frac, _SIDE, axis=0), np.roll(frac, -_SIDE, axis=0)) < 0.12)
    found = []
    for y in range(_SIDE, dark.shape[0] - _SIDE):
        row = np.concatenate([[False], line[y], [False]])
        edges = np.flatnonzero(np.diff(row.astype(np.int8)))
        found += [(y, int(a), int(b)) for a, b in zip(edges[::2], edges[1::2]) if b - a >= _MIN_LEN]
    merged: list[tuple[int, int, int]] = []
    for y, a, b in found:
        if merged and y - merged[-1][0] <= 3 and a < merged[-1][2] and b > merged[-1][1]:
            merged[-1] = (y, min(merged[-1][1], a), max(merged[-1][2], b))
        else:
            merged.append((y, a, b))
    return merged


def _keep_mask(size: tuple[int, int], spec: dict) -> np.ndarray:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for piece in spec["pieces"]:
        draw.rectangle(piece["box"], fill=255)
    for piece in spec["pieces"]:
        x0, y0, x1, y1 = piece["box"]
        for b0, b1, b2, b3 in piece.get("blank", []):
            draw.rectangle([x0 + b0, y0 + b1, min(x0 + b2, x1), min(y0 + b3, y1)], fill=0)
    for polygon in spec.get("wipe", []):
        draw.polygon([tuple(pt) for pt in polygon], fill=0)
    return np.asarray(mask) > 0


def _edges(spec: dict) -> list[tuple[str, str, int, int, int]]:
    edges = []
    for i, piece in enumerate(spec["pieces"]):
        x0, y0, x1, y1 = piece["box"]
        edges += [(f"P{i} top", "h", y0, x0, x1), (f"P{i} bottom", "h", y1, x0, x1),
                  (f"P{i} left", "v", x0, y0, y1), (f"P{i} right", "v", x1, y0, y1)]
        for j, (b0, b1, b2, b3) in enumerate(piece.get("blank", [])):
            ax0, ay0, ax1, ay1 = x0 + b0, y0 + b1, min(x0 + b2, x1), min(y0 + b3, y1)
            for name, kind, at, a, b in (("top", "h", ay0, ax0, ax1), ("bottom", "h", ay1, ax0, ax1),
                                         ("left", "v", ax0, ay0, ay1), ("right", "v", ax1, ay0, ay1)):
                if (kind == "h" and at in (y0, y1)) or (kind == "v" and at in (x0, x1)):
                    continue
                edges.append((f"P{i} blank{j} {name}", kind, at, a, b))
    return edges


def check_edges(orig: Image.Image, spec: dict) -> list[EdgeResult]:
    dark = (np.asarray(orig.convert("L")) < _DARK).astype(np.float32)
    validate_spec(orig.size, spec)
    keep = _keep_mask(orig.size, spec)
    rules = {"h": thin_rules(dark), "v": thin_rules(dark.T)}
    h, w = dark.shape
    results = []
    for label, kind, at, a, b in _edges(spec):
        def px(offset: int, grid: np.ndarray, t: int) -> bool:
            yy, xx = (at + offset, t) if kind == "h" else (t, at + offset)
            return bool(grid[min(max(yy, 0), h - 1), min(max(xx, 0), w - 1)])

        # A column rule crossing this edge is dark on both sides of it too, but it is a
        # rule, not a letter: skip a few px around every perpendicular rule that crosses.
        crossing = {t for pos, s0, s1 in rules["v" if kind == "h" else "h"]
                    if s0 - _CROSS_PAD <= at <= s1 + _CROSS_PAD
                    for t in range(pos - _CROSS_PAD, pos + _CROSS_PAD + 1)}
        crossed = total = 0
        for t in range(max(a, 0), min(b, w if kind == "h" else h)):
            if px(-3, keep, t) == px(3, keep, t):
                continue  # a seam between two kept pieces, not a cut
            if t in crossing:
                continue
            total += 1
            crossed += px(0, dark, t) and px(-2, dark, t) and px(2, dark, t)
        ink = crossed / total if total else 0.0
        near_rule = any(abs(pos - at) <= _SNAP and max(0, min(b, s1) - max(a, s0)) >= 0.5 * max(b - a, 1)
                        for pos, s0, s1 in rules[kind])
        if ink >= _INK_LIMIT or crossed >= _INK_MIN_PIXELS:
            verdict = "cuts_ink"
        elif near_rule:
            verdict = "on_rule"
        elif "blank" in label:
            verdict = "off_rule"
        else:
            verdict = "gutter"
        results.append(EdgeResult(label, verdict, at, (a, b), ink))
    return results


def kept_fraction(size: tuple[int, int], spec: dict) -> float:
    """Share of the scan the crop keeps; above about half it is a whole page."""
    return float(_keep_mask(size, spec).mean())


def before_after(orig: Image.Image, spec: dict, crop: Image.Image, height: int = 1400) -> Image.Image:
    """The scan with kept boxes in red and blanked areas crossed out, next to the crop."""
    marked = orig.convert("RGB")
    shade = Image.new("RGBA", marked.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for piece in spec["pieces"]:
        x0, y0, x1, y1 = piece["box"]
        for b0, b1, b2, b3 in piece.get("blank", []):
            rect = [x0 + b0, y0 + b1, min(x0 + b2, x1), min(y0 + b3, y1)]
            sd.rectangle(rect, fill=(90, 90, 90, 150))
            sd.line(rect, fill=(200, 0, 0, 220), width=8)
            sd.line([rect[0], rect[3], rect[2], rect[1]], fill=(200, 0, 0, 220), width=8)
    for polygon in spec.get("wipe", []):
        sd.polygon([tuple(pt) for pt in polygon], fill=(90, 90, 90, 150))
    marked = Image.alpha_composite(marked.convert("RGBA"), shade).convert("RGB")
    draw = ImageDraw.Draw(marked)
    for piece in spec["pieces"]:
        draw.rectangle(piece["box"], outline=(220, 0, 0), width=max(6, marked.width // 300))
    before = marked.resize((round(marked.width * height / marked.height), height))
    after = crop.convert("RGB").resize((round(crop.width * height / crop.height), height))
    canvas = Image.new("RGB", (before.width + after.width + 30, height), "white")
    canvas.paste(before, (0, 0))
    canvas.paste(after, (before.width + 30, 0))
    return canvas
