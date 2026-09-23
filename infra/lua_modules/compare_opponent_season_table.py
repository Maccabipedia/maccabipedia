"""Old opponent season tables against Module:FootballSeasonTable, on production.

    uv run python infra/lua_modules/compare_opponent_season_table.py --sandbox
    uv run python infra/lua_modules/compare_opponent_season_table.py --sandbox --selftest
    uv run python infra/lua_modules/compare_opponent_season_table.py --full

READ-ONLY, paced (season_api). Per opponent page:

--sandbox (before publishing): the table alone. Both sides first run the
opponent template's own preamble with the page's parameters (so both read the
same יריבות לשליפה); OLD then calls the live table template, NEW the
candidate table body with Module:FootballSeasonTable overridden by the repo
file - the only new page, so one override per request is enough.
--full (after publishing): the whole page with the table template overridden
by the candidate; everything outside the table byte-identical.

The table is checked three ways:
  1. NEW against a direct Cargo query written here, apart from the module:
     the same (season, competition) rows, each with the same wins, draws and
     losses - and the same season sequence the database orders by.
  2. NEW's order inside a season against a sort written here: league, cup,
     the rest, then the name, from the catalogue fetched here.
  3. OLD against NEW. The decided departures and nothing else: every row
     (OLD was cut at Cargo's 100 - a page whose direct count is 100 or more
     must have OLD ⊂ NEW, otherwise the same rows); the order inside a season;
     and the rows of a competition with no catalogue row (ידידות, גביע
     מלצ'ט), which OLD showed as 0/0/0. The season and competition links
     must agree.
--selftest compares one club's OLD with another's NEW and must FAIL.
"""
from __future__ import annotations

import argparse
import html as html_module
import re
import sys
from collections import Counter
from pathlib import Path

import mwparserfromhell

sys.path.insert(0, str(Path('infra/lua_modules')))
sys.path.insert(0, str(Path('infra/season_pages')))
import compare_stadium_leaderboards as common  # noqa: E402
from season_api import call  # noqa: E402

# Both sports' opponent pages carry the same widget, so the gate is the same; only
# these differ. Basketball has no draw, hence two result columns, and its season and
# competition pages live in the כדורסל: namespace. Both wrappers finish their opponent
# list before the same `#vardefine: כמות משחקים רשמיים`, so PREAMBLE is shared.
SPORTS = {
    'football': {
        'page_template': 'תבנית:יריבת כדורגל',
        'table_template': 'תבנית:יריבת כדורגל/הצגת סטטיסטיקה עונתית',
        'module_page': 'Module:FootballSeasonTable',
        'module_file': Path('infra/lua_modules/Module_FootballSeasonTable.lua'),
        'invoke': '{{#invoke:FootballSeasonTable|rows|יריבות={{{יריבות לשליפה|}}}}}',
        'games': 'Football_Games',
        'catalogue': 'Competitions',
        # (name, SQL) per result column, in the table's order.
        'results': [('w', 'SUM(ResultOpt=1)'), ('d', 'SUM(ResultOpt=2)'), ('l', 'SUM(ResultOpt=3)')],
        'uncatalogued': {'ידידות', "גביע מלצ'ט"},
        'selftest_pair': ('הפועל תל אביב', 'מכבי חיפה'),
        'namespace': 0,
        'skip': set(),
        'layer': [('Module:FootballQueries', 'Module_FootballQueries.lua'),
                  ('Module:FootballQueries/Fields', 'Module_FootballQueries_Fields.lua')],
    },
    'basketball': {
        'page_template': 'תבנית:יריבת כדורסל',
        'table_template': 'תבנית:יריבת כדורסל/הצגת סטטיסטיקה עונתית',
        'module_page': 'Module:BasketballSeasonTable',
        'module_file': Path('infra/lua_modules/Module_BasketballSeasonTable.lua'),
        'invoke': '{{#invoke:BasketballSeasonTable|rows|יריבות={{{יריבות לשליפה|}}}}}',
        'games': 'Basketball_Games',
        'catalogue': 'Basketball_Competitions',
        'results': [('w', 'SUM(ResultOpt=1)'), ('l', 'SUM(ResultOpt=3)')],
        # Filled from the catalogue at run time: whichever competitions the pages
        # show that the catalogue does not list.
        'uncatalogued': set(),
        'selftest_pair': ('כדורסל:הפועל תל אביב', 'כדורסל:מכבי חיפה'),
        'namespace': 3003,
        # A scratch page in the main namespace, not an opponent.
        'skip': {'נסיון'},
        'layer': [('Module:BasketballQueries', 'Module_BasketballQueries.lua'),
                  ('Module:BasketballQueries/Fields', 'Module_BasketballQueries_Fields.lua')],
    },
}
SPORT = SPORTS['football']
CARGO_QUERY = re.compile(r'\{\{#cargo_query:.*?\n\}\}', re.S)
PREAMBLE = re.compile(r'<includeonly>(.*?)<!--\s*-->\{\{#vardefine: כמות משחקים רשמיים', re.S)
LIST_SEPARATOR = '@@name@@'
# From the table body to whatever follows the section; ROW then reads every
# complete row in it (a tighter end - three closing divs - cut the last row).
TABLE = re.compile(r'<div class="title">סטטיסטיקה עונתית</div>.*?<div class="table-content">(.*?)'
                   r'(?=<div class="players-records-container"|<div class="games-records-container"|\Z)', re.S)
ROW = re.compile(r'<div class="table-row">(.*?)</div>', re.S)
SPAN = re.compile(r'<span>(.*?)</span>', re.S)
LINK = re.compile(r'<a [^>]*title="([^"]*)"[^>]*>(.*?)</a>', re.S)
LEAGUE, CUP, OTHER = 1, 2, 3


def candidate_of(body: str) -> str:
    if len(CARGO_QUERY.findall(body)) != 1:
        raise SystemExit('the table template does not hold exactly one #cargo_query - refusing')
    return CARGO_QUERY.sub(lambda _: SPORT['invoke'], body)


def opponent_pages() -> list[str]:
    """Every page that shows the table, in the sport's own namespace.

    Football's opponents are articles (ns 0); basketball's live in `כדורסל:`
    (ns 3003). A page anywhere else is refused rather than quietly gated, unless
    the sport names it as a known scratch page - so a template that starts being
    used somewhere new cannot slip past.
    """
    titles, cont = [], {}
    while True:
        data = call('prod', dict({'action': 'query', 'list': 'embeddedin', 'eititle': SPORT['table_template'],
                                  'eilimit': 'max'}, **cont))
        titles += [(row['ns'], row['title']) for row in data['query']['embeddedin']]
        if 'continue' not in data:
            break
        cont = data['continue']
    elsewhere = [title for ns, title in titles
                 if ns != SPORT['namespace'] and title not in SPORT['skip']]
    if elsewhere:
        raise SystemExit(f'the table template is used outside {SPORT["namespace"]}: {elsewhere[:5]}')
    skipped = [title for ns, title in titles if title in SPORT['skip']]
    if skipped:
        print(f'skipping {len(skipped)} known scratch page(s): {skipped}')
    return sorted(title for ns, title in titles if ns == SPORT['namespace'])


def preamble_for(page_body: str, page_wikitext: str) -> str:
    match = PREAMBLE.search(page_body)
    if not match:
        raise SystemExit('the opponent template\'s preamble moved - refusing')
    wrapper = SPORT['page_template'].split(':', 1)[1]
    calls = [node for node in mwparserfromhell.parse(page_wikitext).filter_templates()
             if node.name.strip() in (wrapper, SPORT['page_template'])]
    if len(calls) != 1:
        raise ValueError(f'{len(calls)} calls of the opponent template on the page')
    given = {str(param.name).strip(): str(param.value).strip() for param in calls[0].params}
    preamble = mwparserfromhell.parse(match.group(1))
    for argument in preamble.filter_arguments(recursive=True):
        name = str(argument.name).strip()
        value = given.get(name, str(argument.default) if argument.default is not None else str(argument))
        preamble.replace(argument, value)
    text = str(preamble)
    if '#arraydefine: יריבות לשליפה' not in text:
        raise SystemExit('the preamble no longer defines יריבות לשליפה - refusing')
    return text


def opponent_names(title: str, preamble: str) -> list[str]:
    data = call('prod', {'action': 'expandtemplates', 'title': title, 'prop': 'wikitext', 'text':
                         preamble + '{{#arrayprint: יריבות לשליפה|' + LIST_SEPARATOR + '}}'}, post=True)
    names = [html_module.unescape(name).strip()
             for name in data['expandtemplates']['wikitext'].split(LIST_SEPARATOR)]
    names = [name for name in names if name]
    if not names or any('{{{' in name for name in names):
        raise ValueError(f'the opponent list is {names!r}')
    return names


def direct_rows(names: list[str]) -> list[tuple]:
    """(season, competition, *results) straight from Cargo, in the database's
    Season DESC order - written apart from the module."""
    literals = ', '.join('"' + name.replace("'", '').replace('"', '') + '"' for name in names)
    results = ', '.join(f'{sql}={key}' for key, sql in SPORT['results'])
    data = call('prod', {'action': 'cargoquery', 'tables': SPORT['games'],
                         # A comparison sums as 0/1; no game has a NULL ResultOpt
                         # (measured 2026-09-22), and it differs from the module's CASE.
                         'fields': f'Season=s, Competition=c, COUNT(*)=n, {results}',
                         'where': f'Opponent IN ({literals})', 'group_by': 'Season, Competition',
                         'order_by': 'Season DESC', 'limit': '2000'})
    rows = [row['title'] for row in data['cargoquery']]
    if len(rows) >= 2000:
        raise ValueError('the direct query reached its limit')
    return [(html_module.unescape(r['s']), html_module.unescape(r['c']),
             *(int(float(r[key])) for key, _ in SPORT['results'])) for r in rows]


def catalogue_ranks() -> dict:
    data = call('prod', {'action': 'cargoquery', 'tables': SPORT['catalogue'],
                         'fields': 'OriginalName=n, League=l, Trophy=t', 'limit': '500'})
    return {html_module.unescape(r['title']['n']): LEAGUE if r['title']['l'] == '1' else
            CUP if r['title']['t'] == '1' else OTHER for r in data['cargoquery']}


def uncatalogued_competitions() -> set:
    """The competitions games are played in that the catalogue does not list.

    The OLD template counted each row THROUGH the catalogue, so these showed as
    zeroes; the module counts from the games and shows the real numbers. That is a
    decided departure, and `check` allows it only for these competitions - so the
    set has to be the data's, not a list written down once.
    """
    data = call('prod', {'action': 'cargoquery', 'tables': SPORT['games'],
                         'fields': 'Competition=c', 'group_by': 'Competition',
                         'limit': '500'})
    played = {html_module.unescape(row['title']['c']) for row in data['cargoquery']}
    if len(data['cargoquery']) >= 500:
        raise SystemExit('the competition list reached its limit - refusing')
    return played - set(catalogue_ranks())


def table_rows(page: str) -> list[dict]:
    tables = TABLE.findall(page)
    if len(tables) != 1:
        raise ValueError(f'{len(tables)} season tables on the page')
    rows = []
    for body in ROW.findall(tables[0]):
        spans = SPAN.findall(body)
        if len(spans) != 2 + len(SPORT['results']):
            raise ValueError(f'a row with {len(spans)} cells: {body[:120]}')
        cells = []
        for span in spans[:2]:
            link = LINK.search(span)
            text = html_module.unescape(re.sub(r'<[^>]+>', '', span)).strip()
            cells.append((text, html_module.unescape(link.group(1)) if link else None))
        rows.append({'season': cells[0][0], 'season_link': cells[0][1],
                     'competition': cells[1][0], 'competition_link': cells[1][1],
                     'results': tuple(int(re.sub(r'<[^>]+>', '', span).strip() or 0) for span in spans[2:])})
    return rows


def check(old: list[dict], new: list[dict], direct: list[tuple], ranks: dict) -> tuple[str, str]:
    key = lambda row: (row['season'], row['competition'])  # noqa: E731
    # 1. NEW against the direct query.
    direct_map = {(row[0], row[1]): tuple(row[2:]) for row in direct}
    new_map = {key(row): row['results'] for row in new}
    if len(new_map) != len(new):
        return 'FAIL', 'NEW repeats a (season, competition) row'
    if new_map != direct_map:
        missing = sorted(set(direct_map) - set(new_map))[:3]
        extra = sorted(set(new_map) - set(direct_map))[:3]
        wrong = [k for k in direct_map if k in new_map and new_map[k] != direct_map[k]][:3]
        return 'FAIL', f'NEW vs Cargo: missing {missing} extra {extra} wrong {wrong}'
    seasons = lambda rows: [s for i, s in enumerate(rows) if i == 0 or s != rows[i - 1]]  # noqa: E731
    if seasons([row['season'] for row in new]) != seasons([s for s, *_ in direct]):
        return 'FAIL', 'NEW season sequence differs from the database order'
    # 2. The order inside each season.
    for season in {row['season'] for row in new}:
        inside = [row['competition'] for row in new if row['season'] == season]
        if inside != sorted(inside, key=lambda c: (ranks.get(c, OTHER), c)):
            return 'FAIL', f'{season}: order {inside}'
    # 3. OLD against NEW.
    truncated = len(direct) >= 100
    old_keys, new_keys = Counter(map(key, old)), Counter(map(key, new))
    if truncated:
        if len(old) != 100 or old_keys - new_keys:
            return 'FAIL', f'truncated page: OLD {len(old)} rows, not all in NEW'
    elif old_keys != new_keys:
        return 'FAIL', (f'rows: only OLD {sorted(old_keys - new_keys)[:3]}, '
                        f'only NEW {sorted(new_keys - old_keys)[:3]}')
    new_by_key = {key(row): row for row in new}
    for row in old:
        other = new_by_key[key(row)]
        for field in ('season_link', 'competition_link'):
            if row[field] != other[field]:
                return 'FAIL', f'{key(row)} {field}: {row[field]!r} vs {other[field]!r}'
        if row['results'] != other['results']:
            if (row['competition'] in SPORT['uncatalogued']
                    and set(row['results']) == {0}):
                continue
            return 'FAIL', f'{key(row)} results {row["results"]} vs {other["results"]}'
    return 'ok', f'{len(new)} rows' + (f' ({len(new) - len(old)} added)' if truncated else '')


def module_override() -> dict:
    return {'templatesandboxtitle': SPORT['module_page'],
            'templatesandboxtext': SPORT['module_file'].read_text(encoding='utf-8'),
            'templatesandboxcontentmodel': 'Scribunto'}


def check_prod_modules(sandbox: bool) -> None:
    """The layer the module calls must be the repo's; the module itself must
    not be on production yet (--sandbox) or must be the repo's (--full)."""
    for page, name in SPORT['layer']:
        repo = (Path('infra/lua_modules') / name).read_text(encoding='utf-8').strip()
        if common.page_text(page).strip() != repo:
            raise SystemExit(f'{page} on production differs from the repo - refusing')
    data = call('prod', {'action': 'query', 'titles': SPORT['module_page'], 'prop': 'revisions',
                         'rvprop': 'content', 'rvslots': 'main'})['query']['pages'][0]
    live = data['revisions'][0]['slots']['main']['content'].strip() if 'revisions' in data else None
    if sandbox and live is not None:
        raise SystemExit(f'{SPORT["module_page"]} is already published - use --full')
    if not sandbox and live != SPORT['module_file'].read_text(encoding='utf-8').strip():
        raise SystemExit(f'{SPORT["module_page"]} is not the repo\'s - publish first')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--sandbox', action='store_true')
    mode.add_argument('--full', action='store_true')
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--only', nargs='*')
    parser.add_argument('--sport', choices=sorted(SPORTS), default='football')
    options = parser.parse_args()

    global SPORT
    SPORT = SPORTS[options.sport]
    # Football's uncatalogued competitions are a known pair; basketball's are read
    # from the data, so the list cannot rot as competitions are added.
    if not SPORT['uncatalogued']:
        SPORT['uncatalogued'] = uncatalogued_competitions()

    check_prod_modules(options.sandbox)
    page_body = common.page_text(SPORT['page_template'])
    table_body = common.page_text(SPORT['table_template'])
    candidate = candidate_of(table_body)
    # The candidate's body inline, its parameter taken from the page's array.
    inline_new = re.search(r'<includeonly>(.*)</includeonly>', candidate, re.S).group(1).replace(
        '{{{יריבות לשליפה|}}}', '{{#arrayprint: יריבות לשליפה}}')
    old_call = ('{{' + SPORT['table_template'].split(':', 1)[1]
                + ' |יריבות לשליפה={{#arrayprint: יריבות לשליפה}} }}')
    ranks = catalogue_ranks()
    pages = options.only or opponent_pages()
    if len(pages) == 1 and pages[0].startswith('@'):
        pages = [line.strip() for line in Path(pages[0][1:]).read_text(encoding='utf-8').splitlines()
                 if line.strip()]

    def render(title: str, new: bool) -> tuple[str, str, float]:
        """(page html, html outside the table, walltime)."""
        if options.sandbox:
            text = preamble_for(page_body, common.page_text(title)) + (inline_new if new else old_call)
            page, wall = common.parse(title, text, module_override() if new else None)
            return page, '', wall
        override = ({'templatesandboxtitle': SPORT['table_template'], 'templatesandboxtext': candidate,
                     'templatesandboxcontentmodel': 'wikitext'} if new else None)
        page, wall = common.parse(title, common.page_text(title), override)
        tables = TABLE.findall(page)
        if len(tables) != 1:
            raise ValueError(f'{len(tables)} season tables on the page')
        return page, page.replace(tables[0], ''), wall

    def compare(old_title: str, new_title: str):
        names = opponent_names(old_title, preamble_for(page_body, common.page_text(old_title)))
        old_page, old_outside, old_wall = render(old_title, False)
        new_page, new_outside, new_wall = render(new_title, True)
        # Errors are looked for in the table only. The rest of the page must be
        # byte-identical anyway, and the largest clubs' all-games list already
        # carries "יותר מדי קריאות ל#זמן" (too many #time calls) on production.
        for label, page in (('old', old_page), ('new', new_page)):
            tables = TABLE.findall(page) or ['']
            if 'scribunto-error' in tables[0] or 'class="error"' in tables[0]:
                return 'ERROR', f'{label} table carries an error', old_wall, new_wall
        verdict, detail = check(table_rows(old_page), table_rows(new_page), direct_rows(names), ranks)
        if verdict == 'ok' and old_outside != new_outside:
            verdict, detail = 'FAIL', 'the page outside the table differs'
        return verdict, detail, old_wall, new_wall

    if options.selftest:
        first, second = SPORT['selftest_pair']
        verdict, detail, *_ = compare(first, second)
        print(f'selftest: {first} OLD vs {second} NEW -> {verdict}: {detail}')
        sys.exit(0 if verdict == 'FAIL' else 1)

    tally, added, old_walls, new_walls = Counter(), 0, [], []
    for index, title in enumerate(pages, 1):
        try:
            verdict, detail, old_wall, new_wall = compare(title, title)
        except ValueError as error:
            verdict, detail, old_wall, new_wall = 'ERROR', str(error), 0.0, 0.0
        tally[verdict] += 1
        added += 'added' in detail
        old_walls.append(old_wall)
        new_walls.append(new_wall)
        print(f'{index}/{len(pages)} {verdict:5} {title}: {detail}  ({old_wall:.2f}s -> {new_wall:.2f}s)',
              flush=True)
    import statistics  # noqa: PLC0415
    print(f'\n{len(pages)} opponents: ' + '  '.join(f'{k} {v}' for k, v in sorted(tally.items()))
          + f'; {added} pages gained rows; walltime median '
          f'{statistics.median(old_walls):.2f}s -> {statistics.median(new_walls):.2f}s')
    sys.exit(0 if set(tally) == {'ok'} else 1)


if __name__ == '__main__':
    main()
