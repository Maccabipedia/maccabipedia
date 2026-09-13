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
    'player-on-both-teams': (
        'אברהם לוי played for both sides across his career - only Maccabi',
        {'tables': 'Games_Events', 'fields': 'COUNT(*)=n',
         'where': 'PlayerName = "אברהם לוי" AND Team = 1'}),
    'player-on-both-teams-opponent-side': (
        'the same name on the opposing side',
        {'tables': 'Games_Events', 'fields': 'COUNT(*)=n',
         'where': 'PlayerName = "אברהם לוי" AND Team = 0'}),
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


def check_grain(site, queries: dict) -> int:
    """A game with no events must still be counted by a game-grain cell.

    This is the case that made the review's Team-in-the-WHERE finding matter:
    production has 51 games with no events at all and 65 with no Maccabi event,
    and a merged block counted 3,439 of 3,504 games before the fix.
    """
    season = '1951/52'
    query = queries.get('eventless-games-by-grain')
    if not query:
        print('MISSING  eventless-games-by-grain was not printed')
        return 1

    actual = cells(site, query)
    total_games = run(site, {
        'tables': 'Football_Games', 'fields': 'COUNT(*)=n',
        'where': f'Season = "{season}"'})
    goals = run(site, {
        'tables': 'Football_Games,Games_Events', 'join_on': JOIN_EVENTS,
        'fields': 'COUNT(*)=n',
        'where': f'Football_Games.Season = "{season}"'
                 ' AND Games_Events.EventType = 3 AND Games_Events.Team = 1'})

    failures = 0
    for alias, expected, label in [('c1', total_games, 'games (game grain)'),
                                   ('c2', goals, 'goals (event grain)')]:
        got = actual.get(alias, 'missing')
        ok = got == expected
        failures += 0 if ok else 1
        print(f'{"OK  " if ok else "FAIL"}  eventless/{label}: module={got} '
              f'independent={expected}')

    eventless = run(site, {
        'tables': 'Football_Games,Games_Events', 'join_on': JOIN_EVENTS,
        'fields': 'COUNT(DISTINCT Football_Games._pageID)=n',
        'where': f'Football_Games.Season = "{season}"'
                 ' AND Games_Events._pageID IS NULL'})
    print(f'        {season} has {eventless} game(s) with no events at all, '
          f'and the game-grain cell includes them')
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


def main() -> None:
    site = get_site()
    queries = printed_queries()
    failures = selftest(site, queries)
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
        failures += 0 if ok else 1
        print(f'{"OK  " if ok else "FAIL"}  {name}: module={actual} '
              f'independent={expected}')
        print(f'        {description}')

    print()
    failures += check_grain(site, queries)

    total = len(EXPECTATIONS) + 2
    print(f'\n{total - failures}/{total} edge-case checks agree')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
