"""Old assistant-referee leaderboards against the one-invoke tabbers, locally.

    uv run python infra/football_queries/convert_referee_section.py --local
    uv run python infra/football_queries/compare_referee_leaderboards.py
    uv run python infra/football_queries/compare_referee_leaderboards.py --selftest

Renders the section both ways through the REAL templates and the real invoke,
for every assistant referee in the local data, and compares each box and tab:
title, heading (with its distinct-player count), the ranked rows, and whether
there is an "עוד" link. See .claude/referee_leaderboards_spec.md §4.5 for the
only differences allowed, checked mechanically here:

  1. tied players may be ordered differently, and at the top-10 boundary a
     different member of the tie may be shown - the counts must still match;
  4. a tab with exactly ten players has a link today and none now.

Refuses to pass over nothing: a run in which no referee shows a single row, or
any rendering carries an error, fails.
"""
from __future__ import annotations

import argparse
import html as html_module
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path('infra/tabs')))
from verify_tabs import ERROR_MARKERS, render  # noqa: E402

API = 'http://localhost:8080/api.php'
OLD = '{{#vardefine:שם להצגה|%s}}{{שופט כדורגל/עוזר שופט}}'
NEW = '{{#vardefine:שם להצגה|%s}}{{שופט כדורגל/עוזר שופט/ארגז חול לידרבורדים}}'
TOP = 10

BOX = re.compile(r'<div class="records-list-tabs-container"[^>]*>(.*?)'
                 r'(?=<div class="records-list-tabs-container"|\Z)', re.S)
TITLE = re.compile(r'<div class="title">([^<]*)</div>')
OLD_PANEL = re.compile(r'<div id="tab\d-content">(.*?)(?=<div id="tab\d-content">|\Z)', re.S)
NEW_PANEL = re.compile(r'<article[^>]*class="tabber__panel"[^>]*>(.*?)</article>', re.S)
HEADER = re.compile(r'<div class="tab-header">([^<]*)</div>')
ROW = re.compile(r'<span class="player-name">\s*(?:<a [^>]*>)?([^<]*)(?:</a>)?\s*</span>'
                 r'<div class="atom-recors-list-player-info"><span class="record">([^<]*)</span>')
MORE = re.compile(r'>עוד</a>')


def assistant_referees() -> list[str]:
    params = {'action': 'cargoquery', 'format': 'json', 'limit': '5000',
              'tables': 'Games_Referees', 'fields': 'AssistantReferees__full=a'}
    with urllib.request.urlopen(f'{API}?{urllib.parse.urlencode(params)}') as response:
        rows = json.loads(response.read())['cargoquery']
    names = set()
    for row in rows:
        names.update(name.strip() for name in (row['title'].get('a') or '').split(',') if name.strip())
    return sorted(names)


def boxes_of(page: str, panel: re.Pattern) -> list[dict]:
    boxes = []
    for box in BOX.findall(page):
        tabs = []
        for body in panel.findall(box):
            header = HEADER.search(body)
            rows = [(html_module.unescape(name).strip(), count.strip())
                    for name, count in ROW.findall(body)]
            tabs.append({'header': header.group(1).strip() if header else None,
                         'rows': rows, 'more': bool(MORE.search(body))})
        title = TITLE.search(box)
        boxes.append({'title': title.group(1) if title else None, 'tabs': tabs})
    return boxes


def players_in(header: str) -> int:
    match = re.search(r'\((\d+) ', header or '')
    return int(match.group(1)) if match else -1


def compare_tab(old: dict, new: dict) -> str | None:
    """None when equal or differing only as the spec allows."""
    if old['header'] != new['header']:
        return f'heading {old["header"]!r} vs {new["header"]!r}'
    old_counts = [count for _, count in old['rows']]
    new_counts = [count for _, count in new['rows']]
    if old_counts != new_counts:
        return f'counts {old_counts} vs {new_counts}'
    # Departure 1: players may move within a group of equal counts, and the
    # group that straddles the top-ten boundary may show different members.
    boundary = old_counts[-1] if len(old_counts) == TOP else None
    for count in dict.fromkeys(old_counts):
        old_names = sorted(name for name, c in old['rows'] if c == count)
        new_names = sorted(name for name, c in new['rows'] if c == count)
        if old_names != new_names and count != boundary:
            return f'players with {count}: {old_names} vs {new_names}'
    if old['more'] != new['more']:
        # Departure 4: exactly ten players - a link today, none now.
        if not (old['more'] and not new['more'] and players_in(old['header']) == TOP):
            return f'"עוד" link {old["more"]} vs {new["more"]}'
    return None


def compare(name: str, new_name: str | None = None) -> tuple[str, str, int]:
    old_page = render(OLD % name)
    new_page = render(NEW % (new_name or name))
    for label, page in (('old', old_page), ('new', new_page)):
        errors = [marker for marker in ERROR_MARKERS if marker in page]
        if errors:
            return 'ERROR', f'{label} rendering carries {errors}', 0
    if 'tabber__panel' not in new_page or 'slim-tabs' in new_page:
        return 'FAIL', 'the new section is not the tabber version', 0
    if re.search(r'</article>\s*<p class="mw-empty-elt">', new_page) or \
            re.search(r'עוד</a></p>', new_page):
        # A paragraph the old markup never had: it adds a margin under the
        # list, and the empty one beside a panel shifted the fade's counting.
        return 'FAIL', 'the parser wrapped the "עוד" link in a paragraph', 0
    old_boxes, new_boxes = boxes_of(old_page, OLD_PANEL), boxes_of(new_page, NEW_PANEL)
    if len(old_boxes) != 4 or len(new_boxes) != 4:
        return 'FAIL', f'{len(old_boxes)} old boxes, {len(new_boxes)} new', 0
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selftest', action='store_true',
                        help='two referees crossed must FAIL')
    options = parser.parse_args()

    names = assistant_referees()
    if not names:
        raise SystemExit('no assistant referees in the local data - nothing to compare')

    if options.selftest:
        verdict, detail, _ = compare(names[0], new_name=names[1])
        print(f'selftest: {names[0]} old vs {names[1]} new -> {verdict}: {detail}')
        sys.exit(0 if verdict == 'FAIL' else 1)

    tally, total_rows = {}, 0
    for name in names:
        verdict, detail, rows = compare(name)
        tally[verdict] = tally.get(verdict, 0) + 1
        total_rows += rows
        if verdict != 'ok':
            print(f'{verdict:5} {name}: {detail}')
    print(f'\n{len(names)} referees, {total_rows} rows compared: '
          + '  '.join(f'{k} {v}' for k, v in sorted(tally.items())))
    if total_rows == 0:
        raise SystemExit('not a single row was compared - proves nothing')
    sys.exit(0 if set(tally) == {'ok'} else 1)


if __name__ == '__main__':
    main()
