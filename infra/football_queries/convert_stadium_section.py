"""Put the stadium page's four leaderboard boxes on one #invoke.

    uv run python infra/football_queries/convert_stadium_section.py --print

In `תבנית:אצטדיון כדורגל` the four `record-section-container` boxes - each a
`סטטיסטיקה/תצוגה/שחקנים/שיאני …/עיצוב חדש` template, 8 Cargo queries - become
one `{{#invoke:FootballStatsBlock|leaderboards|בלוק=stadium|…}}` that renders
the same four boxes, as tabbers, from one query. See
.claude/football_queries.md, "Leaderboards".

Reads production's template (read-only) and prints the candidate. Writing it
is a separate, approved step.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path('infra/season_pages')))

TEMPLATE = 'תבנית:אצטדיון כדורגל'

BOXES = ('הופעות', 'כיבושים', 'בישולים', 'מוצהבים')
OLD_BOX = ('<div class="record-section-container">\n'
           '<div class="title">שיאני {box}</div>\n'
           '<div class="content">{{{{סטטיסטיקה/תצוגה/שחקנים/שיאני {box}/עיצוב חדש '
           '|אצטדיונים={{{{#arrayprint: אצטדיונים לשליפה}}}} }}}}</div>\n'
           '</div>')
BOX_SEPARATOR = '<!--\n\n-->'
INVOKE = ('{{#invoke:FootballStatsBlock|leaderboards|בלוק=stadium'
          '|אצטדיונים={{#arrayprint: אצטדיונים לשליפה}}}}')

# The grid the boxes sit in. Its id is the page's "שיאנים" anchor, so it
# stays, and the invoke's boxes carry none of their own.
SECTION_OPEN = '<div class="details-records-lists-container" id="שיאנים">'


def old_boxes() -> str:
    return BOX_SEPARATOR.join(OLD_BOX.format(box=box) for box in BOXES)


def candidate_of(body: str) -> str:
    """The template with its four boxes replaced by one invoke.

    The four must appear exactly once, consecutively and in order, directly
    inside the grid div - anything else is a template this was not written
    for, and a candidate that quietly replaced fewer than four would compare
    the remaining boxes against themselves.
    """
    block = f'{SECTION_OPEN}\n{old_boxes()}\n</div>'
    if body.count(block) != 1:
        raise SystemExit('the four stadium boxes were not found exactly once, '
                         'consecutive and in order, inside the grid - refusing')
    return body.replace(block, f'{SECTION_OPEN}\n{INVOKE}\n</div>')


def section_texts(body: str) -> tuple[str, str]:
    """The OLD and NEW section alone, for a section-only render. Both read
    the page's אצטדיונים לשליפה array, which the caller defines first."""
    candidate_of(body)
    return (f'{SECTION_OPEN}\n{old_boxes()}\n</div>',
            f'{SECTION_OPEN}\n{INVOKE}\n</div>')


def prod_template() -> str:
    from season_api import call  # noqa: PLC0415 - path set above
    data = call('prod', {'action': 'query', 'titles': TEMPLATE, 'prop': 'revisions',
                         'rvprop': 'content', 'rvslots': 'main'})
    return data['query']['pages'][0]['revisions'][0]['slots']['main']['content']


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--print', action='store_true', required=True,
                        help='print the candidate built from production\'s template')
    parser.parse_args()
    print(candidate_of(prod_template()))


if __name__ == '__main__':
    main()
