"""Point the live day template at the modules, and be able to undo it.

    uv run python infra/lua_modules/migrate_day_template.py --apply
    uv run python infra/lua_modules/migrate_day_template.py --revert

One edit to one template, which reaches all 366 day pages at once - they all
transclude it, so there is no canary page. The safety net is the other way
round: the numbers every one of those pages publishes were recorded first
(capture_day_pages.py), all 366 were compared byte for byte against the module
through a sandbox copy, and this records the exact revision to go back to.

--revert restores the text that was live before --apply, from the rollback
file this writes. It does not guess: if the file is missing, it refuses.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, 'packages/maccabipediabot/src')

from compare_prod_day_pages import (  # noqa: E402
    SANDBOX, TEMPLATE, candidate_of, publish, read_page, site,
)

ROLLBACK = Path('infra/lua_modules/fixtures/day_template_rollback.json')

APPLY_SUMMARY = (
    'מעבר לשליפה אחת דרך [[יחידה:FootballStatsBlock]] - התוצאה זהה בית-בית '
    'ב-366 הדפים (28 שליפות במקום אחת)')
REVERT_SUMMARY = 'חזרה לגרסה שלפני המעבר ליחידת הלואה'


def apply_migration(connection) -> int:
    live = read_page(connection, TEMPLATE)
    candidate = candidate_of(live)

    sandbox = read_page(connection, SANDBOX)
    if sandbox.strip() != candidate.strip():
        raise SystemExit(
            'the sandbox copy is not what this would write - the comparison '
            'that passed was of something else. Refusing.')

    import pywikibot as pw

    page = pw.Page(connection, TEMPLATE)
    revision = page.latest_revision
    ROLLBACK.parent.mkdir(parents=True, exist_ok=True)
    ROLLBACK.write_text(json.dumps({
        'title': TEMPLATE,
        'revision': revision.revid,
        'timestamp': str(revision.timestamp),
        'recorded': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'text': live,
    }, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'rollback point recorded: revision {revision.revid} -> {ROLLBACK}')

    print(f'\nwriting {TEMPLATE}')
    result = publish(connection, TEMPLATE, candidate, APPLY_SUMMARY)
    print(f'  {result}')
    if result != 'ok':
        return 1

    print('\nthe live template now renders through the modules. Verify NOW:')
    print('  uv run python infra/lua_modules/capture_day_pages.py verify')
    print('and if anything differs:')
    print('  uv run python infra/lua_modules/migrate_day_template.py '
          '--revert')
    return 0


def revert_migration(connection) -> int:
    if not ROLLBACK.exists():
        raise SystemExit(
            f'no rollback point at {ROLLBACK} - refusing to guess what the '
            'template said before')
    record = json.loads(ROLLBACK.read_text(encoding='utf-8'))
    print(f'restoring {record["title"]} to revision {record["revision"]} '
          f'({record["timestamp"]})')
    result = publish(connection, record['title'], record['text'],
                     REVERT_SUMMARY)
    print(f'  {result}')
    return 0 if result == 'ok' else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true',
                        help='point the live template at the modules')
    parser.add_argument('--revert', action='store_true',
                        help='restore the text recorded by --apply')
    options = parser.parse_args()

    if options.apply == options.revert:
        parser.error('pass exactly one of --apply or --revert')

    connection = site()
    sys.exit(apply_migration(connection) if options.apply
             else revert_migration(connection))


if __name__ == '__main__':
    main()
