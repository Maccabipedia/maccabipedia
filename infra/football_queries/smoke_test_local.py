"""Run the module inside Scribunto on the local wiki and check its numbers.

The stub suites prove the SQL the module builds. They cannot prove that
mw.ext.cargo.query behaves as assumed, that mw.loadData accepts the spec page,
or that a value comes back from Cargo the way the code expects. Only a real
Scribunto run does that.

Every expectation here is computed by a direct Cargo query, so the module is
compared against the database rather than against itself.

    uv run python infra/football_queries/smoke_test_local.py
"""
import json
import sys
import urllib.parse
import urllib.request

API = 'http://localhost:8080/api.php'

# (label, invoke arguments, the direct Cargo query that must agree)
CASES = [
    (
        'season game count',
        {'עונה': '2021/22'},
        {'tables': 'Football_Games', 'fields': 'COUNT(*)=n',
         'where': 'Football_Games.Season = "2021/22"'},
    ),
    (
        'player league goals',
        {'שחקן': 'ערן זהבי', 'מספר אירוע': '3', 'קטגוריית מפעל': 'ליגה'},
        {'tables': 'Football_Games,Games_Events,Competitions',
         'join_on': 'Football_Games._pageID=Games_Events._pageID,'
                    'Football_Games.Competition=Competitions.OriginalName',
         'fields': 'COUNT(*)=n',
         'where': 'Games_Events.PlayerName = "ערן זהבי"'
                  ' AND Games_Events.EventType = 3'
                  ' AND Games_Events.Team = 1 AND Competitions.League = 1'},
    ),
    (
        'wins in a season',
        {'עונה': '2021/22', 'תוצאה': 'ניצחון'},
        {'tables': 'Football_Games', 'fields': 'COUNT(*)=n',
         'where': 'Football_Games.Season = "2021/22"'
                  ' AND Football_Games.ResultOpt = 1'},
    ),
    (
        'goals scored, via the aggregate',
        {'עונה': '2021/22', 'נתון משחק': 'כיבושים'},
        {'tables': 'Football_Games', 'fields': 'SUM(ResultMaccabi)=n',
         'where': 'Football_Games.Season = "2021/22"'},
    ),
]

ERROR_CASES = [
    ('unsupported filter', {'כרטיסים צהובים': '1'}, 'unsupported filter'),
    ('unknown competition category', {'קטגוריית מפעל': 'שטות'},
     'unknown קטגוריית מפעל'),
    ('ampersand refused', {'יריבות': 'x&#0034; OR 1=1'}, 'ampersand'),
]


def api(**params) -> dict:
    params.setdefault('format', 'json')
    request = urllib.request.Request(
        API, data=urllib.parse.urlencode(params).encode('utf-8'))
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode('utf-8'))


def cargo_number(query: dict) -> str:
    rows = api(action='cargoquery', limit=1, **query).get('cargoquery', [])
    value = rows[0]['title']['n'] if rows else '0'
    return str(int(float(value))) if value else '0'


SHIM_TEMPLATE = 'תבנית:ארגז חול/שליפת נתוני משחק'
SHIM_BODY = '<includeonly>{{#invoke:FootballQueries|gameDataCount}}</includeonly>'


def ensure_shim() -> None:
    """The shim must be exercised through a template, as production would.

    gameDataCount reads the CALLING template's parameters, so invoking it
    straight from wikitext passes it nothing - which is how the first run of
    this test got the unfiltered total for every case.
    """
    import subprocess
    result = subprocess.run(
        ['docker', 'compose', '-f', 'infra/local-wiki/docker-compose.yml',
         'exec', '-T', 'mediawiki', 'php', 'maintenance/edit.php',
         '--user', 'Admin', '--summary', 'smoke test shim', SHIM_TEMPLATE],
        input=SHIM_BODY, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'could not create the shim: {result.stderr[:300]}')


def invoke(arguments: dict, through_template: bool = True) -> str:
    if through_template:
        call = '{{' + SHIM_TEMPLATE
    else:
        call = '{{#invoke:FootballQueries|count'
    for name, value in arguments.items():
        call += f'|{name}={value}'
    call += '}}'
    parsed = api(action='parse', text=call, title='עונת 2021/22',
                 contentmodel='wikitext', prop='text', formatversion=2,
                 disablelimitreport=1)
    html = parsed['parse']['text']
    # Strip tags; what remains is the number or the error text.
    import re
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()


def main() -> None:
    failures = 0
    ensure_shim()

    print('--- numbers through a template shim, vs a direct Cargo query ---')
    for label, arguments, query in CASES:
        expected = cargo_number(query)
        actual = invoke(arguments)
        ok = actual == expected
        failures += 0 if ok else 1
        print(f'{"OK  " if ok else "FAIL"}  {label}: module={actual!r} '
              f'cargo={expected!r}')

    print('\n--- the same filters through the direct entry point ---')
    for label, arguments, query in CASES:
        if 'נתון משחק' in arguments:
            continue  # that parameter belongs to the shim, not to count
        expected = cargo_number(query)
        actual = invoke(arguments, through_template=False)
        ok = actual == expected
        failures += 0 if ok else 1
        print(f'{"OK  " if ok else "FAIL"}  {label}: module={actual!r} '
              f'cargo={expected!r}')

    print('\n--- guards must raise visibly, not return a number ---')
    for label, arguments, expected_text in ERROR_CASES:
        output = invoke(arguments)
        ok = expected_text in output
        failures += 0 if ok else 1
        print(f'{"OK  " if ok else "FAIL"}  {label}: {output[:110]!r}')

    print('\n--- misuse must not silently return the unfiltered total ---')
    call = '{{#invoke:FootballQueries|gameDataCount|עונה=2021/22}}'
    parsed = api(action='parse', text=call, title='עונת 2021/22',
                 contentmodel='wikitext', prop='text', formatversion=2,
                 disablelimitreport=1)
    import re
    output = re.sub(r'\s+', ' ',
                    re.sub(r'<[^>]+>', ' ', parsed['parse']['text'])).strip()
    ok = 'takes none of its own' in output
    failures += 0 if ok else 1
    print(f'{"OK  " if ok else "FAIL"}  direct args rejected: {output[:120]!r}')

    print(f'\n{failures} failure(s)')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
