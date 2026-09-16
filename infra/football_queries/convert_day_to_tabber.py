"""Turn the day template into ONE #invoke that emits the whole widget.

    uv run python infra/football_queries/convert_day_to_tabber.py --local
    uv run python infra/football_queries/convert_day_to_tabber.py --local --dates 22-08,01-01

What it replaces, and why there is anything left to replace: the day family
already runs on one query, but it took five #invoke calls to get there - prime
computed all 24 numbers and stashed them in page variables, and four more
invokes read them back out. That detour existed for one reason: the tab strip
was a signed <shtml> block whose HMAC cannot be regenerated, so the strip had
to stay in the wikitext and the numbers had to be handed around it.

Emitting the strip as a <tabber> removes the reason. One invoke renders the
strip, the headings and all four panels, and the page variables - and the
namespace they shared with every other template on the page - go with it.

The candidate is built by replacing the template's whole <includeonly> body,
which is checked to be the shape this expects before anything is written.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path('infra/tabs')))

COMPOSE = 'infra/local-wiki/docker-compose.yml'

TEMPLATE = 'תבנית:סטטיסטיקה/תצוגה/ימים/סיכום תוצאות'
SANDBOX = 'תבנית:ארגז חול/ימים בטאברים'

INVOKE = '{{#invoke:FootballStatsBlock|render|בלוק=day-results}}'

BODY = re.compile(r'<includeonly>.*?</includeonly>', re.S)


def candidate_of(body: str) -> str:
    """The template with its whole rendering body replaced by one invoke.

    Guarded three ways, because a candidate that quietly changed nothing would
    be compared against the original and pass:

      * exactly one <includeonly> region, or this refuses;
      * that region must contain the signed <shtml> strip this exists to
        remove - it is the marker that says we are looking at the widget and
        not at some already-converted page;
      * the result must differ from what came in.
    """
    regions = BODY.findall(body)
    if len(regions) != 1:
        raise SystemExit(
            f'expected exactly one <includeonly> region, found {len(regions)} '
            '- refusing to guess which one renders the widget')
    if '<shtml' not in regions[0]:
        raise SystemExit(
            'the <includeonly> body has no <shtml> strip, so this is not the '
            'widget this converts (already converted?). Refusing.')

    candidate = body.replace(regions[0], f'<includeonly>{INVOKE}</includeonly>')
    if candidate == body:
        raise SystemExit('the candidate is identical to the original')
    return candidate


def read_local(title: str) -> str:
    result = subprocess.run(
        ['docker', 'compose', '-f', COMPOSE, 'exec', '-T', 'mediawiki',
         'php', 'maintenance/getText.php', title],
        capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'reading {title} failed: {result.stderr[-400:]}')
    return result.stdout


PROD_SANDBOX = TEMPLATE + '/ארגז חול טאברים'
ROLLBACK = Path('infra/football_queries/fixtures/day_template_tabber_rollback.json')
APPLY_SUMMARY = ('תצוגה בקריאה אחת ל-[[יחידה:FootballStatsBlock]] עם טאבים '
                 '(tabber) במקום shtml - מספרים זהים ב-366 התאריכים')
REVERT_SUMMARY = 'חזרה לגרסת ה-shtml שלפני המעבר לטאבים'


def production(options) -> int:
    """Sandbox, apply or revert on production. One page, one edit each."""
    import json
    import time

    sys.path.insert(0, 'infra/football_queries')
    sys.path.insert(0, 'packages/maccabipediabot/src')
    from compare_prod_day_pages import publish, read_page, site

    connection = site()

    if options.prod_revert:
        if not ROLLBACK.exists():
            raise SystemExit(f'no rollback at {ROLLBACK} - refusing to guess')
        record = json.loads(ROLLBACK.read_text(encoding='utf-8'))
        # Only undo OUR edit. If the live template is no longer exactly the
        # one-invoke body, someone has edited it since, and writing the old
        # text back would silently throw their change away.
        live = read_page(connection, TEMPLATE)
        if f'<includeonly>{INVOKE}</includeonly>' not in live:
            raise SystemExit('the live template is not the converted one any '
                             'more - it was edited after the switch. Refusing '
                             'to overwrite; revert by hand from the rollback '
                             'file.')
        print(f'restoring revision {record["revision"]}')
        result = publish(connection, TEMPLATE, record['text'], REVERT_SUMMARY)
        print(f'  {result}')
        return 0 if result == 'ok' else 1

    live = read_page(connection, TEMPLATE)
    candidate = candidate_of(live)

    if options.prod_sandbox:
        result = publish(connection, PROD_SANDBOX, candidate,
                         'בדיקת תצוגת טאברים לפני החלפה')
        print(f'{PROD_SANDBOX}: {result}')
        return 0 if result == 'ok' else 1

    sandbox = read_page(connection, PROD_SANDBOX)
    if sandbox.strip() != candidate.strip():
        raise SystemExit('the sandbox does not hold this candidate - the check '
                         'that passed was of something else. Refusing.')

    import pywikibot as pw
    revision = pw.Page(connection, TEMPLATE).latest_revision
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
                        help='print the candidate and stop')
    parser.add_argument('--apply', action='store_true',
                        help='write the REAL template on the local wiki, not '
                             'the sandbox. Undo with scripts/restore-db.sh, '
                             'which restores the committed snapshot')
    parser.add_argument('--prod-sandbox', action='store_true',
                        help='PRODUCTION: write the candidate to a sandbox '
                             'template only')
    parser.add_argument('--prod-apply', action='store_true',
                        help='PRODUCTION: record the rollback, then replace '
                             'the live template (refuses unless the sandbox '
                             'holds exactly this candidate)')
    parser.add_argument('--prod-revert', action='store_true',
                        help='PRODUCTION: restore the recorded rollback text')
    options = parser.parse_args()

    # Exactly one target. `--local --prod-apply` used to reach production, and
    # `--prod-sandbox --prod-apply` quietly ran only the sandbox write.
    chosen = [flag for flag in ('local', 'prod_sandbox', 'prod_apply', 'prod_revert')
              if getattr(options, flag)]
    if len(chosen) > 1:
        raise SystemExit(f'pick one of --local/--prod-sandbox/--prod-apply/'
                         f'--prod-revert, got {chosen}')
    if options.prod_sandbox or options.prod_apply or options.prod_revert:
        sys.exit(production(options))
    if not options.local:
        raise SystemExit('pass --local, or one of the --prod-* modes')

    live = read_local(TEMPLATE)
    candidate = candidate_of(live)

    if options.print:
        print(candidate)
        return

    from verify_tabs import write_local  # noqa: PLC0415 - path set above

    target = TEMPLATE if options.apply else SANDBOX
    write_local(target, candidate)
    print(f'wrote {target} ({len(candidate)} bytes, was {len(live)})')
    if options.apply:
        return
    print('compare it with:')
    print('  uv run python infra/football_queries/compare_day_widget.py')


if __name__ == '__main__':
    main()
