"""Screenshot wiki pages on the local wiki, logged out, at two widths.

    uv run --with playwright python infra/visual_diff/shoot.py --out DIR TITLE...

Writes DIR/<slug>-<viewport>.png for every title and viewport, plus
DIR/shots.json mapping each file to its title and viewport. Animations are
frozen so two shots of an unchanged page match pixel for pixel.
"""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

BASE = 'http://localhost:8080'
VIEWPORTS = {'desktop': (1280, 900), 'mobile': (390, 844)}
# Long pages are cut here: a full season-length page would make a PNG nobody
# can read in a PR comment.
MAX_HEIGHT = 6000


def slug_of(title: str) -> str:
    """A filename-safe, stable name for a title (Hebrew kept, rest replaced)."""
    return re.sub(r'[^\w֐-׿-]+', '_', title).strip('_')[:80]


def shoot(titles: list[str], out: Path) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    shots = []
    with sync_playwright() as runner:
        browser = runner.chromium.launch()
        for viewport, (width, height) in VIEWPORTS.items():
            page = browser.new_page(viewport={'width': width, 'height': height})
            for title in titles:
                url = f'{BASE}/{quote(title.replace(" ", "_"))}'
                response = page.goto(url, wait_until='networkidle', timeout=90000)
                status = response.status if response else 0
                page.wait_for_timeout(500)
                full_height = page.evaluate('document.documentElement.scrollHeight')
                name = f'{slug_of(title)}-{viewport}.png'
                page.screenshot(
                    path=str(out / name), animations='disabled', caret='hide',
                    clip={'x': 0, 'y': 0, 'width': width,
                          'height': min(full_height, MAX_HEIGHT)},
                    full_page=True)
                shots.append({'file': name, 'title': title, 'viewport': viewport,
                              'status': status, 'height': full_height})
                print(f'  {viewport:7} {status} {title}')
            page.close()
        browser.close()
    (out / 'shots.json').write_text(json.dumps(shots, ensure_ascii=False, indent=1),
                                    encoding='utf-8')
    return shots


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('titles', nargs='+')
    options = parser.parse_args()
    shoot(options.titles, options.out)


if __name__ == '__main__':
    main()
