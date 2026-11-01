"""Compare before/after screenshots and write the PR comment (used by run.py).

`before_again` and `after_again` are second shots of each state, taken after
switching away and back. A page that differs between two shots of the same
code (a random box, a slider, ties in a leaderboard ordered differently by
another render) is reported as unstable rather than as changed, so its noise
cannot pass for the PR's change.

Writes the images the comment shows (only for shots that differ) and
report.json into the output directory; comment() builds the markdown.
"""
import json
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageChops

MARKER = '<!-- visual-diff -->'
# A shot counts as changed when more pixels than this differ. A count, not a
# share of the image: a swapped 20x20 icon must show on a 6000px-tall page too.
# Two renders of the same code matched pixel for pixel when this was measured;
# the margin is for stray anti-aliasing.
MIN_CHANGED_PIXELS = 20
# How far one colour channel must move for a pixel to count as changed.
CHANNEL_DELTA = 16


def padded(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    canvas = Image.new('RGB', size, 'white')
    canvas.paste(image, (0, 0))
    return canvas


def changed_pixels(first: Path, second: Path) -> tuple[int, float, Image.Image, Image.Image]:
    """How many pixels differ and what share that is, the mask of them, and
    `second` on the common canvas. Shots of different heights are compared on a
    canvas that fits both, so a page that grew counts its new part as changed.
    A pixel differs when any one channel moves: a greyscale difference would
    weight blue at 0.11 and miss a recoloured link."""
    a, b = Image.open(first).convert('RGB'), Image.open(second).convert('RGB')
    size = (max(a.width, b.width), max(a.height, b.height))
    a, b = padded(a, size), padded(b, size)
    red, green, blue = ImageChops.difference(a, b).split()
    largest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    mask = largest.point(lambda v: 255 if v > CHANNEL_DELTA else 0)
    count = mask.histogram()[255]
    return count, count / (size[0] * size[1]), mask, b


def changes_image(mask: Image.Image, after: Image.Image) -> Image.Image:
    """The after shot faded to grey, with every changed pixel in red."""
    faded = Image.blend(after.convert('L').convert('RGB'),
                        Image.new('RGB', after.size, 'white'), 0.65)
    return Image.composite(Image.new('RGB', after.size, (220, 0, 0)), faded, mask)


def save_jpeg(image: Image.Image, target: Path) -> None:
    image.convert('RGB').save(target, 'JPEG', quality=85, optimize=True)


def compare(before: Path, after: Path, before_again: Path, after_again: Path,
            out: Path) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    shots = json.loads((after / 'shots.json').read_text(encoding='utf-8'))
    before_status = {s['file']: s['status'] for s in
                     json.loads((before / 'shots.json').read_text(encoding='utf-8'))}
    results = []
    for shot in shots:
        name = shot['file']
        noise = max(changed_pixels(before / name, before_again / name)[0],
                    changed_pixels(after / name, after_again / name)[0])
        count, share, mask, after_canvas = changed_pixels(before / name, after / name)
        if noise > MIN_CHANGED_PIXELS:
            verdict = 'unstable'
        elif count > MIN_CHANGED_PIXELS:
            verdict = 'changed'
        else:
            verdict = 'same'
        stem = name.removesuffix('.png')
        if verdict != 'same':
            save_jpeg(Image.open(before / name), out / f'{stem}-before.jpg')
            save_jpeg(Image.open(after / name), out / f'{stem}-after.jpg')
            save_jpeg(changes_image(mask, after_canvas), out / f'{stem}-changes.jpg')
        results.append({**shot, 'stem': stem, 'verdict': verdict,
                        'pixels': count, 'share': round(share, 4), 'noise_pixels': noise,
                        'before_status': before_status.get(name)})
    (out / 'report.json').write_text(json.dumps(results, ensure_ascii=False, indent=1),
                                     encoding='utf-8')
    return results


def pair_table(result: dict, image_base: str) -> str:
    width = 300 if result['viewport'] == 'desktop' else 200
    cells = []
    for kind in ('before', 'after', 'changes'):
        url = f'{image_base}/{quote(result["stem"])}-{kind}.jpg'
        cells.append(f'<a href="{url}"><img src="{url}" width="{width}"></a>')
    return ('| Before | After | Changes (red) |\n|---|---|---|\n| '
            + ' | '.join(cells) + ' |\n')


def comment(results: list[dict], image_base: str, header: str) -> str:
    order = list(dict.fromkeys(r['title'] for r in results))
    results = sorted(results, key=lambda r: order.index(r['title']))  # a page's widths together
    changed =[r for r in results if r['verdict'] == 'changed']
    unstable = [r for r in results if r['verdict'] == 'unstable']
    same = [r for r in results if r['verdict'] == 'same']
    lines = [MARKER, '## Before / after', '', header, '']
    if changed:
        lines.append(f'**{len(changed)} of {len(results)} shots changed.** '
                     'Click an image for full size.\n')
    else:
        lines.append(f'**No visual change** in any of the {len(results)} shots.\n')
    for result in changed:
        lines.append(f'<details open><summary><b>{result["title"]}</b> · '
                     f'{result["viewport"]} · {result["pixels"]:,} pixels changed ({result["share"]:.1%})'
                     '</summary>\n')
        lines.append(pair_table(result, image_base))
        lines.append('</details>\n')
    for result in unstable:
        lines.append(f'<details><summary>{result["title"]} · {result["viewport"]} · '
                     'unstable: differs between two shots of the same code, so a '
                     'change here cannot be told from noise</summary>\n')
        lines.append(pair_table(result, image_base))
        lines.append('</details>\n')
    broken = [r for r in results if r['status'] != 200 or r['before_status'] != 200]
    if broken:
        lines.append('**Pages that did not load (HTTP status before → after):** ' + ', '.join(
            f'{r["title"]} ({r["before_status"]} → {r["status"]})' for r in broken
            if r['viewport'] == 'desktop') + '\n')
    if same:
        lines.append('<details><summary>Unchanged: ' + str(len(same)) + ' shots</summary>\n\n'
                     + '\n'.join(f'- {r["title"]} · {r["viewport"]}' for r in same)
                     + '\n</details>\n')
    lines.append('<sub>Rendered on the CI local wiki (snapshot data, logged out) by '
                 '`.github/workflows/visual_diff.yaml`. To shoot more pages, add a '
                 '`<!-- visual-pages ... -->` block to the PR description, one title per '
                 'line. See `.claude/visual_diff.md`.</sub>')
    return '\n'.join(lines) + '\n'
