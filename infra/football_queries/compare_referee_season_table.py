"""Old referee season tables against Module:FootballSeasonTable, on production.

    uv run python infra/football_queries/compare_referee_season_table.py --role main --sandbox
    uv run python infra/football_queries/compare_referee_season_table.py --role assistant --sandbox --selftest

READ-ONLY, paced. The section alone, per referee: OLD through the live table
template, NEW through the candidate body with Module:FootballSeasonTable
overridden by the repo file (the published module predates the referee
filters). Same checks as compare_opponent_season_table.py, except that a row
is identified by its whole competition CELL - the referee rows show the
competition's grouping name (Football_Competitions_Map) when that page is
missing, and nothing when the map lacks it - so the expected cell is computed
here, independently: the grouping row first (a row whose name differs from
the competition), else the competition's own row; linked when that page
exists. The first map row in storage order (_ID) wins, as the templates'
unordered `limit=1` returned it; OLD against NEW checks that against today's pages.
"""
from __future__ import annotations

import argparse
import html as html_module
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path('infra/football_queries')))
sys.path.insert(0, str(Path('infra/season_pages')))
import compare_opponent_season_table as opponent  # noqa: E402
import compare_referee_main_leaderboards as referee  # noqa: E402
from season_api import call  # noqa: E402

TEMPLATES = {'main': 'תבנית:שופט כדורגל/הצגת סטטיסטיקה עונתית/שופט ראשי',
             'assistant': 'תבנית:שופט כדורגל/הצגת סטטיסטיקה עונתית/עוזר שופט'}
FILTER = {'main': 'שופט', 'assistant': 'עוזר שופט'}
CARGO_QUERY = re.compile(r'\{\{#cargo_query:.*?\n\}\}', re.S)
# The table, up to the next section: the wins/losses boxes follow it with rows of their own.
TABLE = re.compile(r'<div class="title">סטטיסטיקה עונתית</div>.*?<div class="table-content">(.*?)'
                   r'(?=<div class="section"|<div class="games-records-container"|\Z)', re.S)


def candidate_of(body: str, role: str) -> str:
    if len(CARGO_QUERY.findall(body)) != 1:
        raise SystemExit('the table template does not hold exactly one #cargo_query - refusing')
    invoke = ('{{#invoke:FootballSeasonTable|rows|' + FILTER[role]
              + '={{{שם להצגה|}}}|קישור מפעל=מרכז}}')
    return CARGO_QUERY.sub(lambda _: invoke, body)


def rows_of(page: str) -> list[dict]:
    tables = TABLE.findall(page)
    if len(tables) != 1:
        raise ValueError(f'{len(tables)} season tables on the page')
    return opponent.table_rows('<div class="title">סטטיסטיקה עונתית</div><div class="table-content">'
                               + tables[0])


class GroupingMap(dict):
    """competition -> its grouping name, by the templates' own lookup
    (`Names HOLDS "name"`, limit 1) through the API, once per competition."""

    def __missing__(self, competition: str) -> str:
        data = call('prod', {'action': 'cargoquery', 'tables': 'Football_Competitions_Map',
                             'fields': 'ConcentratedName=c', 'where': f'Names HOLDS "{competition}"',
                             'limit': '1'})
        rows = data['cargoquery']
        self[competition] = html_module.unescape(rows[0]['title']['c']).strip() if rows else ''
        return self[competition]


def grouping_map() -> GroupingMap:
    return GroupingMap()


def existing(titles: set[str]) -> set[str]:
    found, titles = set(), sorted(t for t in titles if t)
    for start in range(0, len(titles), 50):
        data = call('prod', {'action': 'query', 'titles': '|'.join(titles[start:start + 50])})
        found |= {p['title'] for p in data['query']['pages'] if 'missing' not in p and 'invalid' not in p}
    return found


def direct_rows(name: str, role: str) -> list[tuple]:
    literal = '"' + name.replace('\\', '\\\\').replace('"', '\\"') + '"'
    # Full table names: Cargo's field parser refuses SUM(alias.column=1).
    params = {'action': 'cargoquery', 'group_by': 'Football_Games.Season, Football_Games.Competition',
              'order_by': 'Football_Games.Season DESC', 'limit': '2000',
              'fields': 'Football_Games.Season=s, Football_Games.Competition=c, '
                        'SUM(Football_Games.ResultOpt=1)=w, SUM(Football_Games.ResultOpt=2)=d, '
                        'SUM(Football_Games.ResultOpt=3)=l'}
    if role == 'main':
        params.update(tables='Football_Games', where=f'Football_Games.Refs = {literal}')
    else:
        params.update(tables='Football_Games, Games_Referees',
                      join_on='Football_Games._pageID=Games_Referees._pageID',
                      where=f'Games_Referees.AssistantReferees HOLDS {literal}')
    return [(html_module.unescape(r['title']['s']), html_module.unescape(r['title']['c']),
             int(float(r['title']['w'])), int(float(r['title']['d'])), int(float(r['title']['l'])))
            for r in call('prod', params)['cargoquery']]


def expected_cell(competition: str, groups: dict, pages: set) -> tuple:
    grouping = groups[competition]
    if grouping and grouping in pages:
        return competition, grouping
    return grouping, None


def check(old: list[dict], new: list[dict], direct: list[tuple], groups: dict, pages: set,
          ranks: dict) -> tuple[str, str]:
    cell = lambda row: (row['season'], row['competition'], row['competition_link'])  # noqa: E731
    expected = Counter()
    for season, competition, wins, draws, losses in direct:
        text, link = expected_cell(competition, groups, pages)
        expected[(season, text, link, (wins, draws, losses))] += 1
    got = Counter((row['season'], row['competition'], row['competition_link'], row['results']) for row in new)
    if got != expected:
        return 'FAIL', f'NEW vs Cargo: only NEW {list(got - expected)[:3]}, only Cargo {list(expected - got)[:3]}'
    seasons = lambda values: [v for i, v in enumerate(values) if i == 0 or v != values[i - 1]]  # noqa: E731
    if seasons([row['season'] for row in new]) != seasons([s for s, *_ in direct]):
        return 'FAIL', 'NEW season sequence differs from the database order'
    competition_of = {(s, *expected_cell(c, groups, pages)): c for s, c, *_ in direct}
    for season in {row['season'] for row in new}:
        inside = [competition_of[cell(row)] for row in new if row['season'] == season]
        if inside != sorted(inside, key=lambda c: (ranks.get(c, opponent.OTHER), c)):
            return 'FAIL', f'{season}: order {inside}'
    if Counter(map(cell, old)) != Counter(map(cell, new)):
        return 'FAIL', (f'cells: only OLD {sorted(Counter(map(cell, old)) - Counter(map(cell, new)))[:3]}, '
                        f'only NEW {sorted(Counter(map(cell, new)) - Counter(map(cell, old)))[:3]}')
    new_by_cell = {cell(row): row for row in new}
    for row in old:
        other = new_by_cell[cell(row)]
        if row['season_link'] != other['season_link']:
            return 'FAIL', f'{cell(row)} season link {row["season_link"]!r} vs {other["season_link"]!r}'
        if row['results'] != other['results']:
            if competition_of[cell(row)] in opponent.UNCATALOGUED and row['results'] == (0, 0, 0):
                continue
            return 'FAIL', f'{cell(row)} results {row["results"]} vs {other["results"]}'
    return 'ok', f'{len(new)} rows'


def referee_pages(template: str) -> list[str]:
    titles, cont = [], {}
    while True:
        # No namespace filter: referee pages live in the כדורגל: namespace.
        data = call('prod', dict({'action': 'query', 'list': 'embeddedin', 'eititle': template,
                                  'eilimit': 'max'}, **cont))
        titles += [row['title'] for row in data['query']['embeddedin']]
        if 'continue' not in data:
            return sorted(titles)
        cont = data['continue']


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--role', choices=('main', 'assistant'), required=True)
    parser.add_argument('--sandbox', action='store_true', required=True)
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--only', nargs='*')
    options = parser.parse_args()

    template = TEMPLATES[options.role]
    body = opponent.common.page_text(template)
    inline = re.search(r'<includeonly>(.*)</includeonly>', candidate_of(body, options.role), re.S).group(1)
    groups, ranks = grouping_map(), opponent.catalogue_ranks()
    every_grouping = call('prod', {'action': 'cargoquery', 'tables': 'Football_Competitions_Map',
                                   'fields': 'ConcentratedName=c', 'limit': '500'})['cargoquery']
    pages_with_titles = existing({html_module.unescape(r['title']['c']).strip() for r in every_grouping})
    pages = options.only or referee_pages(template)
    if len(pages) == 1 and pages[0].startswith('@'):
        pages = [line.strip() for line in Path(pages[0][1:]).read_text(encoding='utf-8').splitlines() if line.strip()]

    def render(title: str, name: str, new: bool) -> str:
        if new:
            text = inline.replace('{{{שם להצגה|}}}', name)
            page, _ = opponent.common.parse(title, text, opponent.module_override())
        else:
            call_text = '{{' + template.removeprefix('תבנית:') + ' |שם להצגה=' + name + ' }}'
            page, _ = opponent.common.parse(title, '{{#vardefine: שם להצגה |' + name + '}}' + call_text)
        return page

    def compare(old_title: str, new_title: str):
        old_name, new_name = referee.referee_name(old_title), referee.referee_name(new_title)
        old_page, new_page = render(old_title, old_name, False), render(new_title, new_name, True)
        for label, page in (('old', old_page), ('new', new_page)):
            tables = TABLE.findall(page) or ['']
            if 'scribunto-error' in tables[0] or 'class="error"' in tables[0]:
                return 'ERROR', f'{label} table carries an error'
        return check(rows_of(old_page), rows_of(new_page), direct_rows(old_name, options.role),
                     groups, pages_with_titles, ranks)

    if options.selftest:
        first, second = pages[0], pages[-1]
        verdict, detail = compare(first, second)
        print(f'selftest: {first} OLD vs {second} NEW -> {verdict}: {detail}')
        sys.exit(0 if verdict == 'FAIL' else 1)

    tally = Counter()
    for index, title in enumerate(pages, 1):
        try:
            verdict, detail = compare(title, title)
        except ValueError as error:
            verdict, detail = 'ERROR', str(error)
        tally[verdict] += 1
        print(f'{index}/{len(pages)} {verdict:5} {title}: {detail}', flush=True)
    print(f'\n{len(pages)} referees ({options.role}): ' + '  '.join(f'{k} {v}' for k, v in sorted(tally.items())))
    sys.exit(0 if set(tally) == {'ok'} else 1)


if __name__ == '__main__':
    main()
