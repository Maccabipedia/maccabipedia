"""The games-list media icons: today's gallery test against a cheaper check,
for every game of every football season, on production. Read-only.

    uv run python infra/season_pages/compare_game_icons.py            # all seasons
    uv run python infra/season_pages/compare_game_icons.py 1966/68 2024/25
    uv run python infra/season_pages/compare_game_icons.py --selftest

Each game row in תבנית:כדורגל/רשימת משחקים/הצגת משחק decides three icons -
programme, press, photos - by rendering a whole DPL <gallery> of a category
and testing only whether it came out non-empty. The candidate asks the
category table for its size instead. This renders both tests, side by side,
for all three categories of every game (one action=parse&text= per season,
nothing saved) and requires the same answer everywhere.

--selftest compares one season's games against another season's categories
and must FAIL: a comparison that cannot fail proves nothing.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request

API = 'https://www.maccabipedia.co.il/api.php'
UA = {'User-Agent': 'MaccabipediaBot/game-icons (infra/season_pages)'}
PAUSE_SECONDS = 1.0

OLD = '{{{{#תנאי: {{{{הצגת גלריה לפי קטגוריה |שם קטגוריה={category} |אין תוצאות=}}}} |1|0}}}}'
NEW = '{{{{#ifexpr: {{{{PAGESINCATEGORY:{category}|all|R}}}} > 0 |1|0}}}}'
# Placeholder for the media date the row template computes; replaced per game.
MEDIA = '{media date}'
# The three categories, exactly as the row template names them.
CATEGORIES = {
    'programme': '{page}/תוכניית משחק',
    'press': 'עיתונות למשחק מה-' + MEDIA,
    'photos': '{page}/תמונות',
}


def api(params: dict, post: bool = False) -> dict:
    params = dict(params, format='json', formatversion='2')
    body = urllib.parse.urlencode(params).encode('utf-8')
    request = (urllib.request.Request(API, data=body, headers=UA) if post else
               urllib.request.Request(f'{API}?{body.decode()}', headers=UA))
    with urllib.request.urlopen(request, timeout=300) as response:
        data = json.loads(response.read().decode('utf-8'))
    if 'error' in data:
        raise SystemExit(f'API error: {data["error"]}')
    return data


def seasons() -> list[str]:
    data = api({'action': 'cargoquery', 'tables': 'Football_Games', 'fields': 'Season',
                'group_by': 'Season', 'limit': '500'})
    return sorted(row['title']['Season'] for row in data['cargoquery'])


def games(season: str) -> list[tuple[str, str]]:
    data = api({'action': 'cargoquery', 'tables': 'Football_Games',
                'fields': '_pageName=Page,Date', 'where': f'Season="{season}"',
                'limit': '500'})
    if 'cargoquery' not in data:
        raise SystemExit(f'cargoquery failed for {season}: {data}')
    return [(row['title']['Page'].replace('&quot;', '"'), row['title']['Date'])
            for row in data['cargoquery']]


def media_date(date: str) -> str:
    return f'{{{{#time:d "ב"F Y|{date} }}}}'


def answers(season: str, rows: list[tuple[str, str]],
            shift: int = 0) -> list[dict[str, tuple[str, str]]]:
    """Per game, per icon: (old answer, new answer), each '1' or '0'.

    shift > 0 makes the NEW side read the categories of the game `shift` rows
    later - only for --selftest, which needs answers that must disagree.
    """
    lines = []
    for index, (page, date) in enumerate(rows):
        other_page, other_date = rows[(index + shift) % len(rows)]
        cells = []
        for pattern in CATEGORIES.values():
            old = pattern.replace('{page}', page).replace(MEDIA, media_date(date))
            new = pattern.replace('{page}', other_page).replace(MEDIA, media_date(other_date))
            cells += [OLD.format(category=old), NEW.format(category=new)]
        lines.append('ROW[' + ','.join(cells) + ']')
    data = api({'action': 'parse', 'title': f'עונת {season}', 'text': '\n'.join(lines),
                'contentmodel': 'wikitext', 'prop': 'text', 'disablelimitreport': 1},
               post=True)
    time.sleep(PAUSE_SECONDS)
    rendered = re.findall(r'ROW\[([01,\s]*)\]', data['parse']['text'])
    if len(rendered) != len(rows):
        raise SystemExit(f'{season}: {len(rows)} games but {len(rendered)} rendered rows')
    result = []
    for cells in rendered:
        values = [value.strip() for value in cells.split(',')]
        if len(values) != 2 * len(CATEGORIES) or set(values) - {'0', '1'}:
            raise SystemExit(f'{season}: unreadable row {cells!r}')
        result.append({icon: (values[2 * i], values[2 * i + 1])
                       for i, icon in enumerate(CATEGORIES)})
    return result


def compare(season: str, rows: list[tuple[str, str]],
            shift: int = 0) -> tuple[int, dict[str, int], list[str]]:
    shown = dict.fromkeys(CATEGORIES, 0)
    disagreements = []
    for (page, _), icons in zip(rows, answers(season, rows, shift)):
        for icon, (old, new) in icons.items():
            shown[icon] += old == '1'
            if old != new:
                disagreements.append(f'{page}: {icon} today {old}, candidate {new}')
    return len(rows), shown, disagreements


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('seasons', nargs='*')
    parser.add_argument('--selftest', action='store_true')
    options = parser.parse_args()

    if options.selftest:
        # 2021/22: press on 2 of its 59 games - so each game's candidate,
        # reading the NEXT game's categories, must disagree somewhere.
        _, _, disagreements = compare('2021/22', games('2021/22'), shift=1)
        print(f'selftest: candidate reads the next game\'s categories -> '
              f'{len(disagreements)} disagreements (must be > 0)')
        sys.exit(0 if disagreements else 1)

    total_games, total_shown, failures = 0, dict.fromkeys(CATEGORIES, 0), []
    for season in options.seasons or seasons():
        count, shown, disagreements = compare(season, games(season))
        total_games += count
        for icon in CATEGORIES:
            total_shown[icon] += shown[icon]
        failures += [f'{season} {line}' for line in disagreements]
        for line in disagreements:
            print(f'DIFFERS {season} {line}', flush=True)
    print(f'\n{total_games} games, {3 * total_games} icon checks; icons shown today: '
          f'{total_shown}; disagreements: {len(failures)}')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
