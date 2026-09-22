"""Production gate for Module:FootballDate: does every game date come out as #time printed it?

The opponent all-games row (תבנית:יריבת כדורגל/הצגת כל המשחקים/הצגת משחק) printed its
date through תבנית:המרות/המרות תאריך/תאריך מלא לפורמט הצגה, i.e. #time, which a page may
call only ~240 times. The row now calls {{#invoke:FootballDate|full|…}}.

    dates   every distinct Football_Games.Date (plus an empty and an odd value, which go
            back through the template) rendered both ways: OLD through the template in
            batches the #time budget allows, NEW through the module rendered unsaved via
            TemplateSandbox. Each date byte for byte.
    pages   whole opponent pages, live vs the candidate row template (the module must be
            published). Every row identical, except rows where OLD printed the #time error:
            there NEW must print a date and nothing else may differ.
            The same run renders a module with two months swapped (the selftest): it must fail.

Run from the repository root:
    uv run python infra/football_queries/compare_opponent_dates.py dates|pages [titles…]
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, 'infra/season_pages')
from season_api import call  # noqa: E402
from compare_stadium_leaderboards import page_text, parse  # noqa: E402

MODULE = 'Module:FootballDate'
MODULE_SOURCE = Path('infra/football_queries/Module_FootballDate.lua')
DATE_TEMPLATE = 'המרות/המרות תאריך/תאריך מלא לפורמט הצגה'
ROW = 'תבנית:יריבת כדורגל/הצגת כל המשחקים/הצגת משחק'
OLD_CALL = '{{המרות/המרות תאריך/תאריך מלא לפורמט הצגה |תאריך={{{Date|}}} }}'
NEW_CALL = '{{#invoke:FootballDate|full|{{{Date|}}}}}'
TIME_ERROR = 'יותר מדי קריאות ל#זמן'
BATCH = 150
BIG = ['הפועל תל אביב', 'מכבי חיפה', 'מכבי פתח תקווה', 'מכבי נתניה']
LIST = 'תבנית:יריבת כדורגל/הצגת כל המשחקים'


def game_dates() -> list[str]:
    dates, offset = [], 0
    while True:
        result = call('prod', {'action': 'cargoquery', 'tables': 'Football_Games', 'fields': 'Date',
                               'group_by': 'Date', 'order_by': 'Date', 'limit': 500, 'offset': offset,
                               'format': 'json'})
        rows = [row['title']['Date'] for row in result['cargoquery']]
        dates += rows
        if len(rows) < 500:
            return dates
        offset += 500


def rendered(calls: list[str], override: dict | None = None) -> list[str]:
    """Each call's HTML, split out of one parse by numbered markers."""
    text = ''.join(f'@@@{index}@@@{piece}' for index, piece in enumerate(calls)) + f'@@@{len(calls)}@@@'
    html, _ = parse('ארגז חול', text, override)
    pieces = re.split(r'@@@(\d+)@@@', html)
    found = {int(pieces[index]): pieces[index + 1] for index in range(1, len(pieces) - 1, 2)}
    assert sorted(found) == list(range(len(calls) + 1)), 'markers lost'
    return [found[index] for index in range(len(calls))]


def differences(dates: list[str], old: list[str], module_source: str) -> list[str]:
    override = {'templatesandboxtitle': MODULE, 'templatesandboxtext': module_source,
                'templatesandboxcontentmodel': 'Scribunto'}
    new = rendered([f'{{{{#invoke:FootballDate|full|{date}}}}}' for date in dates], override)
    assert not any('script-error' in piece or TIME_ERROR in piece for piece in new), 'NEW errored'
    return [f'{date!r}: OLD {old_piece!r}\n    NEW {new_piece!r}'
            for date, old_piece, new_piece in zip(dates, old, new) if old_piece != new_piece]


def compare_dates() -> int:
    dates = game_dates() + ['', '1931-10-05 16:00']
    assert len(dates) > 3000, f'only {len(dates)} dates - the date query broke'
    old: list[str] = []
    for start in range(0, len(dates), BATCH):
        old += rendered([f'{{{{{DATE_TEMPLATE} |תאריך={date} }}}}' for date in dates[start:start + BATCH]])
        print(f'  OLD {len(old)}/{len(dates)}', flush=True)
    assert not any(TIME_ERROR in piece for piece in old), 'OLD hit the #time budget - lower BATCH'
    assert sum('<a ' in piece for piece in old) >= len(dates) - 2, 'OLD printed no links - vacuous'
    source = MODULE_SOURCE.read_text(encoding='utf-8')
    swapped = source.replace("'ינואר', 'פברואר',", "'פברואר', 'ינואר',", 1)
    assert swapped != source
    caught = differences(dates, old, swapped)
    print(f'selftest (January/February swapped): {len(caught)} dates differ '
          f'- {"ok" if caught else "GATE CANNOT FAIL"}')
    found = differences(dates, old, source)
    for line in found[:20]:
        print(line)
    print(f'dates: {len(dates) - len(found)}/{len(dates)} identical')
    return int(bool(found) or not caught)


def opponent_pages() -> list[str]:
    titles, cont = [], {}
    while True:
        result = call('prod', {'action': 'query', 'list': 'embeddedin', 'eititle': LIST, 'einamespace': 0,
                               'eilimit': 'max', 'format': 'json', **cont})
        titles += [page['title'] for page in result['query']['embeddedin']]
        if 'continue' not in result:
            return titles
        cont = result['continue']


DATE_CELL = re.compile(r'^(<div class="table-row[^"]*"><span class="desktop-only">)(.*?)(&#160;|</span>)', re.S)


def compare_page(title: str, candidate: str) -> list[str]:
    text = page_text(title)
    old, _ = parse(title, text)
    new, _ = parse(title, text, {'templatesandboxtitle': ROW, 'templatesandboxtext': candidate,
                                 'templatesandboxcontentmodel': 'wikitext'})
    problems = []
    if new.count(TIME_ERROR):
        problems.append(f'NEW still has {new.count(TIME_ERROR)} #time errors')
    old_rows, new_rows = old.split('<div class="table-row'), new.split('<div class="table-row')
    if len(old_rows) != len(new_rows):
        return problems + [f'{len(old_rows)} rows vs {len(new_rows)}']
    fixed = 0
    for old_row, new_row in zip(old_rows, new_rows):
        if old_row == new_row:
            continue
        old_full, new_full = '<div class="table-row' + old_row, '<div class="table-row' + new_row
        old_cell, new_cell = DATE_CELL.match(old_full), DATE_CELL.match(new_full)
        rest_same = (old_cell and new_cell and old_cell.group(1) == new_cell.group(1)
                     and old_full[old_cell.end(2):] == new_full[new_cell.end(2):])
        if rest_same and TIME_ERROR in old_cell.group(2) and re.fullmatch(
                r'<a [^>]+>\d{1,2} ב\S+</a> <a [^>]+>\d{4}</a>', new_cell.group(2)):
            fixed += 1
            continue
        problems.append(f'row differs:\n    OLD {old_row[:300]!r}\n    NEW {new_row[:300]!r}')
    rows = len(old_rows) - 1
    print(f'  {title}: {rows} rows, {fixed} #time errors fixed, {len(problems)} problems', flush=True)
    return problems


def compare_pages(titles: list[str]) -> int:
    row = page_text(ROW)
    assert row.count(OLD_CALL) == 1, 'the row template no longer holds the date call'
    candidate = row.replace(OLD_CALL, NEW_CALL)
    exists = call('prod', {'action': 'query', 'titles': MODULE, 'format': 'json'})['query']['pages'][0]
    assert 'missing' not in exists, f'{MODULE} is not published - publish it first'
    if not titles:
        others = [title for title in opponent_pages() if title not in BIG]
        titles = BIG + others[::25]
    failed = 0
    for title in titles:
        problems = compare_page(title, candidate)
        for problem in problems[:5]:
            print('   ', problem)
        failed += bool(problems)
    print(f'pages: {len(titles) - failed}/{len(titles)} ok')
    return failed


if __name__ == '__main__':
    mode, *arguments = sys.argv[1:] or ['dates']
    sys.exit(compare_dates() if mode == 'dates' else compare_pages(arguments))


