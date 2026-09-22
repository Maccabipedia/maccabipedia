"""Old main-referee leaderboard boxes against the one-invoke tabbers, on production.

    uv run python infra/football_queries/compare_referee_main_leaderboards.py --sandbox
    uv run python infra/football_queries/compare_referee_main_leaderboards.py --sandbox --selftest
    uv run python infra/football_queries/compare_referee_main_leaderboards.py --full

READ-ONLY, paced (season_api). The same comparison as
compare_stadium_leaderboards.py - per box and tab, plus each side's official
appearances heading against a direct Cargo count - for the four boxes of
תבנית:שופט כדורגל/שופט ראשי.

--sandbox (before publishing): per referee, the section alone - OLD through
the four live wrapper templates, NEW through the invoke with
Module:FootballStatsBlocks overridden by the repo file. One page per request,
so the RENDERER is production's: it does not yet honour a box's own
`boxOpen`, and the id="שיאנים" on the first box is not checked here (the stub
tests and --full check it).

--full (after publishing both modules): the whole referee page with the
section template overridden by the candidate; everything outside the four
boxes byte-identical, and the first box - only the first - carries the id.
"""
from __future__ import annotations

import argparse
import re
import statistics
import subprocess
import sys
from pathlib import Path

import mwparserfromhell

sys.path.insert(0, str(Path('infra/football_queries')))
sys.path.insert(0, str(Path('infra/season_pages')))
import compare_stadium_leaderboards as common  # noqa: E402
from season_api import call  # noqa: E402

common.SINGLE_IN_COLUMNS = ('Football_Games.Refs',)

TEMPLATE = 'תבנית:שופט כדורגל/שופט ראשי'
BOXES = ('הופעות', 'כיבושים', 'בישולים', 'מוצהבים')
OLD_LINES = '\n'.join(f'{{{{שופט כדורגל/הצגת שיאני {box}/שופט ראשי |שם להצגה={{{{#var: שם להצגה}}}} }}}}'
                      for box in BOXES)
INVOKE = '{{#invoke:FootballStatsBlock|leaderboards|בלוק=referee-main|שופט={{#var: שם להצגה}}}}'
OLD_BOX = re.compile(r'<div class="records-list-tabs-container"[^>]*>(.*?)'
                     r'(?=<div class="records-list-tabs-container"|\Z)', re.S)
# The four boxes sit in the banner-container after the balance box.
SECTION = re.compile(r'<div class="records-list-tabs-container".*?(?=</div>\s*<div class="games-records-container">)', re.S)


def candidate_of(body: str) -> str:
    if body.count(OLD_LINES) != 1:
        raise SystemExit('the four main-referee boxes were not found once, in order - refusing')
    return body.replace(OLD_LINES, INVOKE)


def referee_pages() -> list[str]:
    titles, cont = [], {}
    while True:
        data = call('prod', dict({'action': 'query', 'list': 'embeddedin', 'eititle': TEMPLATE,
                                  'eilimit': 'max'}, **cont))
        titles += [(row['ns'], row['title']) for row in data['query']['embeddedin']]
        if 'continue' not in data:
            break
        cont = data['continue']
    return sorted(title for _, title in titles)


def referee_name(title: str) -> str:
    """שם להצגה as תבנית:שופט כדורגל sets it: the page's parameter, else the
    page name without `כדורגל:` and `(שופט)`."""
    calls = [node for node in mwparserfromhell.parse(common.page_text(title)).filter_templates()
             if node.name.strip() in ('שופט כדורגל', 'תבנית:שופט כדורגל')]
    if len(calls) != 1:
        raise ValueError(f'{len(calls)} calls of the referee template on the page')
    if calls[0].has('שם להצגה') and str(calls[0].get('שם להצגה').value).strip():
        return str(calls[0].get('שם להצגה').value).strip()
    data = call('prod', {'action': 'expandtemplates', 'title': title, 'prop': 'wikitext',
                         'text': '{{#replaceset: {{PAGENAME}} |כדורגל:|(שופט)}}'}, post=True)
    return data['expandtemplates']['wikitext'].strip()


def direct_appearances(name: str) -> int:
    """Written apart from both paths: distinct Maccabi players with an
    appearance in an official game this referee refereed."""
    literal = '"' + name.replace('\\', '\\\\').replace('"', '\\"') + '"'
    data = call('prod', {'action': 'cargoquery',
                         'tables': 'Football_Games=fg, Games_Events=ge, Competitions=c',
                         'join_on': 'fg._pageID=ge._pageID, fg.Competition=c.OriginalName',
                         'where': f'fg.Refs = {literal} AND c.Official=1 '
                                  'AND ge.EventType IN (1,5) AND ge.Team=1',
                         'fields': 'COUNT(DISTINCT ge.PlayerName)=n', 'limit': '1'})
    return int(data['cargoquery'][0]['title']['n'])


def sandbox_side(title: str, name: str, new: bool):
    text = '{{#vardefine: שם להצגה |' + name + '}}' + (INVOKE if new else OLD_LINES)
    override = {'templatesandboxtitle': common.BLOCKS_PAGE,
                'templatesandboxtext': common.BLOCKS_FILE.read_text(encoding='utf-8'),
                'templatesandboxcontentmodel': 'Scribunto'} if new else None
    page, wall = common.parse(title, text, override)
    return page, '', wall


def full_side(title: str, candidate: str, new: bool):
    override = {'templatesandboxtitle': TEMPLATE, 'templatesandboxtext': candidate,
                'templatesandboxcontentmodel': 'wikitext'} if new else None
    page, wall = common.parse(title, common.page_text(title), override)
    sections = SECTION.findall(page)
    if len(sections) != 1:
        raise ValueError(f'{"new" if new else "old"} page holds {len(sections)} leaderboard sections')
    if new:
        ids = re.findall(r'<div class="records-list-tabs-container"([^>]*)>', sections[0])
        if ids != [' id="שיאנים"', '', '', '']:
            raise ValueError(f'new box wrappers carry {ids}, not the id on the first only')
    return sections[0], SECTION.sub('', page), wall


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--sandbox', action='store_true')
    mode.add_argument('--full', action='store_true')
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--only', nargs='*')
    options = parser.parse_args()

    if options.sandbox:
        # Production still runs master's renderer, which the sandbox renders
        # with; the repo's newer one (box-level boxOpen) is checked in --full.
        master = subprocess.run(['git', 'show', 'origin/master:infra/football_queries/'
                                 'Module_FootballStatsBlock.lua'],
                                capture_output=True, text=True, check=True).stdout
        if common.page_text('Module:FootballStatsBlock').strip() != master.strip():
            raise SystemExit('production\'s renderer is not master\'s - refusing')
        common.OTHER_MODULES = {page: name for page, name in common.OTHER_MODULES.items()
                                if page != 'Module:FootballStatsBlock'}
    common.check_prod_modules(sandbox=options.sandbox, new_block='referee-main')
    candidate = candidate_of(common.page_text(TEMPLATE))
    pages = options.only or referee_pages()
    if len(pages) == 1 and pages[0].startswith('@'):
        # `--only @file`: one page title per line.
        pages = [line.strip() for line in Path(pages[0][1:]).read_text(encoding='utf-8').splitlines()
                 if line.strip()]

    def side(title, name, new):
        return sandbox_side(title, name, new) if options.sandbox else full_side(title, candidate, new)

    def compare(old_title, new_title):
        old_name, new_name = referee_name(old_title), referee_name(new_title)
        expected = direct_appearances(old_name)
        old_section, old_outside, old_wall = side(old_title, old_name, False)
        new_section, new_outside, new_wall = side(new_title, new_name, True)
        verdict, detail, rows = common.compare_sections(old_section, new_section, expected,
                                                        old_box=OLD_BOX)
        if verdict == 'ok' and old_outside != new_outside:
            verdict, detail = 'FAIL', 'the page outside the section differs'
        return verdict, detail, rows, old_wall, new_wall, expected

    if options.selftest:
        first, second = pages[0], pages[-1]
        verdict, detail, *_ = compare(first, second)
        print(f'selftest: {first} old vs {second} new -> {verdict}: {detail}')
        sys.exit(0 if verdict == 'FAIL' else 1)

    tally, total_rows, empty, quoted, old_walls, new_walls = {}, 0, 0, 0, [], []
    for index, title in enumerate(pages, 1):
        try:
            verdict, detail, rows, old_wall, new_wall, expected = compare(title, title)
        except ValueError as error:
            verdict, detail, rows, old_wall, new_wall, expected = 'ERROR', str(error), 0, 0.0, 0.0, -1
        tally[verdict] = tally.get(verdict, 0) + 1
        total_rows += rows
        empty += verdict == 'ok' and expected == 0
        quoted += verdict == 'ok' and expected > 0 and any(mark in title for mark in '"\'')
        old_walls.append(old_wall)
        new_walls.append(new_wall)
        print(f'{index}/{len(pages)} {verdict:5} {title}: {detail}  ({old_wall:.2f}s -> {new_wall:.2f}s)',
              flush=True)

    print(f'\n{len(pages)} referees, {total_rows} rows compared: '
          + '  '.join(f'{key} {value}' for key, value in sorted(tally.items())))
    print(f'walltime median {statistics.median(old_walls):.2f}s -> {statistics.median(new_walls):.2f}s; '
          f'{empty} with no rows, {quoted} quoted names')
    if total_rows == 0:
        raise SystemExit('not a single row was compared - proves nothing')
    sys.exit(0 if set(tally) == {'ok'} else 1)


if __name__ == '__main__':
    main()
