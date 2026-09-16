"""Screenshot a strip before and after conversion, on the local wiki.

    uv run --with playwright python infra/tabs/screenshot_pair.py \
        'תבנית:כדורסל/סטטיסטיקה/שיאני נקודות' --out /tmp/shots

Writes the two host pages (via make_host_pages) and saves four PNGs: the strip
region and the whole page, before and after. This is the visual half of
`.claude/shtml_free_tabs_design.md` §6 item 4 - the part no HTML comparison
can answer, because the markup is meant to differ.
"""
import argparse
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

BASE = 'http://localhost:8080'
BEFORE_PAGE = 'ארגז חול/טאבים/לפני'
AFTER_PAGE = 'ארגז חול/טאבים/אחרי'

# The wrapper a strip sits in, so the shot is the widget rather than the page.
REGIONS = ('.records-list-tabs-container', '.tabber-converted', '.tabber',
           '.slim-tabs', '.mw-parser-output')


def url_of(title: str) -> str:
    return f'{BASE}/{quote(title.replace(" ", "_"))}'


def shoot(page, path: Path, label: str) -> None:
    page.wait_for_timeout(600)
    page.screenshot(path=str(path.with_name(path.name.replace(
        '.png', '-page.png'))), full_page=True)

    for selector in REGIONS:
        region = page.locator(selector).first
        if region.count() and region.is_visible():
            region.screenshot(path=str(path))
            print(f'  {label}: {selector} -> {path.name}')
            return
    print(f'  {label}: no region matched, page shot only')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('title')
    parser.add_argument('--out', default='/tmp/tab-shots')
    parser.add_argument('--parameters', default='')
    parser.add_argument('--converted', default='',
                        help='the converted template, when it is not the '
                             'original plus the sandbox suffix')
    options = parser.parse_args()

    out = Path(options.out)
    out.mkdir(parents=True, exist_ok=True)

    hosts = subprocess.run(
        [sys.executable, 'infra/tabs/make_host_pages.py', options.title,
         '--parameters', options.parameters,
         '--converted', options.converted],
        capture_output=True, text=True)
    if hosts.returncode != 0:
        raise SystemExit(hosts.stderr[:400])

    stem = options.title.split('/')[-1].replace(' ', '-')
    with sync_playwright() as runner:
        browser = runner.chromium.launch()
        page = browser.new_page(viewport={'width': 1100, 'height': 900},
                                device_scale_factor=2)

        page.goto(url_of(BEFORE_PAGE), wait_until='networkidle')
        shoot(page, out / f'{stem}-before.png', 'before')

        page.goto(url_of(AFTER_PAGE), wait_until='networkidle')
        shoot(page, out / f'{stem}-after.png', 'after')

        browser.close()

    print(f'\nsaved under {out}')


if __name__ == '__main__':
    main()
