"""Games-list icons without the galleries.

    uv run python infra/season_pages/convert_game_row_icons.py --local --print
    uv run python infra/season_pages/convert_game_row_icons.py --local --apply

תבנית:כדורגל/רשימת משחקים/הצגת משחק decides each game's programme, press and
photos icons by rendering a whole DPL <gallery> of the matching category and
testing whether it came out non-empty - 165 galleries on a 55-game season,
built and thrown away. This swaps each test for the category's own size,
{{PAGESINCATEGORY:…|all|R}}, and changes nothing else in the template.
compare_game_icons.py checks both give the same answer for every game on
production.

Local only; production is a separate, approved step.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path('infra/tabs')))

COMPOSE = 'infra/local-wiki/docker-compose.yml'
TEMPLATE = 'תבנית:כדורגל/רשימת משחקים/הצגת משחק'

# The three categories as the template names them.
CATEGORIES = (
    '{{{PageName|}}}/תוכניית משחק',
    'עיתונות למשחק מה-{{#var: תאריך עבור מדיה}}',
    '{{{PageName|}}}/תמונות',
)
OLD_TEST = '{{#תנאי: {{הצגת גלריה לפי קטגוריה |שם קטגוריה=%s |אין תוצאות=}} |'
NEW_TEST = '{{#ifexpr: {{PAGESINCATEGORY:%s|all|R}} > 0 |'

# The row receives PageName from a Cargo query, which HTML-encodes a quote:
# `משחק:11-09-1993 בית&quot;ר ירושלים נגד …`. The gallery's DPL decodes that
# entity; PAGESINCATEGORY takes the name literally and finds no category -
# every בית"ר game lost its photos icon until this. So the new test decodes it.
# (No other entity occurs in Football_Games page names.)
PAGE_NAME = '{{{PageName|}}}'
DECODED_PAGE_NAME = '{{#replace:{{{PageName|}}}|&quot;|"}}'


def new_test(category: str) -> str:
    """The category-size test for one of CATEGORIES, as the template gets it."""
    return NEW_TEST % category.replace(PAGE_NAME, DECODED_PAGE_NAME)


def candidate_of(body: str) -> str:
    """The template with each gallery test replaced by a category-size test.

    Each test must be present exactly once - anything else is a template this
    was not written for, and a partial swap would leave the comparison
    checking a mix. The icon HTML after each test is untouched.
    """
    for category in CATEGORIES:
        old = OLD_TEST % category
        if body.count(old) != 1:
            raise SystemExit(f'expected exactly one of {old!r}, found {body.count(old)} - '
                             'refusing')
        body = body.replace(old, new_test(category))
    if 'הצגת גלריה לפי קטגוריה' in body:
        raise SystemExit('a gallery test is still there after the swap - refusing')
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
    parser.add_argument('--print', action='store_true', help='print the candidate and stop')
    parser.add_argument('--apply', action='store_true',
                        help='write the real template (undo: scripts/restore-db.sh)')
    options = parser.parse_args()

    candidate = candidate_of(read_local(TEMPLATE))
    if options.print or not options.apply:
        print(candidate)
        return

    from verify_tabs import write_local  # noqa: PLC0415 - path set above

    write_local(TEMPLATE, candidate)
    print(f'wrote {TEMPLATE}')


if __name__ == '__main__':
    main()
