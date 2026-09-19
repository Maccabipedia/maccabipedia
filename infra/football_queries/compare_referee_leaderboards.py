"""Old assistant-referee leaderboards against the one-invoke tabbers, locally.

The 4 shared display templates the season comparison depends on
(`סטטיסטיקה/תצוגה/שחקנים/שיאני …/עיצוב חדש`) were found, while building that
comparison, to hold a stale `{{#invoke:שיאנים|section…}}` body in the
committed DB fixture - the abandoned Module:שיאנים prototype from the closed
PRs #188/#189 (see the referee spec's §2 "Out of scope"), not production's
real `#cargo_query` wikitext. This module's own dedicated template
(`.../עוזר שופט/עיצוב חדש`) was never touched by that prototype, which is why
this comparison never surfaced it. Fixed in the fixture (production wikitext
restored + re-signed, then re-snapshotted) 2026-09-18 - see
.claude/season_leaderboards_spec.md §7 for the full story.

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
MORE = re.compile(r'<a [^>]*href="([^"]*ViewData[^"]*)"[^>]*>עוד</a>')


def link_query(href: str) -> dict:
    """The ViewData link's query, normalised so equivalent queries compare equal.

    Conditions are compared as a SET with whitespace removed: the templates'
    WHERE repeats `Official = 1`, carries `1=1` and blank lines, and names
    `Team` without its table, none of which changes the rows.
    """
    params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(html_module.unescape(href)).query,
                                         keep_blank_values=True))

    def squash(text: str) -> str:
        return re.sub(r'\s+', '', text)

    where = {squash(part) for part in re.split(r'\s+AND\s+', params.get('where', ''), flags=re.I)}
    where = {'Games_Events.Team=1' if part == 'Team=1' else part for part in where} - {'', '1=1'}
    tables = {squash(part) for part in params.get('tables', '').split(',')}
    join = {squash(part) for part in params.get('join_on', '').split(',')}
    # The templates' #cargo_query has Games_Referees in a static `tables=`
    # list regardless of whether a filter actually uses it (measured: no game
    # has 2+ Games_Referees rows, and it is never SELECTed, so an unused join
    # to it changes no row and no value). The module only joins what a filter
    # touches, so it omits the table here when nothing in the WHERE names it -
    # on referee pages that never happens (עוזר שופט always uses it), so this
    # never fires there; on season pages it always does.
    if not any('games_referees' in part.lower() for part in where):
        tables -= {'Games_Referees'}
        join = {part for part in join if 'games_referees' not in part.lower()}
    return {
        'where': where,
        'tables': tables,
        'join': join,
        'fields': squash(params.get('fields', '')).lower(),
        'group_by': squash(params.get('group_by', '')),
        # Newer Cargo writes its own links as order_by[0]; production's older
        # Cargo writes order_by. The same parameter either way.
        'order_by': squash(params.get('order_by', params.get('order_by[0]', ''))).lower(),
        'offset': params.get('offset'),
        'limit': params.get('limit'),
        'template': params.get('template'),
    }


def compare_links(old_href: str, new_href: str) -> str | None:
    old, new = link_query(old_href), link_query(new_href)
    # The only intended difference: the name tiebreak the box also uses.
    if new['order_by'] != old['order_by'] + ',games_events.playername':
        return f'"עוד" order_by {old["order_by"]!r} vs {new["order_by"]!r}'
    for key in ('where', 'tables', 'join', 'fields', 'group_by', 'offset', 'limit', 'template'):
        if old[key] != new[key]:
            if isinstance(old[key], set):
                return (f'"עוד" {key}: only old {sorted(old[key] - new[key])}, '
                        f'only new {sorted(new[key] - old[key])}')
            return f'"עוד" {key}: {old[key]!r} vs {new[key]!r}'
    return None


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
            link = MORE.search(body)
            tabs.append({'header': header.group(1).strip() if header else None,
                         'rows': rows, 'more': bool(link),
                         'href': link.group(1) if link else None})
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
    # Every row the heading promises must have been extracted, on each side.
    # Without this a row the ROW regex cannot read vanishes from BOTH sides
    # and the tab still compares equal on what is left.
    expected = min(players_in(old['header']), TOP)
    for label, side in (('old', old), ('new', new)):
        if expected < 0 or len(side['rows']) != expected:
            return (f'{label} side: {len(side["rows"])} rows read, heading '
                    f'{side["header"]!r} promises {expected}')
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
    if old['href'] and new['href']:
        return compare_links(old['href'], new['href'])
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
