"""The players portal's leaderboards: old template boxes against the two invokes, on production.

    uv run python infra/lua_modules/compare_players_portal.py
    uv run python infra/lua_modules/compare_players_portal.py --selftest
    uv run python infra/lua_modules/compare_players_portal.py --print

READ-ONLY. קטגוריה:שחקנים (also transcluded by פורטל שחקנים) shows four
leaderboard boxes over every official game - goals and assists above the
current-squad box, appearances and cards below it. The candidate replaces
each pair with one `{{#invoke:FootballStatsBlock|leaderboards|בלוק=…}}`
(blocks players-goals-assists / players-appearances-cards, already published
and called by nothing else). Both versions of the page are rendered with
action=parse&text= and compared:

  - per box and tab, the referee harness's rules (title, heading with its
    distinct-player count, ranked rows, the "עוד" link's query), allowing ties
    ordered by name and no "עוד" on exactly ten;
  - both sides' official appearances heading equals a direct Cargo count;
  - everything outside the four boxes byte-identical.
--selftest renders the NEW side with the boxes' order swapped and must FAIL.
"""
from __future__ import annotations

import argparse
import html as html_module
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path('infra/lua_modules')))
sys.path.insert(0, str(Path('infra/season_pages')))
from compare_referee_leaderboards import compare_tab, HEADER, MORE, ROW, TITLE  # noqa: E402
from compare_stadium_leaderboards import OLD_PANEL, NEW_PANEL, page_text, parse, unify_link_quotes  # noqa: E402
from season_api import call  # noqa: E402

PAGE = 'קטגוריה:שחקנים'
BOX = '<div class="records-container">\n<div class="title">{title}</div>\n<div class="list">{{{{סטטיסטיקה/תצוגה/שחקנים/{name}/עיצוב חדש}}}}</div>\n</div>'
PAIRS = {
    'players-goals-assists': (('שיאני כיבושים', 'שיאני כיבושים'), ('שיאני בישולים ', 'שיאני בישולים')),
    'players-appearances-cards': (('שיאני הופעות', 'שיאני הופעות'), ('שיאני מוצהבים', 'שיאני מוצהבים')),
}
BOX_START = re.compile(r'<div class="records-container[^"]*">')
BOX_REGION = re.compile(r'<div class="records-container[^"]*">.*?'
                        r'(?=<div class="records-container|<div class="season-players-container"|<div>\s*<b>|\Z)', re.S)
OFFICIAL_HEADING = re.compile(r'^משחקים רשמיים \((\d+) מופיעים שונים\)$')


def candidate_of(body: str, swapped: bool = False) -> str:
    for block, boxes in PAIRS.items():
        old = '\n'.join(BOX.format(title=title, name=name) for title, name in boxes)
        if body.count(old) != 1:
            raise SystemExit(f'the {block} boxes were not found once, in order - refusing')
        if swapped:
            block = 'players-appearances-cards' if block == 'players-goals-assists' else 'players-goals-assists'
        body = body.replace(old, '{{#invoke:FootballStatsBlock|leaderboards|בלוק=' + block + '}}')
    return body


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


def direct_appearances() -> int:
    data = call('prod', {'action': 'cargoquery', 'tables': 'Football_Games=fg, Games_Events=ge, Competitions=c',
                         'join_on': 'fg._pageID=ge._pageID, fg.Competition=c.OriginalName',
                         'where': 'c.Official=1 AND ge.EventType IN (1,5) AND ge.Team=1',
                         'fields': 'COUNT(DISTINCT ge.PlayerName)=n', 'limit': '1'})
    return int(data['cargoquery'][0]['title']['n'])


def compare(old_page: str, new_page: str, expected: int) -> tuple[str, str]:
    for label, page in (('old', old_page), ('new', new_page)):
        if 'scribunto-error' in page or 'class="error"' in page:
            return 'ERROR', f'{label} rendering carries an error'
    if new_page.count('tabber-converted') != 4 or 'slim-tabs' in ''.join(BOX_REGION.findall(new_page)):
        return 'FAIL', 'the new boxes are not the four tabbers'
    old_boxes, new_boxes = boxes_of(old_page), boxes_of(new_page)
    if len(old_boxes) != 4 or len(new_boxes) != 4:
        return 'FAIL', f'{len(old_boxes)} old boxes, {len(new_boxes)} new'
    for label, boxes in (('old', old_boxes), ('new', new_boxes)):
        official = next((b for b in boxes if (b['title'] or '').strip() == 'שיאני הופעות'), None)
        heading = OFFICIAL_HEADING.match(official['tabs'][0]['header'] or '') if official else None
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
    if BOX_REGION.sub('', old_page) != BOX_REGION.sub('', new_page):
        return 'FAIL', 'the page outside the four boxes differs'
    return 'ok', f'4 boxes, {rows} rows'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--print', action='store_true', help='print the candidate page text')
    options = parser.parse_args()
    body = page_text(PAGE)
    if options.print:
        print(candidate_of(body))
        return
    old_page, old_wall = parse(PAGE, body)
    new_page, new_wall = parse(PAGE, candidate_of(body, swapped=options.selftest))
    verdict, detail = compare(old_page, new_page, direct_appearances())
    print(f'{"selftest: " if options.selftest else ""}{verdict}: {detail}  ({old_wall:.2f}s -> {new_wall:.2f}s)')
    if options.selftest:
        sys.exit(0 if verdict == 'FAIL' else 1)
    sys.exit(0 if verdict == 'ok' else 1)


if __name__ == '__main__':
    main()
