"""The rendered games list of season pages, captured before a change and
compared byte for byte after it.

    uv run python infra/season_pages/compare_games_list.py capture before     # all seasons
    (edit תבנית:כדורגל/רשימת משחקים/הצגת משחק)
    uv run python infra/season_pages/compare_games_list.py capture after
    uv run python infra/season_pages/compare_games_list.py diff before after

PRODUCTION ONLY. The local wiki resolves files through production's API,
uncached, and a games list checks up to 39 file names per ticket - one local
capture held ~550 open connections to production. Production calls here are
paced (season_api.py).

The icon change touches only the three icon tests in each game row; if their
answers agree, the games list must come out byte-identical. Renders the
list's own template with action=parse&text= - uncached, nothing saved - so
both captures are real renders and none compares the parser cache with
itself. Each capture records which row template it rendered, and diff refuses
unless "before" used the galleries and "after" did not: a capture taken
before the edit landed would otherwise pass by comparing a page with itself.
A diff taken while the current season changes (a new game, a press upload)
fails for that reason - look before calling it a regression.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from season_api import call

OUT = Path('.claude/tmp/games-list')
TEXT = ('{{#vardefine:עונה להצגה|%s}}'
        '{{כדורגל/רשימת משחקים/הצגה לפי מפעל |עונה=%s }}')
GALLERY = 'הצגת גלריה לפי קטגוריה'
TEMPLATE_NAMESPACE = 10


def api(params: dict, post: bool = False) -> dict:
    return call('prod', params, post)  # paced, with 508 back-off


def seasons_with_games() -> list[str]:
    data = api({'action': 'cargoquery', 'tables': 'Football_Games', 'fields': 'Season',
                'group_by': 'Season', 'limit': '500'})
    return sorted(row['title']['Season'] for row in data['cargoquery'])


def capture(label: str, seasons: list[str]) -> None:
    if not seasons:
        raise SystemExit('no seasons to capture - refusing to capture nothing')
    folder = OUT / label
    shutil.rmtree(folder, ignore_errors=True)  # never mix with an earlier run's files
    folder.mkdir(parents=True)
    used_gallery = {}
    for season in seasons:
        parsed = api({'action': 'parse', 'title': f'עונת {season}',
                      'text': TEXT % (season, season), 'contentmodel': 'wikitext',
                      'prop': 'text|templates', 'disablelimitreport': 1}, post=True)['parse']
        html = parsed['text']
        if 'games-list-game-container' not in html:
            raise SystemExit(f'{season}: no game rows rendered - refusing to capture nothing')
        name = season.replace('/', '-')
        (folder / f'{name}.html').write_text(html, encoding='utf-8')
        used_gallery[name] = any(page['ns'] == TEMPLATE_NAMESPACE
                                 and page['title'].split(':', 1)[-1] == GALLERY
                                 for page in parsed.get('templates', []))
        print(f'  {season}: {html.count("games-list-game-container")} games', flush=True)
    (folder / 'used_gallery.json').write_text(json.dumps(used_gallery), encoding='utf-8')


def diff(before: str, after: str) -> int:
    first, second = OUT / before, OUT / after
    names = sorted(path.name for path in first.glob('*.html'))
    if not names:
        raise SystemExit(f'nothing captured under {first}')
    old_rows, new_rows = (json.loads((folder / 'used_gallery.json').read_text(encoding='utf-8'))
                          for folder in (first, second))
    if not all(old_rows.values()) or any(new_rows.values()):
        raise SystemExit(f'"{before}" must render the gallery row template and "{after}" '
                         'must not - the edit has not landed, or the captures are swapped')
    differing = 0
    for name in names:
        other = second / name
        if not other.exists():
            raise SystemExit(f'{name} captured {before} but not {after}')
        old, new = (path.read_text(encoding='utf-8') for path in (first / name, other))
        if old != new:
            differing += 1
            # First differing character; if one is a prefix of the other, where it ends.
            at = next((i for i, (a, b) in enumerate(zip(old, new)) if a != b),
                      min(len(old), len(new)))
            print(f'DIFFERS {name}\n  {before}: …{old[max(0, at - 120):at + 120]!r}\n'
                  f'  {after}: …{new[max(0, at - 120):at + 120]!r}')
    print(f'\n{len(names) - differing}/{len(names)} seasons byte-identical')
    return 1 if differing else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['capture', 'diff'])
    parser.add_argument('labels', nargs='+', help='capture: LABEL [SEASON…]; diff: BEFORE AFTER')
    options = parser.parse_args()

    if options.command == 'capture':
        label, *seasons = options.labels
        capture(label, seasons or seasons_with_games())
        return
    if len(options.labels) != 2:
        parser.error('diff takes BEFORE AFTER')
    sys.exit(diff(*options.labels))


if __name__ == '__main__':
    main()
