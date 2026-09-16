"""Put the referee page's assistant leaderboards on one #invoke.

    uv run python infra/football_queries/convert_referee_section.py --local
    uv run python infra/football_queries/convert_referee_section.py --local --print

In `תבנית:שופט כדורגל/עוזר שופט` the four lines that call
`שופט כדורגל/הצגת שיאני …/עוזר שופט` - eight Cargo queries each - become one
`{{#invoke:FootballStatsBlock|leaderboards|…}}` that renders the same four
boxes, as tabbers, from one query. See .claude/referee_leaderboards_spec.md.

Local only. Production is a separate, approved step.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path('infra/tabs')))

COMPOSE = 'infra/local-wiki/docker-compose.yml'
TEMPLATE = 'תבנית:שופט כדורגל/עוזר שופט'
SANDBOX = TEMPLATE + '/ארגז חול לידרבורדים'

BOXES = ('הופעות', 'כיבושים', 'בישולים', 'מוצהבים')
OLD_LINE = '{{שופט כדורגל/הצגת שיאני %s/עוזר שופט |שם להצגה={{#var: שם להצגה}} }}'
INVOKE = ('{{#invoke:FootballStatsBlock|leaderboards|בלוק=referee-assistant'
          '|שופט={{#var: שם להצגה}}}}')


def candidate_of(body: str) -> str:
    """The section with its four leaderboard lines replaced by one invoke.

    Each line must be present exactly once and the four must be consecutive,
    in order - anything else is a template this was not written for, and a
    candidate that quietly replaced less than all four would still compare
    the remaining boxes against themselves.
    """
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
                        help='write the real section template, not the '
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
