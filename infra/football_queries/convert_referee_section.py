"""Put the referee page's assistant leaderboards on one #invoke.

    uv run python infra/football_queries/convert_referee_section.py --local
    uv run python infra/football_queries/convert_referee_section.py --local --print

In `תבנית:שופט כדורגל/עוזר שופט` the four lines that call
`שופט כדורגל/הצגת שיאני …/עוזר שופט` - eight Cargo queries each - become one
`{{#invoke:FootballStatsBlock|leaderboards|…}}` that renders the same four
boxes, as tabbers, from one query. See .claude/referee_leaderboards_spec.md.

Production modes (each needs Roee's ack at the time):
    --prod-sandbox   write the candidate to the sandbox, nothing else
    --prod-apply     record the rollback, then switch the live section
    --prod-revert    restore the recorded text, unless edited since
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


ROLLBACK = Path('infra/football_queries/fixtures/referee_section_rollback.json')
APPLY_SUMMARY = ('שיאני עוזר השופט בשליפה אחת דרך [[יחידה:FootballStatsBlock]], '
                 'כטאבים - אותם מספרים, והטאבים עובדים')
REVERT_SUMMARY = 'חזרה לגרסת ה-shtml של שיאני עוזר השופט'


def production(options) -> int:
    """Sandbox, apply or revert on production. One page, one edit each."""
    import json
    import time

    sys.path.insert(0, 'infra/football_queries')
    sys.path.insert(0, 'packages/maccabipediabot/src')
    from compare_prod_day_pages import publish, read_page, site

    connection = site()
    live = read_page(connection, TEMPLATE)

    if options.prod_revert:
        if not ROLLBACK.exists():
            raise SystemExit(f'no rollback at {ROLLBACK} - refusing to guess')
        # Only undo OUR edit: if the section is no longer exactly the
        # converted text, someone edited it since and a blind revert would
        # throw that away.
        record = json.loads(ROLLBACK.read_text(encoding='utf-8'))
        if live.strip() != candidate_of(record['text']).strip():
            raise SystemExit('the live section is not the converted one any more '
                             '- edited after the switch. Refusing; revert by hand '
                             'from the rollback file.')
        print(f'restoring revision {record["revision"]}')
        result = publish(connection, TEMPLATE, record['text'], REVERT_SUMMARY)
        print(f'  {result}')
        return 0 if result == 'ok' else 1

    candidate = candidate_of(live)

    if options.prod_sandbox:
        result = publish(connection, SANDBOX, candidate,
                         'בדיקת שיאני עוזר שופט בשליפה אחת לפני החלפה')
        print(f'{SANDBOX}: {result}')
        return 0 if result == 'ok' else 1

    sandbox = read_page(connection, SANDBOX)
    if sandbox.strip() != candidate.strip():
        raise SystemExit('the sandbox does not hold this candidate - the check '
                         'that passed was of something else. Refusing.')

    import pywikibot as pw
    page = pw.Page(connection, TEMPLATE)
    revision = page.latest_revision
    # The text and the revision id from the same revision, and the page must
    # still be what the candidate was built from: publish sends no base
    # timestamp, so an edit landing in between would otherwise be overwritten
    # and the rollback would name the wrong revision.
    if revision.text.strip() != live.strip():
        raise SystemExit('the section changed while this ran - refusing; run again')
    ROLLBACK.write_text(json.dumps({
        'title': TEMPLATE, 'revision': revision.revid,
        'timestamp': str(revision.timestamp),
        'recorded': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'text': live,
    }, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'rollback recorded: revision {revision.revid} -> {ROLLBACK}')

    result = publish(connection, TEMPLATE, candidate, APPLY_SUMMARY)
    print(f'{TEMPLATE}: {result}')
    return 0 if result == 'ok' else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local', action='store_true',
                        help='read and write the LOCAL wiki')
    parser.add_argument('--print', action='store_true',
                        help='with --local: print the candidate and stop')
    parser.add_argument('--apply', action='store_true',
                        help='with --local: write the real section template, not '
                             'the sandbox (undo: scripts/restore-db.sh)')
    parser.add_argument('--prod-sandbox', action='store_true',
                        help='PRODUCTION: write the candidate to the sandbox only')
    parser.add_argument('--prod-apply', action='store_true',
                        help='PRODUCTION: record the rollback, then replace the '
                             'live section (refuses unless the sandbox holds '
                             'exactly this candidate)')
    parser.add_argument('--prod-revert', action='store_true',
                        help='PRODUCTION: restore the recorded rollback text')
    options = parser.parse_args()

    # Exactly one target: --local together with a production flag must not
    # quietly pick one of them.
    targets = [flag for flag in ('local', 'prod_sandbox', 'prod_apply', 'prod_revert')
               if getattr(options, flag)]
    if len(targets) != 1:
        raise SystemExit('pick exactly one of --local/--prod-sandbox/--prod-apply/'
                         f'--prod-revert, got {targets}')
    if (options.print or options.apply) and not options.local:
        raise SystemExit('--print and --apply are local options')
    if not options.local:
        sys.exit(production(options))

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
