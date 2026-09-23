"""A/B the OLD template text against the live module, right now.

    uv run python infra/lua_modules/ab_day_template.py 2026-09-14 ...

Why this exists: verifying the migration against a baseline captured earlier
cannot tell a migration defect from the data having changed since. Both
answers look identical - a number that differs.

So the pre-migration text (kept in the rollback file) is written to a second
sandbox page and rendered side by side with the live template AT THE SAME
MOMENT, over the same data. If they agree, any difference from the baseline is
the data moving on; if they disagree, it is the migration and the rollback
file is right there.

Read-only apart from that one sandbox page, which nothing transcludes.
"""
import difflib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, 'packages/maccabipediabot/src')

from compare_prod_day_pages import (  # noqa: E402
    TEMPLATE, publish, render, site,
)

ROLLBACK = Path('infra/lua_modules/fixtures/day_template_rollback.json')
BEFORE = TEMPLATE + '/ארגז חול לפני'
SUMMARY = ('ארגז חול עם הגרסה שלפני המעבר, להשוואה בזמן אמת - '
           'אף דף אינו קורא לו')


def main() -> None:
    dates = sys.argv[1:] or ['2026-09-14']

    if not ROLLBACK.exists():
        raise SystemExit(f'no rollback text at {ROLLBACK}')
    record = json.loads(ROLLBACK.read_text(encoding='utf-8'))

    connection = site()
    print(f'writing the pre-migration text to {BEFORE} '
          f'(revision {record["revision"]})')
    print(f'  {publish(connection, BEFORE, record["text"], SUMMARY)}')

    failures = 0
    for date in dates:
        before_html, before_ms = render(BEFORE, date)
        time.sleep(0.4)
        after_html, after_ms = render(TEMPLATE, date)
        time.sleep(0.4)

        if before_html == after_html:
            print(f'OK    {date}  identical now  '
                  f'(old {before_ms:.0f}ms, new {after_ms:.0f}ms)')
            continue

        failures += 1
        diff = '\n'.join(list(difflib.unified_diff(
            before_html.splitlines(), after_html.splitlines(),
            'pre-migration', 'live module', lineterm='', n=1))[:30])
        print(f'DIFF  {date}\n{diff}')

    print(f'\n{len(dates) - failures}/{len(dates)} identical against the '
          'pre-migration template, rendered at the same moment')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
