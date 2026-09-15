"""Render both versions of a strip on ONE page, and compare the two regions.

    uv run --with playwright --with pillow python \
        infra/tabs/compare_on_one_page.py 'תבנית:…'

Two separate host pages cannot be compared pixel for pixel: their titles
differ, so everything below sits a couple of pixels apart and every glyph
rasterises against a different sub-pixel phase. The layout can be identical
and the screenshots still differ by 2-3% of pixels, which says nothing.

One page holding both versions removes that variable: same viewport, same
fonts, same phase. What remains is a real difference.
"""
import argparse
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

sys.path.insert(0, 'infra/tabs')

from verify_tabs import SANDBOX_SUFFIX, write_local  # noqa: E402

BASE = 'http://localhost:8080'
HOST = 'ארגז חול/טאבים/זה מול זה'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('title')
    parser.add_argument('--out', default='/tmp/tab-shots/one-page')
    parser.add_argument('--parameters', default='')
    parser.add_argument('--tolerance', type=int, default=8)
    options = parser.parse_args()

    out = Path(options.out)
    out.mkdir(parents=True, exist_ok=True)

    original = options.title.removeprefix('תבנית:')
    converted = original + SANDBOX_SUFFIX
    write_local(HOST, '{{%s%s}}\n\n{{%s%s}}' % (
        original, options.parameters, converted, options.parameters))

    with sync_playwright() as runner:
        browser = runner.chromium.launch()
        page = browser.new_page(viewport={'width': 1100, 'height': 1400},
                                device_scale_factor=2)
        page.goto(f'{BASE}/{quote(HOST.replace(" ", "_"))}',
                  wait_until='networkidle')
        page.wait_for_timeout(600)

        before = page.locator('#tab1-content').first
        after = page.locator('.tabber__panel').first
        if not before.count() or not after.count():
            raise SystemExit('one of the two versions did not render - is the '
                             'sandbox page present?')

        before.screenshot(path=str(out / 'panel-before.png'))
        after.screenshot(path=str(out / 'panel-after.png'))

        strip_before = page.locator('.slim-tabs ul').first
        strip_after = page.locator('.tabber__tabs').first
        strip_before.screenshot(path=str(out / 'strip-before.png'))
        strip_after.screenshot(path=str(out / 'strip-after.png'))
        browser.close()

    for label in ('panel', 'strip'):
        first = Image.open(out / f'{label}-before.png').convert('RGB')
        second = Image.open(out / f'{label}-after.png').convert('RGB')
        print(f'=== {label}: {first.size} vs {second.size}')
        if first.size != second.size:
            width, height = (min(first.width, second.width),
                             min(first.height, second.height))
            first = first.crop((0, 0, width, height))
            second = second.crop((0, 0, width, height))
            print(f'    sizes differ - comparing {width}x{height}')

        mask = ImageChops.difference(first, second).convert('L').point(
            lambda value: 255 if value > options.tolerance else 0)
        changed = sum(1 for pixel in mask.getdata() if pixel)
        total = mask.width * mask.height
        print(f'    differing: {changed} of {total} '
              f'({100 * changed / total:.2f}%)  bbox={mask.getbbox()}')

        if mask.getbbox():
            highlighted = second.copy()
            highlighted.paste(Image.new('RGB', mask.size, (255, 0, 0)),
                              (0, 0), mask)
            highlighted.save(out / f'{label}-diff.png')


if __name__ == '__main__':
    main()
