"""מספרים עונתיים from two queries instead of 32.

    uv run python infra/season_pages/convert_season_numbers.py --local --print
    uv run python infra/season_pages/convert_season_numbers.py --local --sandbox
    uv run python infra/season_pages/convert_season_numbers.py --local --apply

The container, תבנית:עונת כדורגל/הצגת מספרים עונתיים, renders four tabs of
תבנית:עונת כדורגל/הצגת מספרים עונתיים/הצגה לפי מפעל, and each tab ran eight
query templates. This makes the container prime two blocks once
(season-results, season-cards - see Module:FootballStatsBlocks) and each tab
read its eight numbers with `value`. Nothing else in either template changes:
the tab strip, the markup, the percentages, #number_format and the
hide-at-zero rules all stay, so the output must be byte-identical.

--sandbox writes both under /ארגז חול, the sandbox container calling the
sandbox tab, so the new pair can be rendered beside the old one for every
season before anything live changes (compare_season_numbers.py).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path('infra/tabs')))

COMPOSE = 'infra/local-wiki/docker-compose.yml'
CONTAINER = 'תבנית:עונת כדורגל/הצגת מספרים עונתיים'
TAB = 'תבנית:עונת כדורגל/הצגת מספרים עונתיים/הצגה לפי מפעל'
SANDBOX = '/ארגז חול'

OPEN = '--><div class="season-statistics-container">'
PRIME = ('-->{{#invoke:FootballStatsBlock|prime|בלוק=season-results}}'
         '{{#invoke:FootballStatsBlock|prime|בלוק=season-cards}}'
         '<div class="season-statistics-container">')
TAB_CALL = '{{עונת כדורגל/הצגת מספרים עונתיים/הצגה לפי מפעל |'

SCOPE = '|עונה={{{עונה|}}} |קטגוריית מפעל={{{קטגוריית מפעל|}}}'
GAMES = '{{סטטיסטיקה/שליפות/מתקדמות/כמות נתוני משחק ' + SCOPE
EVENTS = '{{סטטיסטיקה/שליפות/מתקדמות/כמות אירועי שחקן ' + SCOPE
VALUE = ('{{#invoke:FootballStatsBlock|value|בלוק=%s|תא=%s'
         '|עונה={{{עונה|}}}|קטגוריית מפעל={{{קטגוריית מפעל|}}}}}')
# Each query call as the tab template has it -> the cell that replaces it.
QUERIES = {
    GAMES + ' |תוצאה=ניצחון}}': ('season-results', 'wins'),
    GAMES + ' |תוצאה=תיקו}}': ('season-results', 'draws'),
    GAMES + ' |תוצאה=הפסד}}': ('season-results', 'losses'),
    GAMES + ' |נתון משחק=כיבושים}}': ('season-results', 'goalsFor'),
    GAMES + ' |נתון משחק=ספיגות}}': ('season-results', 'goalsAgainst'),
    GAMES + ' |תוצאה יריבה=0}}': ('season-results', 'cleanSheets'),
    EVENTS + ' |תת אירוע=71 |מכבי=כן}}': ('season-cards', 'yellows'),
    EVENTS + ' |תת אירוע=72, 73 |מכבי=כן}}': ('season-cards', 'reds'),
}


def once(body: str, piece: str, what: str) -> None:
    if body.count(piece) != 1:
        raise SystemExit(f'expected exactly one {what} ({piece!r}), found '
                         f'{body.count(piece)} - refusing')


def container_candidate(body: str, sandbox: bool = False) -> str:
    """The container, priming both blocks before its tab strip."""
    once(body, OPEN, 'container opening')
    if TAB_CALL not in body or body.count(TAB_CALL) != 4:
        raise SystemExit(f'expected four tab calls, found {body.count(TAB_CALL)} - refusing')
    body = body.replace(OPEN, PRIME)
    if sandbox:
        body = body.replace(TAB_CALL, TAB_CALL.replace(' |', SANDBOX + ' |'))
    return body


def tab_candidate(body: str) -> str:
    """The tab, reading its eight numbers from the primed blocks."""
    for query, (block, cell) in QUERIES.items():
        once(body, query, f'{cell} query')
        body = body.replace(query, VALUE % (block, cell))
    if 'סטטיסטיקה/שליפות' in body:
        raise SystemExit('a query template is still called after the swap - refusing')
    return body


def read_local(title: str) -> str:
    result = subprocess.run(
        ['docker', 'compose', '-f', COMPOSE, 'exec', '-T', 'mediawiki',
         'php', 'maintenance/getText.php', title],
        capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'reading {title} failed: {result.stderr[-400:]}')
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--local', action='store_true', required=True,
                        help='read and write the LOCAL wiki (the only target)')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--print', action='store_true', help='print both candidates')
    mode.add_argument('--sandbox', action='store_true',
                      help='write both under /ארגז חול, nothing live changes')
    mode.add_argument('--apply', action='store_true',
                      help='write the real templates (undo: scripts/restore-db.sh)')
    options = parser.parse_args()

    container = container_candidate(read_local(CONTAINER), sandbox=options.sandbox)
    tab = tab_candidate(read_local(TAB))
    if not (options.sandbox or options.apply):
        print(container, '\n' + '=' * 70 + '\n', tab)
        return

    from verify_tabs import write_local  # noqa: PLC0415 - path set above

    suffix = SANDBOX if options.sandbox else ''
    # The container first: priming on its own is harmless (two queries the
    # old tabs do not yet read), while a tab reading values that nothing
    # primed raises on every page.
    write_local(CONTAINER + suffix, container)
    write_local(TAB + suffix, tab)
    print(f'wrote {CONTAINER + suffix}\nwrote {TAB + suffix}')


if __name__ == '__main__':
    main()
