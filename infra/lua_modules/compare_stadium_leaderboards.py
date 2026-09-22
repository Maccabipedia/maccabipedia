"""Old stadium leaderboard boxes against the one-invoke tabbers, on production.

    uv run python infra/lua_modules/compare_stadium_leaderboards.py --sandbox
    uv run python infra/lua_modules/compare_stadium_leaderboards.py --sandbox --selftest
    uv run python infra/lua_modules/compare_stadium_leaderboards.py --full

READ-ONLY: every render is action=parse&text=, nothing is saved; production
calls go through season_api (3 s apart, backing off on HTTP 508).

--sandbox is the gate BEFORE anything is published. Per stadium page it
renders only the שיאנים section: OLD through the live box templates, NEW
through the invoke with Module:FootballStatsBlocks overridden by the repo's
file (TemplateSandbox) - the one page that holds the new block. Both sides
first define the page's אצטדיונים לשליפה with the template's own preamble,
its parameters filled from the page's call.

--full is the gate AFTER the block data is published and BEFORE the template
is switched: the whole page, with תבנית:אצטדיון כדורגל overridden by the
candidate. Everything outside the section must be byte-identical, and the
section is compared as below.

The section is compared per box and tab with the referee harness's rules
(title; heading with its distinct-player count; ranked rows; the "עוד" link's
query), allowing only the departures accepted on season and referee pages:
ties ordered by name, and no "עוד" on a tab with exactly ten players.

Refuses to pass over nothing: the NEW side must be the tabber version, a
rendering carrying an error fails, a run that compared no row fails, and the
run must include a stadium whose name carries a quote and one with no rows.
--selftest compares one stadium's OLD with another's NEW and must FAIL.
"""
from __future__ import annotations

import argparse
import html as html_module
import re
import statistics
import sys
import urllib.parse
from pathlib import Path

import mwparserfromhell

sys.path.insert(0, str(Path('infra/lua_modules')))
sys.path.insert(0, str(Path('infra/season_pages')))
sys.path.insert(0, str(Path('infra/tabs')))
from compare_referee_leaderboards import compare_tab, HEADER, MORE, ROW, TITLE  # noqa: E402
from convert_stadium_section import (  # noqa: E402
    SECTION_OPEN, TEMPLATE, candidate_of, prod_template, section_texts,
)
from season_api import call  # noqa: E402
from verify_tabs import ERROR_MARKERS  # noqa: E402

BLOCKS_PAGE = 'Module:FootballStatsBlocks'
BLOCKS_FILE = Path('infra/lua_modules/Module_FootballStatsBlocks.lua')
# The modules the new side runs besides the block data: production must hold
# the repo's copies, or the stub tests describe code that is not live.
OTHER_MODULES = {
    'Module:FootballStatsBlock': 'Module_FootballStatsBlock.lua',
    'Module:FootballQueries': 'Module_FootballQueries.lua',
    'Module:FootballQueries/Fields': 'Module_FootballQueries_Fields.lua',
}
# Parser functions trim their arguments, so a whitespace delimiter would glue
# the names together; this one survives.
LIST_SEPARATOR = '@@name@@'
LIST_PROBE = '{{#arrayprint: אצטדיונים לשליפה|' + LIST_SEPARATOR + '}}'
OFFICIAL_HEADING = re.compile(r'^משחקים רשמיים \((\d+) מופיעים שונים\)$')

OLD_BOX = re.compile(r'<div class="record-section-container">(.*?)'
                     r'(?=<div class="record-section-container"|\Z)', re.S)
NEW_BOX = re.compile(r'<div class="records-list-tabs-container"[^>]*>(.*?)'
                     r'(?=<div class="records-list-tabs-container"|\Z)', re.S)
OLD_PANEL = re.compile(r'<div id="tab\d-content">(.*?)(?=<div id="tab\d-content">|\Z)', re.S)
NEW_PANEL = re.compile(r'<article[^>]*class="tabber__panel"[^>]*>(.*?)</article>', re.S)
SECTION = re.compile(r'<div class="details-records-lists-container" id="שיאנים">'
                     r'.*?(?=<div class="games-records-container">)', re.S)
# The template's preamble: from <includeonly> up to the profile-image lookup.
PREAMBLE = re.compile(r'<includeonly>(.*?)<!--\s*-->\{\{#קיים: קובץ:', re.S)


def page_text(title: str) -> str:
    data = call('prod', {'action': 'query', 'titles': title, 'prop': 'revisions',
                         'rvprop': 'content', 'rvslots': 'main'})
    return data['query']['pages'][0]['revisions'][0]['slots']['main']['content']


def stadium_pages() -> list[str]:
    """Every page the template switch touches. Any outside the main namespace
    is refused rather than skipped: it would change without being compared."""
    titles, cont = [], {}
    while True:
        data = call('prod', dict({'action': 'query', 'list': 'embeddedin', 'eititle': TEMPLATE,
                                  'eilimit': 'max'}, **cont))
        titles += [(row['ns'], row['title']) for row in data['query']['embeddedin']]
        if 'continue' not in data:
            break
        cont = data['continue']
    elsewhere = [title for ns, title in titles if ns != 0]
    if elsewhere:
        raise SystemExit(f'the template is also used outside articles: {elsewhere[:5]}')
    return sorted(title for _, title in titles)


def preamble_for(template_body: str, page_wikitext: str) -> str:
    """The template's own variable definitions, with the page's parameters
    filled in - the same array both sides of the comparison then read."""
    match = PREAMBLE.search(template_body)
    if not match:
        raise SystemExit('the stadium template\'s preamble moved - refusing')
    calls = [node for node in mwparserfromhell.parse(page_wikitext).filter_templates()
             if node.name.strip().replace('_', ' ') in ('אצטדיון כדורגל', 'תבנית:אצטדיון כדורגל')]
    if len(calls) != 1:
        raise ValueError(f'{len(calls)} calls of the stadium template on the page')
    given = {str(param.name).strip(): str(param.value).strip()
             for param in calls[0].params}
    preamble = mwparserfromhell.parse(match.group(1))
    for argument in preamble.filter_arguments(recursive=True):
        name = str(argument.name).strip()
        if name in given:
            value = given[name]
        elif argument.default is not None:
            value = str(argument.default)
        else:
            value = str(argument)
        preamble.replace(argument, value)
    text = str(preamble)
    if '#arraydefine: אצטדיונים לשליפה' not in text:
        raise SystemExit('the preamble no longer defines אצטדיונים לשליפה - refusing')
    return text


def stadium_names(title: str, preamble: str) -> list[str]:
    """The names the page filters by, as the wiki builds them."""
    data = call('prod', {'action': 'expandtemplates', 'title': title,
                         'text': preamble + LIST_PROBE, 'prop': 'wikitext'}, post=True)
    names = [html_module.unescape(name).strip()
             for name in data['expandtemplates']['wikitext'].split(LIST_SEPARATOR)]
    names = [name for name in names if name]
    # An unset parameter without a default would reach the list as literal
    # text - both sides would then filter by it and agree on nothing.
    if not names or any('{{{' in name for name in names):
        raise ValueError(f'the stadium list is {names!r}')
    return names


def direct_appearances(names: list[str]) -> int:
    """Distinct Maccabi players with an appearance in an official game at
    these stadiums, counted straight from Cargo - written apart from both the
    templates and the module, so a filter both get wrong the same way (a name
    stripped wrongly, matching nothing) cannot pass as agreement."""
    literals = ', '.join('"' + name.replace("'", '').replace('"', '') + '"' for name in names)
    data = call('prod', {'action': 'cargoquery',
                         'tables': 'Football_Games=fg, Games_Events=ge, Competitions=c',
                         'join_on': 'fg._pageID=ge._pageID, fg.Competition=c.OriginalName',
                         'where': f'fg.Stadium IN ({literals}) AND c.Official=1 '
                                  'AND ge.EventType IN (1,5) AND ge.Team=1',
                         'fields': 'COUNT(DISTINCT ge.PlayerName)=n', 'limit': '1'})
    return int(data['cargoquery'][0]['title']['n'])


# Columns the templates filter with IN (one name) where the module writes
# `= name` - the same rows. Set by a caller whose filter is a single value
# (the referee harness); stadium lists stay IN on both sides.
SINGLE_IN_COLUMNS: tuple[str, ...] = ()


def unify_link_quotes(href: str) -> str:
    """The templates quote the stadium names in the link's WHERE with ', the
    module with ": the same SQL. Only those string literals are rewritten."""
    parts = urllib.parse.urlsplit(html_module.unescape(href))
    params = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)

    def where(value: str) -> str:
        # Only a whole single-quoted list item - `('a', 'b')` - never an
        # apostrophe inside a name (`"ג'ורג' אשקר"`).
        value = re.sub(r"(?<=[(,])(\s*)'([^'\"]*)'(?=\s*[,)])", r'\1"\2"', value)
        for column in SINGLE_IN_COLUMNS:
            value = re.sub(re.escape(column) + r'\s+IN\s*\(\s*("(?:[^"\\]|\\.)*")\s*\)',
                           column + r' = \1', value)
        return value

    params = [(key, where(value) if key == 'where' else value) for key, value in params]
    return parts._replace(query=urllib.parse.urlencode(params)).geturl()


def parse(title: str, text: str, override: dict | None = None) -> tuple[str, float]:
    # disablelimitreport drops the timing comment from the HTML (it differs on
    # every render); the walltime still comes back in limitreportdata.
    params = dict({'action': 'parse', 'title': title, 'text': text,
                   'contentmodel': 'wikitext', 'prop': 'text|limitreportdata',
                   'disablelimitreport': '1'}, **(override or {}))
    data = call('prod', params, post=True)['parse']
    report = {row['name']: row.get('0') for row in data['limitreportdata']}
    return data['text'], float(report['limitreport-walltime'])


def boxes_of(page: str, box: re.Pattern, panel: re.Pattern) -> list[dict]:
    boxes = []
    for body in box.findall(page):
        tabs = []
        for panel_body in panel.findall(body):
            header = HEADER.search(panel_body)
            link = MORE.search(panel_body)
            tabs.append({'header': header.group(1).strip() if header else None,
                         'rows': [(html_module.unescape(name).strip(), count.strip())
                                  for name, count in ROW.findall(panel_body)],
                         'more': bool(link),
                         'href': unify_link_quotes(link.group(1)) if link else None})
        title = TITLE.search(body)
        boxes.append({'title': title.group(1) if title else None, 'tabs': tabs})
    return boxes


def compare_sections(old_page: str, new_page: str, expected: int,
                     old_box: re.Pattern | None = None) -> tuple[str, str, int]:
    """`expected`: the official appearances count Cargo gives directly; both
    sides' official appearances heading must state it."""
    for label, page in (('old', old_page), ('new', new_page)):
        errors = [marker for marker in ERROR_MARKERS if marker in page]
        if errors:
            return 'ERROR', f'{label} rendering carries {errors}', 0
    if 'tabber__panel' not in new_page or 'slim-tabs' in new_page:
        return 'FAIL', 'the new section is not the tabber version', 0
    if re.search(r'</article>\s*<p class="mw-empty-elt">', new_page) or \
            re.search(r'עוד</a></p>', new_page):
        return 'FAIL', 'the parser wrapped the "עוד" link in a paragraph', 0
    old_boxes = boxes_of(old_page, old_box or OLD_BOX, OLD_PANEL)
    new_boxes = boxes_of(new_page, NEW_BOX, NEW_PANEL)
    if len(old_boxes) != 4 or len(new_boxes) != 4:
        return 'FAIL', f'{len(old_boxes)} old boxes, {len(new_boxes)} new', 0
    for label, boxes in (('old', old_boxes), ('new', new_boxes)):
        heading = OFFICIAL_HEADING.match((boxes[0]['tabs'] or [{}])[0].get('header') or '')
        if not heading or int(heading.group(1)) != expected:
            return 'FAIL', (f'{label} official appearances heading '
                            f'{boxes[0]["tabs"][0]["header"]!r}, Cargo counts {expected}'), 0
    rows = 0
    for old_box, new_box in zip(old_boxes, new_boxes):
        if old_box['title'] != new_box['title']:
            return 'FAIL', f'title {old_box["title"]!r} vs {new_box["title"]!r}', rows
        if len(old_box['tabs']) != 4 or len(new_box['tabs']) != 4:
            return 'FAIL', f'{old_box["title"]}: tab counts', rows
        for old_tab, new_tab in zip(old_box['tabs'], new_box['tabs']):
            rows += len(old_tab['rows'])
            problem = compare_tab(old_tab, new_tab)
            if problem:
                return 'FAIL', f'{old_box["title"]} / {old_tab["header"]}: {problem}', rows
    return 'ok', f'{rows} rows', rows


def check_prod_modules(sandbox: bool, new_block: str = 'stadium') -> None:
    """The renderer on production must be the repo's; in --sandbox the block
    data must be the repo's minus the stadium block (so the override adds
    only that), in --full it must already be the repo's."""
    for page, name in OTHER_MODULES.items():
        repo = (Path('infra/lua_modules') / name).read_text(encoding='utf-8').strip()
        if page_text(page).strip() != repo:
            raise SystemExit(f'{page} on production differs from the repo - refusing')
    live = page_text(BLOCKS_PAGE).strip()
    local = BLOCKS_FILE.read_text(encoding='utf-8').strip()
    if not sandbox and live != local:
        raise SystemExit(f'{BLOCKS_PAGE} is not published yet - run --sandbox, or publish')
    if sandbox and f"['{new_block}']" in live:
        raise SystemExit(f'{BLOCKS_PAGE} already holds the {new_block} block - use --full')


def sandbox_side(title: str, template_body: str, new: bool) -> tuple[str, str, float]:
    """(section html, outside html, walltime) of one side, section only."""
    old_section, new_section = section_texts(template_body)
    text = preamble_for(template_body, page_text(title)) + (new_section if new else old_section)
    override = {'templatesandboxtitle': BLOCKS_PAGE,
                'templatesandboxtext': BLOCKS_FILE.read_text(encoding='utf-8'),
                'templatesandboxcontentmodel': 'Scribunto'} if new else None
    page, wall = parse(title, text, override)
    return page, '', wall


def full_side(title: str, candidate: str, new: bool) -> tuple[str, str, float]:
    """(section html, the page without it, walltime) of one side, whole page."""
    override = {'templatesandboxtitle': TEMPLATE, 'templatesandboxtext': candidate,
                'templatesandboxcontentmodel': 'wikitext'} if new else None
    page, wall = parse(title, page_text(title), override)
    sections = SECTION.findall(page)
    if len(sections) != 1:
        raise ValueError(f'{"new" if new else "old"} page holds {len(sections)} '
                         'שיאנים sections, not one')
    return sections[0], SECTION.sub('', page), wall


def compare_page(old_title: str, new_title: str, side, expected: int):
    old_section, old_outside, old_wall = side(old_title, False)
    new_section, new_outside, new_wall = side(new_title, True)
    verdict, detail, rows = compare_sections(old_section, new_section, expected)
    if verdict == 'ok' and old_outside != new_outside:
        verdict, detail = 'FAIL', 'the page outside the section differs'
    return verdict, detail, rows, old_wall, new_wall


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--sandbox', action='store_true', help='before publishing (section only)')
    mode.add_argument('--full', action='store_true', help='after publishing the block data')
    parser.add_argument('--selftest', action='store_true',
                        help='one stadium\'s OLD against another\'s NEW - must FAIL')
    parser.add_argument('--only', nargs='*', help='these stadium pages only')
    options = parser.parse_args()

    check_prod_modules(options.sandbox)
    template_body = prod_template()
    candidate = candidate_of(template_body)
    pages = options.only or stadium_pages()

    def side(title, new):
        if options.sandbox:
            return sandbox_side(title, template_body, new)
        return full_side(title, candidate, new)

    def expected_for(title):
        return direct_appearances(stadium_names(
            title, preamble_for(template_body, page_text(title))))

    if options.selftest:
        first, second = 'אצטדיון בלומפילד', 'אצטדיון רמת גן'
        verdict, detail, *_ = compare_page(first, second, side, expected_for(first))
        print(f'selftest: {first} old vs {second} new -> {verdict}: {detail}')
        sys.exit(0 if verdict == 'FAIL' else 1)

    tally, total_rows, empty, quoted = {}, 0, 0, 0
    old_walls, new_walls = [], []
    for index, title in enumerate(pages, 1):
        expected = 0
        try:
            expected = expected_for(title)
            verdict, detail, rows, old_wall, new_wall = compare_page(title, title, side, expected)
        except ValueError as error:
            verdict, detail, rows, old_wall, new_wall = 'ERROR', str(error), 0, 0.0, 0.0
        tally[verdict] = tally.get(verdict, 0) + 1
        total_rows += rows
        # Counted only where Cargo itself confirms the case: an empty stadium
        # has no games, and a quoted name must have matched some.
        empty += verdict == 'ok' and expected == 0
        quoted += verdict == 'ok' and expected > 0 and any(mark in title for mark in '"\'')
        old_walls.append(old_wall)
        new_walls.append(new_wall)
        print(f'{index}/{len(pages)} {verdict:5} {title}: {detail}  '
              f'({old_wall:.2f}s -> {new_wall:.2f}s)', flush=True)

    print(f'\n{len(pages)} stadiums, {total_rows} rows compared: '
          + '  '.join(f'{key} {value}' for key, value in sorted(tally.items())))
    print(f'walltime median {statistics.median(old_walls):.2f}s -> '
          f'{statistics.median(new_walls):.2f}s; {empty} with no rows, {quoted} quoted names')
    if total_rows == 0:
        raise SystemExit('not a single row was compared - proves nothing')
    if not options.only and (empty == 0 or quoted == 0):
        raise SystemExit('the sweep never reached an empty stadium or a quoted name')
    sys.exit(0 if set(tally) == {'ok'} else 1)


if __name__ == '__main__':
    main()
