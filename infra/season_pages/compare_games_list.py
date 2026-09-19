"""The rendered games list of season pages, captured before a change and
compared byte for byte after it.

    uv run python infra/season_pages/compare_games_list.py capture before --wiki local 1939 1966/68
    uv run python infra/season_pages/compare_games_list.py capture after  --wiki local 1939 1966/68
    uv run python infra/season_pages/compare_games_list.py diff before after --wiki local

    uv run python infra/season_pages/compare_games_list.py capture before --wiki prod   # all seasons

The icon change touches only the three icon tests in each game row; if their
answers agree, the games list must come out byte-identical. Renders the
list's own template with action=parse&text= - uncached, nothing saved - so
both captures are real renders and none compares the parser cache with
itself.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

WIKIS = {'local': 'http://localhost:8080/api.php',
         'prod': 'https://www.maccabipedia.co.il/api.php'}
UA = {'User-Agent': 'MaccabipediaBot/games-list (infra/season_pages)'}
OUT = Path('.claude/tmp/games-list')
TEXT = ('{{#vardefine:עונה להצגה|%s}}'
        '{{כדורגל/רשימת משחקים/הצגה לפי מפעל |עונה=%s }}')
PROD_PAUSE_SECONDS = 1.0


def api(wiki: str, params: dict, post: bool = False) -> dict:
    params = dict(params, format='json', formatversion='2')
    body = urllib.parse.urlencode(params).encode('utf-8')
    url = WIKIS[wiki]
    request = (urllib.request.Request(url, data=body, headers=UA) if post else
               urllib.request.Request(f'{url}?{body.decode()}', headers=UA))
    with urllib.request.urlopen(request, timeout=300) as response:
        data = json.loads(response.read().decode('utf-8'))
    if 'error' in data:
        raise SystemExit(f'{wiki} API error: {data["error"]}')
    if wiki == 'prod':
        time.sleep(PROD_PAUSE_SECONDS)
    return data


def seasons_with_games(wiki: str) -> list[str]:
    data = api(wiki, {'action': 'cargoquery', 'tables': 'Football_Games', 'fields': 'Season',
                      'group_by': 'Season', 'limit': '500'})
    return sorted(row['title']['Season'] for row in data['cargoquery'])


def capture(wiki: str, label: str, seasons: list[str]) -> None:
    folder = OUT / wiki / label
    folder.mkdir(parents=True, exist_ok=True)
    for season in seasons:
        html = api(wiki, {'action': 'parse', 'title': f'עונת {season}',
                          'text': TEXT % (season, season), 'contentmodel': 'wikitext',
                          'prop': 'text', 'disablelimitreport': 1}, post=True)['parse']['text']
        if 'games-list-game-container' not in html:
            raise SystemExit(f'{season}: no game rows rendered - refusing to capture nothing')
        (folder / f'{season.replace("/", "-")}.html').write_text(html, encoding='utf-8')
        print(f'  {season}: {html.count("games-list-game-container")} games', flush=True)


def diff(wiki: str, before: str, after: str) -> int:
    first, second = OUT / wiki / before, OUT / wiki / after
    names = sorted(path.name for path in first.glob('*.html'))
    if not names:
        raise SystemExit(f'nothing captured under {first}')
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
    parser.add_argument('--wiki', choices=sorted(WIKIS), required=True)
    options = parser.parse_intermixed_args()  # seasons may follow --wiki

    if options.command == 'capture':
        label, *seasons = options.labels
        capture(options.wiki, label, seasons or seasons_with_games(options.wiki))
        return
    if len(options.labels) != 2:
        parser.error('diff takes BEFORE AFTER')
    sys.exit(diff(options.wiki, *options.labels))


if __name__ == '__main__':
    main()
