"""Run the module's edge-case queries against production, read-only.

Every one of these cases lives in the old data the local wiki does not hold -
a club whose name carries a quote, a player appearing on both teams in one
game, the rarer event subtypes, a game with no events. So the SQL the module
builds is taken from `tests/edge_case_queries.lua` and executed against
production, then compared with an expectation written here independently.

Nothing is written to any wiki.

    uv run python infra/football_queries/verify_edge_cases.py
"""
import subprocess
import sys

from maccabipediabot.common.wiki_login import get_site

QUERY_PRINTER = 'infra/football_queries/tests/edge_case_queries.lua'

JOIN_EVENTS = 'Football_Games._pageID=Games_Events._pageID'

# name -> (description, an independently written query for the same question)
EXPECTATIONS = {
    'opponent-double-quote-list': (
        'games against בית"ר ירושלים, whose Opponents name carries a quote',
        {'tables': 'Football_Games', 'fields': 'COUNT(*)=n',
         'where': 'Opponent = "ביתר ירושלים"'}),
    'opponent-apostrophe-list': (
        "games against צ'לסי, whose name carries an apostrophe",
        {'tables': 'Football_Games', 'fields': 'COUNT(*)=n',
         'where': 'Opponent = "צלסי"'}),
    'opponent-double-quote-alias': (
        'the same club through the alias expansion',
        {'tables': 'Football_Games', 'fields': 'COUNT(*)=n',
         'where': 'Opponent = "ביתר ירושלים"'}),
    'opponent-apostrophe-alias': (
        'the same club through the alias expansion',
        {'tables': 'Football_Games', 'fields': 'COUNT(*)=n',
         'where': 'Opponent = "צלסי"'}),
    # The same NAME on both teams in ONE game, pinned to that game by date.
    # Career totals would hide the confusion; these are asymmetric on purpose.
    'same-name-both-teams-maccabi': (
        'אלון נתן, 1986-05-24: on both sides of this one game, Maccabi side',
        {'tables': 'Games_Events', 'fields': 'COUNT(*)=n',
         'where': 'PlayerName = "אלון נתן" AND Date = "1986-05-24"'
                  ' AND Team = 1'}),
    'same-name-both-teams-opponent': (
        'the same name in the same game, opposing side',
        {'tables': 'Games_Events', 'fields': 'COUNT(*)=n',
         'where': 'PlayerName = "אלון נתן" AND Date = "1986-05-24"'
                  ' AND Team = 0'}),
    'same-name-both-teams-even-split': (
        'אברהם לוי, 1975-03-01: two events each side, so a leak would be '
        'invisible in the total',
        {'tables': 'Games_Events', 'fields': 'COUNT(*)=n',
         'where': 'PlayerName = "אברהם לוי" AND Date = "1975-03-01"'
                  ' AND Team = 1'}),
    # Metadata queries: about the game, not about a player.
    'metadata-wins': (
        'wins in 1941/42, a season with 6 eventless games and 1 technical',
        {'tables': 'Football_Games', 'fields': 'COUNT(*)=n',
         'where': 'Season = "1941/42" AND ResultOpt = 1'}),
    'metadata-draws': (
        'draws in the same season',
        {'tables': 'Football_Games', 'fields': 'COUNT(*)=n',
         'where': 'Season = "1941/42" AND ResultOpt = 2'}),
    'metadata-losses': (
        'losses in the same season',
        {'tables': 'Football_Games', 'fields': 'COUNT(*)=n',
         'where': 'Season = "1941/42" AND ResultOpt = 3'}),
    'opponent-many-historical-names': (
        'games against מ.ס. אשדוד under all three names it has been stored '
        'under, asked for by the rarest of them',
        {'tables': 'Football_Games', 'fields': 'COUNT(*)=n',
         'where': 'Opponent IN ("הפועל אשדוד", "מ.ס. אשדוד", '
                  '"מכבי עירוני אשדוד")'}),
    'subtype-excluded': (
        'goals excluding penalties - NULL subtypes are dropped too, which is '
        'what the template does as well',
        {'tables': 'Games_Events', 'fields': 'COUNT(*)=n',
         'where': 'EventType = 3 AND SubType != 35 AND Team = 1'}),
}

# The subtype cases share one shape, so they are generated rather than listed.
for event_type, subtype in [('1', '111'), ('2', '211'), ('3', '35'),
                            ('4', '41'), ('7', '71'), ('8', '81'),
                            ('13', '131')]:
    EXPECTATIONS[f'subtype-{event_type}-{subtype}'] = (
        f'events of type {event_type} with subtype {subtype}',
        {'tables': 'Games_Events', 'fields': 'COUNT(*)=n',
         'where': f'EventType = {event_type} AND SubType = {subtype}'
                  ' AND Team = 1'})


def printed_queries() -> dict:
    result = subprocess.run(['lua5.1', QUERY_PRINTER],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'could not print the queries: {result.stderr[:400]}')

    queries = {}
    for line in result.stdout.splitlines():
        parts = line.split('\t')
        if len(parts) == 5:
            name, tables, join, where, fields = parts
            queries[name] = {'tables': tables, 'join_on': join,
                             'where': where, 'fields': fields}
    return queries


def run(site, query: dict) -> str:
    params = {key: value for key, value in query.items() if value}
    response = site.simple_request(
        action='cargoquery', format='json', limit=1, **params).submit()
    rows = response.get('cargoquery', [])
    if not rows:
        return 'NO ROWS'
    value = list(rows[0]['title'].values())[0]
    return str(int(float(value))) if value not in (None, '') else '0'


def cells(site, query: dict) -> dict:
    """A multi-cell aggregate row, keyed by alias."""
    params = {key: value for key, value in query.items() if value}
    response = site.simple_request(
        action='cargoquery', format='json', limit=1, **params).submit()
    rows = response.get('cargoquery', [])
    if not rows:
        return {}
    return {alias: (str(int(float(value))) if value not in (None, '') else '0')
            for alias, value in rows[0]['title'].items()}


SEASON = '1941/42'


def check_metadata(site, queries: dict) -> int:
    """Metadata numbers must include games that have no events.

    1941/42 has 31 games, 6 of them with no events at all and 1 technical, and
    its results split 24 wins / 3 draws / 4 losses - which sums to 31. So the
    four numbers together prove nothing was dropped. This is the case that made
    the review's Team-in-the-WHERE finding matter: it took 3,504 games down to
    3,439 across production.
    """
    failures = 0

    query = queries.get('metadata-results-in-one-query')
    if not query:
        print('MISSING  metadata-results-in-one-query was not printed')
        return 1

    # A metadata query must not reach the events table at all.
    if 'Games_Events' in (query['tables'] or ''):
        print(f'FAIL  metadata joins the events table: {query["tables"]}')
        failures += 1
    else:
        print('OK    metadata asks Football_Games alone, no events join')

    actual = cells(site, query)
    expected = {
        'c1': run(site, {'tables': 'Football_Games', 'fields': 'COUNT(*)=n',
                         'where': f'Season = "{SEASON}" AND ResultOpt = 1'}),
        'c2': run(site, {'tables': 'Football_Games', 'fields': 'COUNT(*)=n',
                         'where': f'Season = "{SEASON}" AND ResultOpt = 2'}),
        'c3': run(site, {'tables': 'Football_Games', 'fields': 'COUNT(*)=n',
                         'where': f'Season = "{SEASON}" AND ResultOpt = 3'}),
        'c4': run(site, {'tables': 'Football_Games', 'fields': 'COUNT(*)=n',
                         'where': f'Season = "{SEASON}"'}),
    }
    labels = {'c1': 'wins', 'c2': 'draws', 'c3': 'losses', 'c4': 'all games'}
    for alias in ['c1', 'c2', 'c3', 'c4']:
        got = actual.get(alias, 'missing')
        ok = got == expected[alias]
        failures += 0 if ok else 1
        print(f'{"OK  " if ok else "FAIL"}  metadata/{labels[alias]}: '
              f'module={got} independent={expected[alias]}')

    parts = sum(int(actual.get(alias, 0)) for alias in ['c1', 'c2', 'c3'])
    whole = int(actual.get('c4', -1))
    if parts != whole:
        print(f'FAIL  metadata: wins+draws+losses is {parts} but all games is '
              f'{whole} - something was dropped')
        failures += 1
    else:
        print(f'OK    metadata: wins+draws+losses = all games = {whole}')

    # Mixing a metadata cell with a player-event cell in one query.
    mixed = queries.get('metadata-and-events-together')
    if mixed:
        got = cells(site, mixed)
        games = run(site, {'tables': 'Football_Games', 'fields': 'COUNT(*)=n',
                           'where': f'Season = "{SEASON}"'})
        ok = got.get('c1') == games
        failures += 0 if ok else 1
        print(f'{"OK  " if ok else "FAIL"}  metadata beside an event cell: '
              f'games={got.get("c1")} independent={games}')

    eventless = run(site, {
        'tables': 'Football_Games,Games_Events', 'join_on': JOIN_EVENTS,
        'fields': 'COUNT(DISTINCT Football_Games._pageID)=n',
        'where': f'Football_Games.Season = "{SEASON}"'
                 ' AND Games_Events._pageID IS NULL'})
    technical = run(site, {
        'tables': 'Football_Games', 'fields': 'COUNT(*)=n',
        'where': f'Season = "{SEASON}" AND Technical = 1'})
    print(f'        {SEASON}: {eventless} game(s) with no events and '
          f'{technical} technical, all included above')
    return failures


def selftest(site, queries: dict) -> int:
    """Prove the comparison can fail, by asking it a question it must reject.

    Without this the whole file is a list of OK lines that would print OK
    whatever the module did - which is exactly how an earlier harness in this
    directory reported success while comparing nothing.
    """
    name = 'opponent-double-quote-list'
    query = queries[name]
    wrong = {'tables': 'Football_Games', 'fields': 'COUNT(*)=n',
             'where': 'Opponent = "הפועל תל אביב"'}

    actual = run(site, query)
    expected = run(site, wrong)
    if actual == expected:
        print(f'SELFTEST FAILED: {name} matched a deliberately wrong '
              f'expectation ({actual})')
        return 1
    print(f'SELFTEST PASSED: {name} is {actual} and refuses to match '
          f'{expected} from the wrong club')
    return 0


def check_subtype_exclusion(site) -> int:
    """ללא תת אירוע must actually remove rows that are there.

    The comparison above puts the module's exclusion beside an independently
    written exclusion, so both sides agree even if neither excludes anything -
    which is exactly what a broken `!=` would look like. This asserts the
    three numbers relate as they must: goals with the subtype, goals without
    it, and goals excluding it, on real data.
    """
    goals = int(run(site, {'tables': 'Games_Events', 'fields': 'COUNT(*)=n',
                           'where': 'EventType = 3 AND Team = 1'}))
    penalties = int(run(site, {
        'tables': 'Games_Events', 'fields': 'COUNT(*)=n',
        'where': 'EventType = 3 AND SubType = 35 AND Team = 1'}))
    excluded = int(run(site, {
        'tables': 'Games_Events', 'fields': 'COUNT(*)=n',
        'where': 'EventType = 3 AND SubType != 35 AND Team = 1'}))

    print('--- the subtype being excluded is actually in the data ---')
    print(f'        goals={goals} penalties={penalties} '
          f'excluding penalties={excluded}')

    if penalties == 0:
        print('FAIL  no goal carries subtype 35, so excluding it proves '
              'nothing - pick a subtype that exists')
        return 1
    if excluded >= goals:
        print(f'FAIL  excluding subtype 35 removed nothing: {excluded} of '
              f'{goals} - the exclusion is not being applied')
        return 1

    # SQL's `SubType != 35` also drops rows whose SubType is NULL, because
    # NULL != 35 is NULL, not true - the template behaves the same way. So the
    # exclusion must remove AT LEAST every penalty, and possibly more.
    # Measured on production: it removes exactly 473 of 6287, which says every
    # goal row carries a subtype. That is a fact about the data, so it is
    # reported rather than asserted; the invariant is what is checked.
    removed = goals - excluded
    if removed < penalties:
        print(f'FAIL  excluding subtype 35 removed {removed} rows but {penalties} '
              'carry that subtype - the exclusion is only partly applied')
        return 1

    also_null = removed - penalties
    print(f'OK    excluding subtype 35 removed {removed} of {goals} goals: '
          f'{penalties} penalties and {also_null} with no subtype at all')
    return 0


def main() -> None:
    site = get_site()
    queries = printed_queries()
    failures = selftest(site, queries)
    hollow: list = []
    print()

    for name, (description, expectation) in sorted(EXPECTATIONS.items()):
        query = queries.get(name)
        if not query:
            print(f'MISSING  {name} was not printed by the Lua harness')
            failures += 1
            continue

        actual = run(site, query)
        expected = run(site, expectation)
        ok = actual == expected

        # Agreement at zero proves nothing: a query that matched nothing and a
        # query that is simply wrong both answer 0. Such a case is reported as
        # INCONCLUSIVE rather than OK, so it cannot pad the score.
        if ok and actual in ('0', 'NO ROWS'):
            print(f'HOLLOW  {name}: both sides are {actual} - this case '
                  'cannot distinguish right from wrong')
            print(f'        {description}')
            hollow.append(name)
            continue

        failures += 0 if ok else 1
        print(f'{"OK  " if ok else "FAIL"}  {name}: module={actual} '
              f'independent={expected}')
        print(f'        {description}')

    print()
    failures += check_subtype_exclusion(site)
    print()
    failures += check_metadata(site, queries)

    total = len(EXPECTATIONS) + 7
    print(f'\n{total - failures - len(hollow)}/{total} edge-case checks agree '
          f'on a non-zero value')
    if hollow:
        print(f'{len(hollow)} case(s) agree only at zero and prove nothing: '
              f'{", ".join(hollow)}')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
