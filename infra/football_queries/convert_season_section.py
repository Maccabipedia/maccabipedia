"""Put the season page's four leaderboard boxes on one #invoke.

    uv run python infra/football_queries/convert_season_section.py --local
    uv run python infra/football_queries/convert_season_section.py --local --print

In `תבנית:עונת כדורגל` the four lines that call `עונת כדורגל/הצגת שיאני …`
- 8 Cargo queries each - become one
`{{#invoke:FootballStatsBlock|leaderboards|…}}` that renders the same four
boxes, as tabbers, from one query. See .claude/lua_modules.md,
"Leaderboards".

Local only. Production is a separate, approved step.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path('infra/tabs')))

COMPOSE = 'infra/local-wiki/docker-compose.yml'
TEMPLATE = 'תבנית:עונת כדורגל'
SANDBOX = TEMPLATE + '/ארגז חול לידרבורדים'

BOXES = ('הופעות', 'כיבושים', 'בישולים', 'מוצהבים')
OLD_LINE = '{{עונת כדורגל/הצגת שיאני %s |עונה={{#var: עונה להצגה}} }}'
INVOKE = ('{{#invoke:FootballStatsBlock|leaderboards|בלוק=season'
          '|עונה={{#var: עונה להצגה}}}}')

# The div the section is wrapped in on the real page - its id, unlike the
# referee boxes' own id, lives on this PARENT, so it must survive untouched.
SECTION_OPEN = '<div class="players-records-container" id="שיאנים">'


def candidate_of(body: str) -> str:
    """The section with its four leaderboard lines replaced by one invoke.

    Each line must be present exactly once and the four must be consecutive,
    in order, inside the records container div - anything else is a template
    this was not written for, and a candidate that quietly replaced less than
    all four would still compare the remaining boxes against themselves.
    """
    if body.count(SECTION_OPEN) != 1:
        raise SystemExit(f'expected exactly one {SECTION_OPEN!r}, found '
                         f'{body.count(SECTION_OPEN)} - refusing')
    lines = [OLD_LINE % box for box in BOXES]
    for line in lines:
        if body.count(line) != 1:
            raise SystemExit(f'expected exactly one of {line!r}, found '
                             f'{body.count(line)} - refusing')
    block = '\n'.join(lines)
    if body.count(block) != 1:
        raise SystemExit('the four leaderboard lines are not consecutive and '
                         'in order - refusing')
    return body.replace(block, INVOKE)


def section_texts(body: str) -> tuple[str, str]:
    """The isolated OLD and NEW section fragments, for a section-only render.

    Season pages carry other <shtml> strips above and below this section (the
    seasonal numbers, the games list), so rendering the WHOLE page through
    {{עונת כדורגל}} - the way the referee comparison renders through
    {{שופט כדורגל/עוזר שופט}} - would pull those in too. This returns just
    the records container: OLD as production has it, NEW with the one line
    swapped in, both still wrapped in the SAME id-carrying div.
    """
    lines = [OLD_LINE % box for box in BOXES]
    old_block = '\n'.join(lines)
    if body.count(SECTION_OPEN) != 1 or body.count(old_block) != 1:
        raise SystemExit('could not isolate the שיאנים section - refusing')
    old = f'{SECTION_OPEN}\n{old_block}\n</div>'
    new = f'{SECTION_OPEN}\n{INVOKE}\n</div>'
    return old, new


def read_local(title: str) -> str:
    result = subprocess.run(
        ['docker', 'compose', '-f', COMPOSE, 'exec', '-T', 'mediawiki',
         'php', 'maintenance/getText.php', title],
        capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'reading {title} failed: {result.stderr[-400:]}')
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local', action='store_true', required=True,
                        help='read and write the LOCAL wiki (the only target)')
    parser.add_argument('--print', action='store_true',
                        help='print the candidate and stop')
    parser.add_argument('--apply', action='store_true',
                        help='write the real season template, not the '
                             'sandbox (undo: scripts/restore-db.sh)')
    options = parser.parse_args()

    live = read_local(TEMPLATE)
    candidate = candidate_of(live)
    if options.print:
        print(candidate)
        return

    from verify_tabs import write_local  # noqa: PLC0415 - path set above

    target = TEMPLATE if options.apply else SANDBOX
    write_local(target, candidate)
    print(f'wrote {target}')


if __name__ == '__main__':
    main()
