"""Old referee season tables against Module:FootballSeasonTable, on production.

    uv run python infra/lua_modules/compare_referee_season_table.py --role main --sandbox
    uv run python infra/lua_modules/compare_referee_season_table.py --role assistant --sandbox --selftest

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
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path('infra/lua_modules')))
sys.path.insert(0, str(Path('infra/season_pages')))
import mwparserfromhell  # noqa: E402

import compare_opponent_season_table as opponent  # noqa: E402
from season_api import call  # noqa: E402

CARGO_QUERY = re.compile(r'\{\{#cargo_query:.*?\n\}\}', re.S)
# The table, up to the next section: the wins/losses boxes follow it with rows of their own.
TABLE = re.compile(r'<div class="title">סטטיסטיקה עונתית</div>.*?<div class="table-content">(.*?)'
                   r'(?=<div class="section"|<div class="games-records-container"|\Z)', re.S)


def referee_name(title: str) -> str:
    """`שם להצגה` as the sport's referee template sets it: the page's own
    parameter, else the page name without the sport's namespace and `(שופט)`.

    Football's helper in compare_referee_main_leaderboards hardcodes
    `שופט כדורגל` and `כדורגל:`; this is the same rule read from the sport.
    """
    wrapper = opponent.SPORT['wrapper']
    calls = [node for node in mwparserfromhell.parse(opponent.common.page_text(title)).filter_templates()
             if node.name.strip() in (wrapper, 'תבנית:' + wrapper)]
    if len(calls) != 1:
        raise ValueError(f'{len(calls)} calls of the referee template on the page')
    if calls[0].has('שם להצגה') and str(calls[0].get('שם להצגה').value).strip():
        return str(calls[0].get('שם להצגה').value).strip()
    namespace = opponent.SPORT['page_template'].split(':', 1)[1].split(' ')[-1] + ':'
    data = call('prod', {'action': 'expandtemplates', 'title': title, 'prop': 'wikitext',
                         'text': '{{#replaceset: {{PAGENAME}} |' + namespace + '|(שופט)}}'}, post=True)
    return data['expandtemplates']['wikitext'].strip()


def candidate_of(body: str, role: str) -> str:
    if len(CARGO_QUERY.findall(body)) != 1:
        raise SystemExit('the table template does not hold exactly one #cargo_query - refusing')
    module = opponent.SPORT['module_page'].removeprefix('Module:')
    invoke = ('{{#invoke:' + module + '|rows|' + opponent.SPORT['referee_filters'][role]
              + '={{{שם להצגה|}}}|קישור מפעל=מרכז}}')
    return CARGO_QUERY.sub(lambda _: invoke, body)


def previous_text(template: str) -> str:
    """The template's text before the switch, from switch_template_prod.py's record.

    Once a template is switched it holds no #cargo_query, so `candidate_of` refuses
    and the gate cannot run at all - for either sport, since football's were switched
    in September. This is what `--against` renders as the OLD side instead, and it is
    the only way to re-check these pages when the module changes later.
    """
    found = []
    for record in sorted(Path('.claude/tmp/template_switches').glob('*.json')):
        saved = json.loads(record.read_text(encoding='utf-8'))
        if saved['title'] == template:
            found.append((record.stat().st_mtime, saved['previous_text']))
    if not found:
        raise SystemExit(f'no saved switch record for {template} - cannot run --against')
    return max(found)[1]


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
        data = call('prod', {'action': 'cargoquery', 'tables': opponent.SPORT['map_table'],
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
    """(season, competition, *results) from Cargo, written apart from the module."""
    literal = '"' + name.replace('\\', '\\\\').replace('"', '\\"') + '"'
    games = opponent.SPORT['games']
    # Full table names: Cargo's field parser refuses SUM(alias.column=1).
    results = ', '.join(f'{sql.replace("(", f"({games}.")}={key}'
                        for key, sql in opponent.SPORT['results'])
    params = {'action': 'cargoquery', 'group_by': f'{games}.Season, {games}.Competition',
              'order_by': f'{games}.Season DESC', 'limit': '2000',
              'fields': f'{games}.Season=s, {games}.Competition=c, {results}'}
    params.update(**opponent.SPORT['referee_where'][role](literal))
    return [(html_module.unescape(r['title']['s']), html_module.unescape(r['title']['c']),
             *(int(float(r['title'][key])) for key, _ in opponent.SPORT['results']))
            for r in call('prod', params)['cargoquery']]


def expected_cell(competition: str, groups: dict, pages: set) -> tuple:
    """The cell the row shows: the competition linked to its grouping page when
    that page exists, else the bare grouping name. The grouping page lives in the
    sport's own namespace - basketball's `ליגת העל` is `כדורסל: ליגת העל`, and the
    bare name is FOOTBALL's article."""
    grouping = groups[competition]
    page = opponent.SPORT['grouping_page'] % grouping if grouping else ''
    if grouping and page in pages:
        return competition, page
    return grouping, None


def check(old: list[dict], new: list[dict], direct: list[tuple], groups: dict, pages: set,
          ranks: dict) -> tuple[str, str]:
    cell = lambda row: (row['season'], row['competition'], row['competition_link'])  # noqa: E731
    expected = Counter()
    for season, competition, *results in direct:
        text, link = expected_cell(competition, groups, pages)
        expected[(season, text, link, tuple(results))] += 1
    got = Counter((row['season'], row['competition'], row['competition_link'], row['results']) for row in new)
    if got != expected:
        return 'FAIL', f'NEW vs Cargo: only NEW {list(got - expected)[:3]}, only Cargo {list(expected - got)[:3]}'
    seasons = lambda values: [v for i, v in enumerate(values) if i == 0 or v != values[i - 1]]  # noqa: E731
    if seasons([row['season'] for row in new]) != seasons([s for s, *_ in direct]):
        return 'FAIL', 'NEW season sequence differs from the database order'
    # Two competitions in one season can render the SAME cell - both uncatalogued,
    # so both show an empty grouping name (גביע המחזיקות and גביע אירופה למחזיקות
    # in 1966/67 do). Keyed by cell alone, one row would shadow the other and the
    # mismatch would be reported against the wrong competition. Each cell therefore
    # holds the LIST of rows that produced it, and a lookup consumes one.
    competition_of = defaultdict(list)
    for season, competition, *_ in direct:
        competition_of[(season, *expected_cell(competition, groups, pages))].append(competition)
    for season in sorted({row['season'] for row in new}):
        taken = defaultdict(int)
        inside = []
        for row in new:
            if row['season'] != season:
                continue
            names = competition_of[cell(row)]
            index = taken[cell(row)]
            taken[cell(row)] += 1
            inside.append(names[index] if index < len(names) else None)
        if None in inside:
            return 'FAIL', f'{season}: NEW has more rows for a cell than the database'
        if inside != sorted(inside, key=lambda c: (ranks.get(c, opponent.OTHER), c)):
            return 'FAIL', f'{season}: order {inside}'
    if Counter(map(cell, old)) != Counter(map(cell, new)):
        return 'FAIL', (f'cells: only OLD {sorted(Counter(map(cell, old)) - Counter(map(cell, new)))[:3]}, '
                        f'only NEW {sorted(Counter(map(cell, new)) - Counter(map(cell, old)))[:3]}')
    # Same reason as above: two rows may share a cell, so each OLD row is paired
    # with its OWN NEW row rather than with whichever one a dict kept.
    new_by_cell = defaultdict(list)
    for row in new:
        new_by_cell[cell(row)].append(row)
    taken = defaultdict(int)
    for row in old:
        index = taken[cell(row)]
        taken[cell(row)] += 1
        other = new_by_cell[cell(row)][index]
        if row['season_link'] != other['season_link']:
            return 'FAIL', f'{cell(row)} season link {row["season_link"]!r} vs {other["season_link"]!r}'
        if row['results'] != other['results']:
            names = competition_of[cell(row)]
            if (index < len(names) and names[index] in opponent.SPORT['uncatalogued']
                    and set(row['results']) == {0}):
                continue
            return 'FAIL', f'{cell(row)} results {row["results"]} vs {other["results"]}'
    # A page whose name matches no game compares three empty tables. That is not a
    # failure, but calling it `ok` lets the summary imply a comparison happened.
    if not direct and not old and not new:
        return 'empty', 'no games under this name - nothing compared'
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
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--sandbox', action='store_true',
                      help='before the switch: the live template is OLD, the candidate NEW')
    mode.add_argument('--against', action='store_true',
                      help='after the switch: the saved previous template is OLD, the live page NEW')
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--only', nargs='*')
    parser.add_argument('--sport', choices=sorted(opponent.SPORTS), default='football')
    options = parser.parse_args()

    opponent.SPORT = opponent.SPORTS[options.sport]
    if not opponent.SPORT['uncatalogued']:
        opponent.SPORT['uncatalogued'] = opponent.uncatalogued_competitions()
    # The logic under review is Module:SeasonTable and the query layer, none of which
    # the sandbox override can replace - the overridden page is only the sport's
    # declaration. Without this the run would judge whatever production happens to
    # hold, and read as a clean pass on code the repo no longer has.
    opponent.check_prod_modules(sandbox=False)
    template = opponent.SPORT['referee_templates'][options.role]
    body = opponent.common.page_text(template)
    old_body = previous_text(template) if options.against else body
    inline = re.search(r'<includeonly>(.*)</includeonly>',
                       body if options.against else candidate_of(body, options.role), re.S).group(1)
    groups, ranks = grouping_map(), opponent.catalogue_ranks()
    every_grouping = call('prod', {'action': 'cargoquery', 'tables': opponent.SPORT['map_table'],
                                   'fields': 'ConcentratedName=c', 'limit': '500'})['cargoquery']
    # The grouping page in this sport's namespace, which is what the row links to.
    pages_with_titles = existing({opponent.SPORT['grouping_page'] % html_module.unescape(
        r['title']['c']).strip() for r in every_grouping})
    pages = options.only or referee_pages(template)
    if len(pages) == 1 and pages[0].startswith('@'):
        pages = [line.strip() for line in Path(pages[0][1:]).read_text(encoding='utf-8').splitlines() if line.strip()]

    def render(title: str, name: str, new: bool) -> str:
        if new:
            text = inline.replace('{{{שם להצגה|}}}', name)
            page, _ = opponent.common.parse(title, text, opponent.module_override())
        elif options.against:
            # The template this one replaced, rendered inline with the same name.
            # The `#vardefine` is not decoration: the old ROW template reads
            # `שם להצגה` as a page variable to filter its per-row counts. Without it
            # every row counted EVERY game of that season and competition - the old
            # side showed Maccabi's whole record (32-3) instead of one referee's.
            text = re.search(r'<includeonly>(.*)</includeonly>', old_body, re.S).group(1)
            page, _ = opponent.common.parse(
                title, '{{#vardefine: שם להצגה |' + name + '}}'
                + text.replace('{{{שם להצגה|}}}', name))
        else:
            call_text = '{{' + template.removeprefix('תבנית:') + ' |שם להצגה=' + name + ' }}'
            page, _ = opponent.common.parse(title, '{{#vardefine: שם להצגה |' + name + '}}' + call_text)
        return page

    def compare(old_title: str, new_title: str):
        old_name, new_name = referee_name(old_title), referee_name(new_title)
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
        except KeyError as error:
            # A page that does not exist (a typo in --only) came back as a raw
            # traceback that killed the whole sweep partway through.
            verdict, detail = 'ERROR', f'cannot read the page ({error})'
        tally[verdict] += 1
        print(f'{index}/{len(pages)} {verdict:5} {title}: {detail}', flush=True)
    print(f'\n{len(pages)} referees ({options.role}): ' + '  '.join(f'{k} {v}' for k, v in sorted(tally.items())))
    # `empty` pages compared nothing, so they are counted apart and never let the
    # run pass on their own: a sweep that is all `empty` proves nothing.
    sys.exit(0 if set(tally) <= {'ok', 'empty'} and tally['ok'] else 1)


if __name__ == '__main__':
    main()
