"""Player-category pages: the old leaderboard boxes against the one invoke, on production.

    uv run python infra/lua_modules/compare_player_categories.py
    uv run python infra/lua_modules/compare_player_categories.py --selftest
    uv run python infra/lua_modules/compare_player_categories.py --print

READ-ONLY. Every page using תבנית:קטגוריית שחקני כדורגל, rendered whole with
the live template and with the candidate (TemplateSandbox, unsaved), which
replaces the four boxes with
    {{#invoke:FootballStatsBlock|leaderboards|בלוק=player-category|שחקנים={{#arrayprint: שחקנים לשליפה}}}}
(the list the template already built from the category-members helper - one
DPL instead of five). Compared per box and tab with the referee rules, the
official appearances heading against a direct Cargo count over the
category's own members, and everything outside the boxes byte for byte.
--selftest renders page A's old version against page B's new one; it must FAIL.
"""
from __future__ import annotations

import argparse
import html as html_module
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path('infra/lua_modules')))
sys.path.insert(0, str(Path('infra/season_pages')))
from compare_players_portal import OFFICIAL_HEADING  # noqa: E402
from compare_referee_leaderboards import compare_tab, HEADER, MORE, ROW, TITLE  # noqa: E402
from compare_stadium_leaderboards import OLD_PANEL, NEW_PANEL, page_text, parse, unify_link_quotes  # noqa: E402
from season_api import call  # noqa: E402

TEMPLATE = 'תבנית:קטגוריית שחקני כדורגל'
HELPER = '{{סטטיסטיקה/שמות דפים מקטגוריה מופרדים לשליפה |שם קטגוריה={{שם הדף}} }}'
BOX = ('<div class="records-section-container">\n<div class="title">שיאני {name}</div>\n'
       '<div class="list">{{{{סטטיסטיקה/תצוגה/שחקנים/שיאני {name}/עיצוב חדש |שחקנים=' + HELPER.replace('{', '{{').replace('}', '}}')
       + '|עוד תוצאות= }}}}</div>\n</div>')
NAMES = ('הופעות', 'כיבושים', 'בישולים', 'מוצהבים')
INVOKE = '{{#invoke:FootballStatsBlock|leaderboards|בלוק=player-category|שחקנים={{#arrayprint: שחקנים לשליפה}}}}'
# A box runs to the next box, the last one to the end of the render: nested
# closing divs inside the old tab strips make any tighter end cut a box short.
# After the boxes a category page's render holds only closing tags (the member
# list is not part of the parse), so "outside" is everything before the first.
BOX_REGION = re.compile(r'<div class="records-section-container[^"]*">.*?'
                        r'(?=<div class="records-section-container|\Z)', re.S)
BOXES_START = re.compile(r'<div class="records-section-container')


def candidate_of(body: str) -> str:
    old = '<!--\n\n-->'.join(BOX.format(name=name) for name in NAMES)
    if body.count(old) != 1:
        raise SystemExit('the four boxes were not found once, in order - refusing')
    return body.replace(old, INVOKE)


def category_pages() -> list[str]:
    data = call('prod', {'action': 'query', 'list': 'embeddedin', 'eititle': TEMPLATE, 'eilimit': 'max'})
    return sorted(row['title'] for row in data['query']['embeddedin'])


def members(title: str) -> list[str]:
    data = call('prod', {'action': 'expandtemplates', 'title': title, 'prop': 'wikitext', 'text': HELPER}, post=True)
    items = [html_module.unescape(item).strip().strip('"') for item in data['expandtemplates']['wikitext'].split(',')]
    return [item for item in items if item]


def direct_appearances(names: list[str]) -> int:
    if not names:
        return 0
    literals = ', '.join('"' + name.replace('\\', '\\\\').replace('"', '\\"') + '"' for name in names)
    data = call('prod', {'action': 'cargoquery', 'tables': 'Football_Games=fg, Games_Events=ge, Competitions=c',
                         'join_on': 'fg._pageID=ge._pageID, fg.Competition=c.OriginalName',
                         'where': f'c.Official=1 AND ge.EventType IN (1,5) AND ge.Team=1 AND ge.PlayerName IN ({literals})',
                         'fields': 'COUNT(DISTINCT ge.PlayerName)=n', 'limit': '1'},
                post=True)   # a big category's name list is too long for a URL (414)
    return int(data['cargoquery'][0]['title']['n'])


def boxes_of(page: str) -> list[dict]:
    boxes = []
    for region in BOX_REGION.findall(page):
        panel = NEW_PANEL if 'tabber__panel' in region else OLD_PANEL
        tabs = []
        for body in panel.findall(region):
            header, link = HEADER.search(body), MORE.search(body)
            tabs.append({'header': header.group(1).strip() if header else None,
                         'rows': [(html_module.unescape(n).strip(), c.strip()) for n, c in ROW.findall(body)],
                         'more': bool(link), 'href': unify_link_quotes(link.group(1)) if link else None})
        title = TITLE.search(region)
        boxes.append({'title': title.group(1) if title else None, 'tabs': tabs})
    return boxes


def compare(old_page: str, new_page: str, expected: int) -> tuple[str, str]:
    for label, page in (('old', old_page), ('new', new_page)):
        if 'scribunto-error' in page or 'class="error"' in page:
            return 'ERROR', f'{label} rendering carries an error'
    old_boxes, new_boxes = boxes_of(old_page), boxes_of(new_page)
    if not old_boxes and not new_boxes:
        return 'ok', 'no boxes on either side (one member or none)'
    if len(old_boxes) != 4 or len(new_boxes) != 4 or new_page.count('tabber-converted') != 4:
        return 'FAIL', f'{len(old_boxes)} old boxes, {len(new_boxes)} new'
    for label, boxes in (('old', old_boxes), ('new', new_boxes)):
        heading = OFFICIAL_HEADING.match(boxes[0]['tabs'][0]['header'] or '')
        if not heading or int(heading.group(1)) != expected:
            return 'FAIL', f'{label} official appearances heading, Cargo counts {expected}'
    rows = 0
    for old_box, new_box in zip(old_boxes, new_boxes):
        if old_box['title'] != new_box['title']:
            return 'FAIL', f'title {old_box["title"]!r} vs {new_box["title"]!r}'
        for old_tab, new_tab in zip(old_box['tabs'], new_box['tabs']):
            rows += len(old_tab['rows'])
            problem = compare_tab(old_tab, new_tab)
            if problem:
                return 'FAIL', f'{old_box["title"]} / {old_tab["header"]}: {problem}'
    before = lambda page: page[:BOXES_START.search(page).start()]  # noqa: E731
    if before(old_page) != before(new_page):
        return 'FAIL', 'the page before the boxes differs'
    return 'ok', f'4 boxes, {rows} rows'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--print', action='store_true')
    options = parser.parse_args()
    candidate = candidate_of(page_text(TEMPLATE))
    if options.print:
        print(candidate)
        return
    override = {'templatesandboxtitle': TEMPLATE, 'templatesandboxtext': candidate,
                'templatesandboxcontentmodel': 'wikitext'}
    pages = category_pages()
    pairs = [(pages[0], pages[1])] if options.selftest else [(p, p) for p in pages]
    tally = {}
    for old_title, new_title in pairs:
        old_page, old_wall = parse(old_title, page_text(old_title))
        new_page, new_wall = parse(new_title, page_text(new_title), override)
        verdict, detail = compare(old_page, new_page, direct_appearances(members(old_title)))
        tally[verdict] = tally.get(verdict, 0) + 1
        print(f'{verdict:5} {old_title}{" vs " + new_title if old_title != new_title else ""}: {detail}  '
              f'({old_wall:.2f}s -> {new_wall:.2f}s)', flush=True)
    if options.selftest:
        sys.exit(0 if 'FAIL' in tally else 1)
    print(f'\n{len(pages)} category pages: ' + '  '.join(f'{k} {v}' for k, v in sorted(tally.items())))
    sys.exit(0 if set(tally) == {'ok'} else 1)


if __name__ == '__main__':
    main()
