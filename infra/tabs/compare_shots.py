"""Compare the before/after page screenshots pixel by pixel.

    uv run --with pillow python infra/tabs/compare_shots.py <dir>

`.claude/shtml_free_tabs_design.md` §6 item 4. The markup changes by design,
so this is not expected to be a zero-pixel match; what it answers is WHERE the
page differs and by how much, so a difference can be judged instead of
guessed at from a screenshot pair by eye.

Writes a diff image highlighting the changed rows.
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageChops


def load(path: Path) -> Image.Image:
    return Image.open(path).convert('RGB')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    parser.add_argument('--tolerance', type=int, default=8,
                        help='per-channel difference treated as noise')
    parser.add_argument('--region', action='store_true',
                        help='compare the widget shots instead of the whole '
                             'pages - the two host pages have different '
                             'titles, so a page shot can never match')
    options = parser.parse_args()

    directory = Path(options.directory)
    suffix = '' if options.region else '-page'
    before = sorted(directory.glob(f'*-before{suffix}.png'))
    after = sorted(directory.glob(f'*-after{suffix}.png'))
    if not before or not after:
        raise SystemExit(f'need *-before{suffix}.png and *-after{suffix}.png '
                         f'in {directory}')

    first, second = load(before[0]), load(after[0])
    print(f'before {first.size}   after {second.size}')

    if first.size != second.size:
        # Not a failure by itself: a different element height changes the page
        # height. Compare the overlapping region and say so.
        width = min(first.width, second.width)
        height = min(first.height, second.height)
        print(f'sizes differ - comparing the top-left {width}x{height}')
        first = first.crop((0, 0, width, height))
        second = second.crop((0, 0, width, height))

    difference = ImageChops.difference(first, second)
    mask = difference.convert('L').point(
        lambda value: 255 if value > options.tolerance else 0)
    box = mask.getbbox()

    changed = sum(1 for pixel in mask.getdata() if pixel)
    total = mask.width * mask.height
    print(f'differing pixels: {changed} of {total} '
          f'({100 * changed / total:.2f}%)')

    if box is None:
        print('IDENTICAL within tolerance')
        return

    print(f'changed region: left={box[0]} top={box[1]} '
          f'right={box[2]} bottom={box[3]}')

    rows = []
    for y in range(mask.height):
        row = mask.crop((0, y, mask.width, y + 1))
        if row.getbbox():
            rows.append(y)
    if rows:
        print(f'changed rows: {rows[0]}..{rows[-1]} ({len(rows)} rows)')

    out = directory / 'diff.png'
    highlighted = second.copy()
    highlighted.paste(Image.new('RGB', mask.size, (255, 0, 0)), (0, 0), mask)
    highlighted.save(out)
    print(f'diff image: {out}')


if __name__ == '__main__':
    main()
