"""The final table of every European (and Asian) group Maccabi Tel Aviv played in, on its football season page.

    uv run python infra/season_pages/european_group_tables.py check
    uv run python infra/season_pages/european_group_tables.py renderer --out FILE
    uv run python infra/season_pages/european_group_tables.py candidate --out FILE --compare 2016/17 [--compare ...]
    uv run --with playwright python infra/season_pages/european_group_tables.py preview --season 2016/17 --out DIR
    uv run python infra/season_pages/european_group_tables.py publish --season 2016/17
    uv run python infra/season_pages/european_group_tables.py publish --all

The tables live in european_group_tables.json (source: en.wikipedia's group
tables, Maccabi's own results checked against our game pages; 1980/81 corrected
from the press). Each season gets `תבנית:טבלת בית בינלאומי כדורגל <season>`,
the same shape as the league's `תבנית:טבלת ליגת כדורגל <season>`: the page
renders the generic league-table renderer, and `{{... |כותרת}}` returns the
section title ("ליגת האלופות - בית ג'"). `תבנית:עונת כדורגל` shows it as its
own section after the league table, when the season has one. A 36-club league
phase shows only the rows around Maccabi, numbered from `מיקום ראשון`.

check     - validates the data (no wiki access).
renderer  - writes the renderer with `מיקום ראשון` and proves every league table
            on the wiki renders byte for byte the same with it.
candidate - writes the new תבנית:עונת כדורגל, built from the live text, and
            proves the --compare season pages render the same with it.
            Both files are for switch_template_prod.py.
preview   - renders the section on production with the renderer candidate in
            a TemplateSandbox (no wiki write), puts it into the live season
            page in a browser and screenshots it.
publish   - creates the season templates (createonly), one page per season.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
DATA_FILE = HERE / 'european_group_tables.json'
TEMPLATE_PREFIX = 'תבנית:טבלת בית בינלאומי כדורגל '
SEASON_TEMPLATE = 'תבנית:עונת כדורגל'
MACCABI = 'מכבי תל אביב'
SUMMARY = 'MaccabiBot - טבלת שלב הבתים במפעל הבינלאומי של העונה'

# A league phase (36 clubs) shows this many rows around Maccabi, with their real positions.
WINDOW = 7

# תבנית:עונת כדורגל: the title is looked up once and kept in a variable; an
# empty title (no template for the season) leaves the TOC and the page as today.
SEASON_VARS_END = '-->{{#vardefine: עונה בפורמט שליפה |{{#replace: {{#var: עונה להצגה}} |/|-}} }}<!--\n'
LEAGUE_TOC_ENTRY = '{{#קיים: תבנית: טבלת ליגת כדורגל {{#var: עונה להצגה}} |טבלת הליגה}},'
LEAGUE_SECTION_END = ('|טקסט={{טבלת ליגת כדורגל {{#var: עונה להצגה}} }}\n}}\n}}<!--\n')
GROUP_CALL = 'טבלת בית בינלאומי כדורגל {{#var: עונה להצגה}}'
GROUP_VAR = ('-->{{#vardefine: טבלת בית בינלאומי |{{#קיים: תבנית: ' + GROUP_CALL
             + ' |{{' + GROUP_CALL + ' |כותרת}} }} }}<!--\n')
GROUP_TOC_ENTRY = '{{#var: טבלת בית בינלאומי}},'
GROUP_SECTION = ('\n-->{{#תנאי: {{#var: טבלת בית בינלאומי}} |{{פרק\n|כותרת={{#var: טבלת בית בינלאומי}}'
                 '\n|טקסט={{' + GROUP_CALL + ' }}\n}}\n}}<!--\n')

# תבנית:טבלת ליגת כדורגל: an optional `מיקום ראשון` is the position of the first
# row, for a table that shows a slice. Without it (every league table) rows are
# numbered from 1, as before. Not a 9th row field: three live league tables
# (1946/47, 1970/71, 1974/75) already carry a stray 9th field in one row.
RENDERER = 'תבנית:טבלת ליגת כדורגל'
RENDERER_ROW_START = '|^}}<!--\n-->{{#תנאי: {{#arraysize: פלייאופים}}'
RENDERER_POSITION_VAR = ('|^}}<!--\n-->{{#vardefine: מיקום מוצג |{{#expr: {{#var: מיקום בלולאה}}'
                         ' + {{{מיקום ראשון|1}}} }} }}<!--\n'
                         '-->{{#תנאי: {{#arraysize: פלייאופים}}')
RENDERER_CHAMPION = '{{#שווה: {{#var: מיקום בלולאה}} |0 | champion}}'
RENDERER_CHAMPION_NEW = '{{#שווה: {{#var: מיקום מוצג}} |1 | champion}}'
RENDERER_POSITION = '<span class="position">{{#expr: {{#var: מיקום בלולאה}} + 1}}</span>'
RENDERER_POSITION_NEW = '<span class="position">{{#var: מיקום מוצג}}</span>'
LEAGUE_TABLES_CATEGORY = 'קטגוריה:טבלאות ליגת כדורגל'


def load() -> dict:
    return json.loads(DATA_FILE.read_text(encoding='utf-8'))


def problems(season: str, group: dict) -> list[str]:
    """Everything that would make the table wrong on its face."""
    found = []
    rows = group['rows']
    for row in rows:
        if row['played'] != row['wins'] + row['draws'] + row['losses']:
            found.append(f'{row["team"]}: played is not wins + draws + losses')
        if row['points'] != row['wins'] * group['win_points'] + row['draws']:
            found.append(f'{row["team"]}: points do not follow from the results')
        if any(separator in row['team'] for separator in ',^|'):
            found.append(f'{row["team"]}: the name carries a table separator')
    if sum(row['wins'] for row in rows) != sum(row['losses'] for row in rows):
        found.append('wins and losses do not balance')
    if sum(row['draws'] for row in rows) % 2:
        found.append('an odd number of draws')
    if sum(row['goals_for'] for row in rows) != sum(row['goals_against'] for row in rows):
        found.append('goals for and against do not balance')
    points = [row['points'] for row in rows]
    if points != sorted(points, reverse=True):
        found.append('rows are not in points order')
    if [row['team'] for row in rows].count(MACCABI) != 1:
        found.append(f'{MACCABI} is not in the table exactly once')
    if ',' in group['title'] or not group['title'].strip():
        found.append('the title is empty or carries a comma (it is a table-of-contents entry)')
    return [f'{season}: {problem}' for problem in found]


def shown_rows(group: dict) -> tuple[int, list[dict]]:
    """The first shown position and the rows: all of a group, or WINDOW rows
    around Maccabi in a league phase."""
    rows = group['rows']
    if len(rows) <= WINDOW + 1:
        return 1, rows
    maccabi = [row['team'] for row in rows].index(MACCABI)
    start = min(max(maccabi - WINDOW // 2, 0), len(rows) - WINDOW)
    return start + 1, rows[start:start + WINDOW]


def table_call(group: dict) -> str:
    first, rows = shown_rows(group)
    trimmed = len(rows) < len(group['rows'])
    table = ',\n'.join('^'.join(str(value) for value in (
        row['team'], row['played'], row['wins'], row['draws'], row['losses'],
        row['goals_for'], row['goals_against'], row['points'])) for row in rows)
    notes = list(group['notes'])
    if trimmed:
        notes.append(f'מוצגים המקומות {first}-{first + len(rows) - 1} מתוך {len(group["rows"])}.')
    note_lines = ''.join(f'\n* {note}' for note in notes)
    first_line = f'\n|מיקום ראשון={first}' if trimmed else ''
    return (f'{{{{טבלת ליגת כדורגל\n|מספר יורדות=0{first_line}\n|הערות=<nowiki> </nowiki>{note_lines}'
            f'\n|טבלה={table}\n}}}}')


def template_text(group: dict) -> str:
    return (f'{{{{#switch: {{{{{{1|}}}}}}\n|כותרת={group["title"]}\n|#default={table_call(group)}\n}}}}'
            f'<noinclude>\nמקור: {group["source"]}\n</noinclude>')


def _replace_once(text: str, old: str, new: str, page: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f'expected exactly one {old!r} in {page}')
    return text.replace(old, new)


def season_template_candidate(live: str) -> str:
    """The live תבנית:עונת כדורגל with the group table's title variable, TOC entry and section added."""
    if GROUP_CALL in live:
        raise ValueError('the season template already shows the group table')
    text = _replace_once(live, SEASON_VARS_END, SEASON_VARS_END + GROUP_VAR, SEASON_TEMPLATE)
    text = _replace_once(text, LEAGUE_TOC_ENTRY, LEAGUE_TOC_ENTRY + ' ' + GROUP_TOC_ENTRY, SEASON_TEMPLATE)
    return _replace_once(text, LEAGUE_SECTION_END,
                         LEAGUE_SECTION_END[:-len('<!--\n')] + '<!--' + GROUP_SECTION, SEASON_TEMPLATE)


def renderer_candidate(live: str) -> str:
    """The live league-table renderer, taking an optional shown position per row."""
    if 'מיקום מוצג' in live:
        raise ValueError('the renderer already takes a shown position')
    text = _replace_once(live, RENDERER_ROW_START, RENDERER_POSITION_VAR, RENDERER)
    text = _replace_once(text, RENDERER_CHAMPION, RENDERER_CHAMPION_NEW, RENDERER)
    return _replace_once(text, RENDERER_POSITION, RENDERER_POSITION_NEW, RENDERER)


def live_text(title: str) -> str:
    from season_api import call

    data = call('prod', {'action': 'query', 'titles': title, 'prop': 'revisions',
                         'rvprop': 'content', 'rvslots': 'main'})
    return data['query']['pages'][0]['revisions'][0]['slots']['main']['content']


def parse(title: str, text: str, renderer: str | None) -> str:
    """Production's rendering of `text`, with the renderer candidate sandboxed in when given."""
    from season_api import call

    override = ({'templatesandboxtitle': RENDERER, 'templatesandboxtext': renderer,
                 'templatesandboxcontentmodel': 'wikitext'} if renderer else {})
    data = call('prod', dict({'action': 'parse', 'title': title, 'text': text, 'contentmodel': 'wikitext',
                              'prop': 'text', 'disablelimitreport': '1'}, **override), post=True)
    return data['parse']['text']


def league_table_templates() -> list[str]:
    from season_api import call

    titles, cont = [], {}
    while True:
        data = call('prod', dict({'action': 'query', 'list': 'categorymembers', 'cmtitle': LEAGUE_TABLES_CATEGORY,
                                  'cmnamespace': 10, 'cmlimit': 'max'}, **cont))
        titles += [row['title'] for row in data['query']['categorymembers']]
        if 'continue' not in data:
            return sorted(titles)
        cont = data['continue']


def compare_renderer(renderer: str, out: Path) -> int:
    """Every league table on the wiki must render byte for byte the same with the candidate renderer."""
    titles = league_table_templates()
    text = '\n'.join(f'<div class="compare-{index}">\n{{{{{title.split(":", 1)[1]}}}}}\n</div>'
                     for index, title in enumerate(titles))
    before, after = parse('ארגז חול', text, None), parse('ארגז חול', text, renderer)
    out.with_suffix('.before.html').write_text(before, encoding='utf-8')
    out.with_suffix('.after.html').write_text(after, encoding='utf-8')
    if 'class="error"' in after:
        print('the candidate renders an error')
        return 1
    print(f'{len(titles)} league tables: {"identical" if before == after else "DIFFERENT"}')
    return 0 if before == after else 1


def compare_season_pages(candidate: str, seasons: list[str]) -> int:
    """Before any group template exists, the candidate season template must render
    these season pages byte for byte as the live one does."""
    from season_api import call

    failures = 0
    for season in seasons:
        title = f'עונת {season}'
        text = live_text(title)
        renders = []
        for override in ({}, {'templatesandboxtitle': SEASON_TEMPLATE, 'templatesandboxtext': candidate,
                              'templatesandboxcontentmodel': 'wikitext'}):
            data = call('prod', dict({'action': 'parse', 'title': title, 'text': text,
                                      'contentmodel': 'wikitext', 'prop': 'text|categories',
                                      'disablelimitreport': '1'}, **override), post=True)['parse']
            renders.append((data['text'], sorted(row['category'] for row in data['categories'])))
        same = renders[0] == renders[1]
        failures += not same
        print(f'{title}: {"identical" if same else "DIFFERENT"}', flush=True)
    return 1 if failures else 0


def section_text(group: dict) -> str:
    return f'{{{{פרק\n|כותרת={group["title"]}\n|טקסט={table_call(group)}\n}}}}'


def screenshot(season: str, html: str, title: str, out: Path) -> Path:
    """Open the live season page and put the rendered section after its league
    table, so the shot carries the production skin and styles."""
    from urllib.parse import quote

    from playwright.sync_api import sync_playwright

    path = out / f'{season.replace("/", "-")}.png'
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={'width': 1300, 'height': 3200})
        page.goto(f'https://www.maccabipedia.co.il/{quote("עונת_" + season)}', wait_until='networkidle')
        # The season template puts the section right before the players' records.
        page.evaluate('html => { const box = document.createElement("div"); box.innerHTML = html;'
                      ' document.querySelector("#mw-content-text .players-records-container")'
                      '.before(...box.querySelector(".mw-parser-output").childNodes); }', html)
        section = page.locator('.simple-styled-paragraph').filter(
            has=page.locator('h3 span.title', has_text=title))
        if section.count() != 1:
            raise SystemExit(f'{season}: {section.count()} sections titled {title!r} on the page')
        section.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        section.screenshot(path=str(path))
        # The page from the top down to the section after the new one, to see it in place.
        box = section.bounding_box()
        page.screenshot(path=str(path.with_name(path.stem + '-page.png')), full_page=True,
                        clip={'x': 0, 'y': 0, 'width': 1300, 'height': box['y'] + box['height'] + 250})
        browser.close()
    return path


def publish(connection, season: str, group: dict) -> str:
    """Create one season template, multipart (the firewall refuses urlencoded
    edits), never over an existing page, and read it back."""
    import pywikibot as pw
    from pywikibot.comms import http as pw_http

    title = TEMPLATE_PREFIX + season
    wanted = template_text(group)
    if pw.Page(connection, title).exists():
        return 'EXISTS - left alone'
    fields = {'action': (None, 'edit'), 'title': (None, title), 'text': (None, wanted),
              'summary': (None, SUMMARY), 'token': (None, connection.tokens['csrf']),
              'format': (None, 'json'), 'bot': (None, '1'), 'createonly': (None, '1')}
    response = pw_http.session.post(connection.base_url('/api.php'), files=fields,
                                    headers={'Accept': 'application/json'}, timeout=120)
    if 'application/json' not in response.headers.get('Content-Type', ''):
        return f'REFUSED ({response.status_code}, {response.headers.get("Content-Type", "?")})'
    answer = response.json()
    if 'error' in answer:
        return f'ERROR {answer["error"].get("code")}'
    time.sleep(1)
    fresh = pw.Page(connection, title)
    fresh.get(force=True)
    return 'ok' if fresh.text.strip() == wanted.strip() else 'MISMATCH'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('check')
    candidate_parser = commands.add_parser('candidate')
    candidate_parser.add_argument('--out', type=Path, required=True)
    candidate_parser.add_argument('--compare', action='append', default=[],
                                  help='a season whose page must render unchanged (repeatable)')
    renderer_parser = commands.add_parser('renderer')
    renderer_parser.add_argument('--out', type=Path, required=True)
    preview_parser = commands.add_parser('preview')
    preview_parser.add_argument('--season', action='append', required=True)
    preview_parser.add_argument('--out', type=Path, required=True)
    publish_parser = commands.add_parser('publish')
    which = publish_parser.add_mutually_exclusive_group(required=True)
    which.add_argument('--season')
    which.add_argument('--all', action='store_true')
    options = parser.parse_args()

    groups = load()
    found = [problem for season, group in groups.items() for problem in problems(season, group)]
    if found:
        raise SystemExit('\n'.join(found))
    if options.command == 'check':
        print(f'{len(groups)} seasons, {sum(len(g["rows"]) for g in groups.values())} rows - consistent')
        return

    sys.path.insert(0, str(HERE))
    if options.command == 'candidate':
        candidate = season_template_candidate(live_text(SEASON_TEMPLATE))
        options.out.write_text(candidate, encoding='utf-8')
        print(f'wrote {options.out}')
        raise SystemExit(compare_season_pages(candidate, options.compare))
    if options.command == 'renderer':
        renderer = renderer_candidate(live_text(RENDERER))
        options.out.write_text(renderer, encoding='utf-8')
        print(f'wrote {options.out}')
        raise SystemExit(compare_renderer(renderer, options.out))
    if options.command == 'preview':
        options.out.mkdir(parents=True, exist_ok=True)
        season_template_candidate(live_text(SEASON_TEMPLATE))
        renderer = renderer_candidate(live_text(RENDERER))
        for season in options.season:
            html = parse(f'עונת {season}', section_text(groups[season]), renderer)
            (options.out / f'{season.replace("/", "-")}.html').write_text(html, encoding='utf-8')
            if 'class="error"' in html or 'scribunto-error' in html:
                raise SystemExit(f'{season}: the render carries an error')
            print(screenshot(season, html, groups[season]['title'], options.out))
        return

    sys.path.insert(0, str(HERE.parent / 'football_queries'))
    import deploy_modules_prod as deploy

    connection = deploy.site()
    seasons = list(groups) if options.all else [options.season]
    for season in seasons:
        outcome = publish(connection, season, groups[season])
        print(f'{season}: {outcome}', flush=True)
        if outcome != 'ok':
            raise SystemExit('stopping at the first page that did not land cleanly')
        time.sleep(3)


if __name__ == '__main__':
    main()
