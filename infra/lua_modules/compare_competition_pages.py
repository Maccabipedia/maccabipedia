"""Gate the football competition pages' move to the Lua query layer, page by page.

    uv run python infra/lua_modules/compare_competition_pages.py capture --wiki local --out DIR
    uv run python infra/lua_modules/compare_competition_pages.py sandbox --template T --candidate FILE --out DIR
    uv run python infra/lua_modules/compare_competition_pages.py diff OLD NEW [--expect-change PAGE ...]
    uv run python infra/lua_modules/compare_competition_pages.py check DIR --wiki local|prod
    uv run python infra/lua_modules/compare_competition_pages.py selftest OLD NEW
    uv run python infra/lua_modules/compare_competition_pages.py local-switch old|new

The local run: local-switch old, capture, deploy_modules.py, local-switch new,
capture, then diff/check/selftest on the two captures.

capture - renders every page that transcludes תבנית:מפעל כדורגל, as it is now.
sandbox - production only, read-only: renders them with ONE template swapped for a
          candidate through TemplateSandbox. Nothing is saved.
diff    - every page byte-identical, except the pages named --expect-change, which
          must differ. A page named there that does not differ fails too.
check   - the rendered numbers against Cargo, computed here and not by the module:
          the stats box (games, wins, draws, losses, goals, conceded, clean sheets,
          yellows, reds) and the margins of the biggest wins and losses. Names are
          matched ignoring quote characters on both sides, so this shares nothing
          with the module's quote rule. Also refuses a render with a Lua error.
selftest- proves diff and check can fail: one page's render against another's,
          and a render whose numbers were altered.
"""
import argparse
import html
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

WIKIS = {'local': 'http://localhost:8089/api.php', 'prod': 'https://www.maccabipedia.co.il/api.php'}
CONTAINER = 'תבנית:מפעל כדורגל'
PROD_PAUSE = 3

STATS_LABELS = {'משחקים': 'games', 'ניצחונות': 'wins', 'תיקו': 'draws', 'הפסדים': 'losses',
                'שערים': 'goalsFor', 'ספיגות': 'goalsAgainst', 'שער נקי': 'cleanSheets',
                'צהובים': 'yellows', 'אדומים': 'reds'}
LUA_ERRORS = ('שגיאת Lua', 'Lua error', 'scribunto-error', 'FootballStatsBlock:', 'FootballCompetition:',
              'FootballQueries:')


def session_for(wiki: str) -> requests.Session:
    session = requests.Session()
    session.headers['User-Agent'] = os.environ.get('MACCABIPEDIA_UA_SCRIPT', 'MaccabipediaBot-compare/1.0')
    session.api = WIKIS[wiki]
    session.pause = PROD_PAUSE if wiki == 'prod' else 0
    return session


def api(session, params: dict, post: bool = False) -> dict:
    params = {**params, 'format': 'json', 'formatversion': 2}
    for attempt in range(4):
        if post:
            # Multipart: the production firewall refuses a large urlencoded body
            # (a 302 to its abuse page) and accepts the same bytes this way.
            response = session.post(session.api, files={k: (None, str(v)) for k, v in params.items()},
                                    timeout=180, allow_redirects=False)
        else:
            response = session.get(session.api, params=params, timeout=180, allow_redirects=False)
        if response.status_code == 302:
            raise SystemExit(f'redirected to {response.headers.get("Location")} - the firewall refused the request')
        if response.status_code == 508 and attempt < 3:
            time.sleep(10)
            continue
        if response.status_code != 200 or 'application/json' not in response.headers.get('Content-Type', ''):
            raise SystemExit(f'bad response {response.status_code}: {response.text[:400]}')
        data = response.json()
        if 'error' in data:
            raise SystemExit(f'API error: {data["error"]}')
        return data
    raise SystemExit('508 four times - the server is overloaded, try later')


def competition_pages(session) -> list[str]:
    data = api(session, {'action': 'query', 'list': 'embeddedin', 'eititle': CONTAINER, 'einamespace': 0,
                         'eilimit': 500})
    titles = sorted(page['title'] for page in data['query']['embeddedin'])
    if not titles:
        raise SystemExit('no page transcludes the container - wrong wiki?')
    return titles


def render(session, title: str, override: dict | None = None) -> dict:
    # The page's text parsed as text, never `page=`: that can answer from the
    # parser cache, which after a template edit still holds the old render - a
    # first local run compared the old templates with themselves and "passed".
    page = api(session, {'action': 'query', 'titles': title, 'prop': 'revisions', 'rvprop': 'content',
                         'rvslots': 'main'})['query']['pages'][0]
    params = {'action': 'parse', 'title': title, 'text': page['revisions'][0]['slots']['main']['content'],
              'contentmodel': 'wikitext', 'prop': 'text|templates', 'disablelimitreport': 1,
              'disableeditsection': 1}
    params.update(override or {})
    data = api(session, params, post=True)['parse']
    time.sleep(session.pause)
    return {'title': title, 'html': data['text'], 'templates': sorted(t['title'] for t in data['templates'])}


def file_for(directory: Path, title: str) -> Path:
    return directory / (title.replace('/', '__').replace('"', 'QUOTE') + '.json')


def save_all(session, out: Path, override: dict | None = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    titles = competition_pages(session)
    for title in titles:
        rendered = render(session, title, override)
        file_for(out, title).write_text(json.dumps(rendered, ensure_ascii=False), encoding='utf-8')
        print(f'  rendered {title}: {len(rendered["html"])} bytes')
    print(f'{len(titles)} pages -> {out}')


def load_all(directory: Path) -> dict[str, dict]:
    pages = {}
    for path in sorted(directory.glob('*.json')):
        page = json.loads(path.read_text(encoding='utf-8'))
        pages[page['title']] = page
    if not pages:
        raise SystemExit(f'nothing captured in {directory}')
    return pages


RECORDS = re.compile(r'(<div class="records-list-container" id="שיאנים">).*?(<div class="games-records-container">)',
                     re.S)


def comparable(page_html: str) -> str:
    """The page with its records section blanked. That section is not part of
    this change and is not stable: two renders of the same page list tied
    players in a different order (measured locally on 10 of 29 pages, new vs
    new). Everything else is compared byte for byte."""
    return RECORDS.sub(r'\1[records]\2', page_html)


def differences(old: dict[str, dict], new: dict[str, dict], expected: set[str],
                new_uses: list[str], new_drops: list[str] | None = None) -> list[str]:
    problems = []
    # Proof the new side ran the new code: without it two identical renders of
    # the old templates pass as "no change". One is required: a page the new
    # side uses and the old does not, one the new side dropped, or a page that
    # must change (each sandbox parse carries the same override, so a change on
    # one page shows it was applied to all).
    new_drops = new_drops or []
    if not (new_uses or new_drops or expected):
        problems.append('no proof that the new side ran the candidate: give --new-uses, --new-drops '
                        'or --expect-change')
    for marker in new_drops:
        had = [title for title, page in old.items() if marker in page['templates']]
        if not had:
            problems.append(f'no old render uses {marker}, so dropping it proves nothing')
        for title in had:
            if title in new and marker in new[title]['templates']:
                problems.append(f'{title}: the new render still uses {marker}')
    for marker in new_uses:
        for title, page in sorted(new.items()):
            if marker not in page['templates']:
                problems.append(f'{title}: the new render does not use {marker}')
        for title, page in sorted(old.items()):
            if marker in page['templates']:
                problems.append(f'{title}: the OLD render already uses {marker}, so it proves nothing')
    if set(old) != set(new):
        problems.append(f'different page sets: {sorted(set(old) ^ set(new))}')
    for title in sorted(set(old) & set(new)):
        same = comparable(old[title]['html']) == comparable(new[title]['html'])
        if title in expected and same:
            problems.append(f'{title}: expected to change and did not')
        if title not in expected and not same:
            problems.append(f'{title}: changed ({first_difference(comparable(old[title]["html"]), comparable(new[title]["html"]))})')
    for title in expected - set(new):
        problems.append(f'{title}: named in --expect-change but not rendered')
    return problems


def first_difference(a: str, b: str) -> str:
    index = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return f'at {index}: old …{a[max(0, index - 60):index + 80]!r} new …{b[max(0, index - 60):index + 80]!r}'


# ------------------------------------------------------------------ check against Cargo

def quote_blind(name: str) -> str:
    name = html.unescape(name)
    return re.sub(r'["\'׳״]', '', name).strip()


def cargo_rows(session, tables: str, fields: str, **extra) -> list[dict]:
    rows, offset = [], 0
    while True:
        data = api(session, {'action': 'cargoquery', 'tables': tables, 'fields': fields, 'limit': 500,
                             'offset': offset, **extra})
        batch = [row['title'] for row in data.get('cargoquery', [])]
        rows.extend(batch)
        time.sleep(session.pause)
        if len(batch) < 500:
            return rows
        offset += 500


def page_names(session) -> dict[str, list[str]]:
    """Each competition page's names, from the map table the container stores."""
    rows = cargo_rows(session, 'Football_Competitions_Map', '_pageName=page, Names=names')
    return {html.unescape(row['page']): [n.strip() for n in html.unescape(row['names'] or '').split(',') if n.strip()]
            for row in rows}


def expected_numbers(session) -> dict:
    games = cargo_rows(session, 'Football_Games',
                       '_pageName=page, Competition=competition, ResultOpt=result, '
                       'ResultMaccabi=goals_for, ResultOpponent=goals_against')
    cards = cargo_rows(session, 'Games_Events,Football_Games', 'Football_Games.Competition=competition, '
                       'Games_Events.SubType=subtype, COUNT(*)=n',
                       join_on='Games_Events._pageID=Football_Games._pageID',
                       where='Games_Events.Team=1 AND Games_Events.SubType IN (71,72,73)',
                       group_by='Football_Games.Competition, Games_Events.SubType')
    return {'games': games, 'cards': cards}


def numbers_for(names: list[str], data: dict) -> dict:
    wanted = {quote_blind(n) for n in names}
    games = [g for g in data['games'] if quote_blind(g['competition'] or '') in wanted]
    number = lambda value: int(value) if value not in (None, '') else None  # noqa: E731
    wins = [g for g in games if g['result'] == '1']
    losses = [g for g in games if g['result'] == '3']
    margins_won = sorted((number(g['goals_for']) - number(g['goals_against']) for g in wins), reverse=True)
    margins_lost = sorted((number(g['goals_against']) - number(g['goals_for']) for g in losses), reverse=True)
    cards = [c for c in data['cards'] if quote_blind(c['competition'] or '') in wanted]
    sum_of = lambda key: sum(number(g[key]) or 0 for g in games)  # noqa: E731
    return {
        'games': len(wins) + len(losses) + sum(1 for g in games if g['result'] == '2'),
        'wins': len(wins), 'draws': sum(1 for g in games if g['result'] == '2'), 'losses': len(losses),
        'goalsFor': sum_of('goals_for'), 'goalsAgainst': sum_of('goals_against'),
        'cleanSheets': sum(1 for g in games if g['goals_against'] == '0'),
        'yellows': sum(int(c['n']) for c in cards if c['subtype'] == '71'),
        'reds': sum(int(c['n']) for c in cards if c['subtype'] in ('72', '73')),
        'biggestWins': margins_won[:10], 'biggestLosses': margins_lost[:10],
        'summaryWins': len(wins), 'summaryDraws': sum(1 for g in games if g['result'] == '2'),
        'summaryLosses': len(losses),
    }


def rendered_numbers(page_html: str) -> dict:
    found = {}
    for label, value in re.findall(r'<span class="describe">([^<]+)</span>\s*<span class="info">([\d,]+)',
                                   page_html):
        if label in STATS_LABELS:
            found[STATS_LABELS[label]] = int(value.replace(',', ''))
    # MediaWiki writes the ids with underscores for spaces.
    for key, anchor in (('biggestWins', 'הניצחונות_הגדולים'), ('biggestLosses', 'ההפסדים_הגדולים')):
        section = page_html.split(f'id="{anchor}"', 1)
        if len(section) < 2:
            continue
        body = section[1].split('<div class="section"', 1)[0].split('<div class="games-records-container"', 1)[0]
        margins = []
        for score in re.findall(r'<span>(\d+):(\d+)</span>', body):
            opponent, maccabi = int(score[0]), int(score[1])
            margins.append(maccabi - opponent if key == 'biggestWins' else opponent - maccabi)
        found[key] = margins
    # The seasonal-numbers summary row (official competitions only), which now
    # reads the numbers the stats box primed: סה"כ, trophies, then W, D, L.
    summary = re.search(r'<div class="table-summary"><span>סה"כ</span><span class="win">[^<]*</span>'
                        r'<span>([\d,]+)</span><span>([\d,]+)</span><span>([\d,]+)</span>', page_html)
    if summary:
        for key, value in zip(('summaryWins', 'summaryDraws', 'summaryLosses'), summary.groups()):
            found[key] = int(value.replace(',', ''))
    return found


def check(directory: Path, wiki: str, pages: dict[str, dict] | None = None) -> list[str]:
    session = session_for(wiki)
    pages = pages or load_all(directory)
    names = page_names(session)
    data = expected_numbers(session)
    problems = []
    for title, page in sorted(pages.items()):
        for marker in LUA_ERRORS:
            if marker in page['html']:
                problems.append(f'{title}: rendered "{marker}"')
        if title not in names:
            problems.append(f'{title}: no Football_Competitions_Map row')
            continue
        expected = numbers_for(names[title], data)
        shown = rendered_numbers(page['html'])
        for key, value in shown.items():
            if expected[key] != value:
                problems.append(f'{title}: {key} shows {value}, Cargo says {expected[key]}')
        missing = (set(STATS_LABELS.values()) | {'biggestWins', 'biggestLosses'}) - set(shown)
        if missing:
            problems.append(f'{title}: the page lacks {sorted(missing)}')
        print(f'  {title}: ' + ', '.join(f'{k}={shown.get(k)}' for k in ('games', 'wins', 'draws', 'losses',
                                                                        'goalsFor', 'yellows')))
    return problems


def report(problems: list[str], what: str) -> None:
    for problem in problems:
        print('  FAIL', problem)
    print(f'{what}: {"FAIL" if problems else "ok"} ({len(problems)} problems)')
    if problems:
        sys.exit(1)


def selftest(old_dir: Path, new_dir: Path) -> None:
    old, new = load_all(old_dir), load_all(new_dir)
    titles = sorted(old)
    marker = 'יחידה:FootballCompetition'
    swapped = dict(new)
    swapped[titles[0]] = new[titles[1]]
    if not differences(old, swapped, set(), [marker]):
        raise SystemExit('selftest FAILED: diff passed a page rendered as another page')
    if not differences(old, old, {titles[0]}, [marker]):
        raise SystemExit('selftest FAILED: diff passed an expected change that did not happen')
    if not differences(new, new, set(), [marker]):
        raise SystemExit('selftest FAILED: diff passed a marker the old side already had')
    if not differences(old, old, set(), []):
        raise SystemExit('selftest FAILED: diff passed with no proof at all')
    if not differences(old, old, set(), [], ['תבנית:מפעל כדורגל/הצגת סטטיסטיקה']):
        raise SystemExit('selftest FAILED: diff passed a dropped page the new side still uses')

    def altered(title: str, find: str, replace: str) -> dict:
        page = dict(new[title])
        page['html'] = page['html'].replace(find, replace, 1)
        if page['html'] == new[title]['html']:
            raise SystemExit(f'selftest FAILED: "{find}" not on {title} - the markup changed?')
        return {title: page}

    melchett = next(t for t in titles if 'מלצ' in t)
    official = next(t for t in titles if 'class="table-summary"' in new[t]['html'])
    cases = {
        'an altered wins number': altered(melchett, '<span class="describe">ניצחונות</span>\n<span class="info">',
                                          '<span class="describe">ניצחונות</span>\n<span class="info">1'),
        'an altered biggest-win score': altered(melchett, '<span>2:9</span>', '<span>2:8</span>'),
    }
    summary = re.search(r'(<span>סה"כ</span><span class="win">[^<]*</span><span>)(\d+)',
                        new[official]['html'])
    cases['an altered seasonal summary'] = altered(official, summary.group(0),
                                                   summary.group(1) + str(int(summary.group(2)) + 1))
    for label, pages in cases.items():
        if not check(new_dir, 'local', pages):
            raise SystemExit(f'selftest FAILED: check passed {label}')
    print('selftest ok: diff caught a swapped page, a missing change, a stale and a missing marker; '
          'check caught ' + ', '.join(cases))


CANDIDATES = Path('infra/lua_modules/wiki_templates/football_competition')


def title_of(candidate: Path) -> str:
    return 'תבנית:' + candidate.stem.replace('__', '/').replace('_', ' ')


def local_switch(to: str) -> None:
    """The local wiki only: write every candidate under its real title (new), or
    production's current text of each (old; a candidate prod lacks is deleted)."""
    sys.path.insert(0, 'infra/lua_modules')
    import deploy_modules as local  # noqa: E402 - local-only writer, edit.php in the container

    prod = session_for('prod')
    for candidate in sorted(CANDIDATES.glob('*.wiki')):
        title = title_of(candidate)
        if to == 'new':
            local.write_page(title, candidate.read_text(encoding='utf-8'))
            print(f'  local {title} <- {candidate.name}')
            continue
        page = api(prod, {'action': 'query', 'titles': title, 'prop': 'revisions', 'rvprop': 'content',
                          'rvslots': 'main'})['query']['pages'][0]
        if page.get('missing'):
            if local.read_page(title) is not None:
                local.delete_page(title)
            print(f'  local {title} deleted (not on prod)')
        else:
            local.write_page(title, page['revisions'][0]['slots']['main']['content'])
            print(f'  local {title} <- prod')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='mode', required=True)
    capture = sub.add_parser('capture')
    capture.add_argument('--wiki', choices=WIKIS, required=True)
    capture.add_argument('--out', type=Path, required=True)
    sandbox = sub.add_parser('sandbox')
    sandbox.add_argument('--template', required=True)
    sandbox.add_argument('--candidate', type=Path, required=True)
    sandbox.add_argument('--out', type=Path, required=True)
    diff = sub.add_parser('diff')
    diff.add_argument('old', type=Path)
    diff.add_argument('new', type=Path)
    diff.add_argument('--expect-change', nargs='*', default=[])
    diff.add_argument('--new-drops', nargs='+', default=[], help='pages the new renders no longer transclude')
    diff.add_argument('--new-uses', nargs='+', default=[],
                      help='pages every new render must transclude and no old render does')
    checker = sub.add_parser('check')
    checker.add_argument('dir', type=Path)
    checker.add_argument('--wiki', choices=WIKIS, required=True)
    test = sub.add_parser('selftest')
    test.add_argument('old', type=Path)
    test.add_argument('new', type=Path)
    switch = sub.add_parser('local-switch')
    switch.add_argument('to', choices=('old', 'new'))
    options = parser.parse_args()

    if options.mode == 'local-switch':
        local_switch(options.to)
    elif options.mode == 'capture':
        save_all(session_for(options.wiki), options.out)
    elif options.mode == 'sandbox':
        override = {'templatesandboxtitle': options.template,
                    'templatesandboxtext': options.candidate.read_text(encoding='utf-8'),
                    'templatesandboxcontentmodel': 'wikitext'}
        save_all(session_for('prod'), options.out, override)
    elif options.mode == 'diff':
        report(differences(load_all(options.old), load_all(options.new), set(options.expect_change),
                           options.new_uses, options.new_drops), 'diff')
    elif options.mode == 'check':
        report(check(options.dir, options.wiki), 'check')
    else:
        selftest(options.old, options.new)


if __name__ == '__main__':
    main()
