"""Compare the one-invoke tabber widget with the <shtml> strip it replaces.

    uv run python infra/lua_modules/compare_day_widget.py
    uv run python infra/lua_modules/compare_day_widget.py --dates 22-08,25-12
    uv run python infra/lua_modules/compare_day_widget.py --all

Both templates are rendered on the LOCAL wiki for the same date and compared
panel by panel, as visible text: the markup is deliberately different (radio
inputs and labels become a tabber), so only the words and numbers can be
compared, and those must be identical.

What this refuses to call a pass:

  * a panel count that differs, or a panel whose text differs;
  * an error marker in EITHER rendering - comparing two error messages proves
    nothing, and locally that is a real risk: the DB snapshot carries pages
    signed with production's SecureHTML secret, so an un-resigned <shtml>
    renders "שגיאה:גיבוב (hash) לא חוקי" in both;
  * a rendering with no numbers at all in it.
"""
from __future__ import annotations

import argparse
import html as html_module
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path('infra/tabs')))

from verify_tabs import ERROR_MARKERS, render  # noqa: E402

OLD_CALL = '{{סטטיסטיקה/תצוגה/ימים/סיכום תוצאות| תאריך="%s" }}'
NEW_CALL = '{{ארגז חול/ימים בטאברים| תאריך="%s" }}'

TAG = re.compile(r'<[^>]+>')

# The old strip's four panels, by the ids the template gives them.
OLD_PANEL = re.compile(r'<div id="tab([1-4])-content">(.*?)(?=<div id="tab'
                       r'[1-4]-content">|</div>\s*</div>\s*$)', re.S)
NEW_PANEL = re.compile(r'<article[^>]*class="[^"]*tabber__panel[^"]*"[^>]*>'
                       r'(.*?)</article>', re.S)
# The tab links only. A looser class match also catches the <nav
# class="tabber__tabs"> that holds them, and reports a phantom empty label.
NEW_LABEL = re.compile(r'<a[^>]*class="tabber__tab"[^>]*>([^<]*)</a>')

# Every date of the year, as the day pages pass them: a real date whose year is
# irrelevant, because the block matches on %d-%m.
def every_date() -> list[str]:
    from datetime import date, timedelta
    first = date(2020, 1, 1)          # a leap year, so 29-02 is included
    return [(first + timedelta(days=offset)).isoformat() for offset in range(366)]


def visible(fragment: str) -> str:
    return ' '.join(html_module.unescape(TAG.sub(' ', fragment)).split())


def numbers_in(text: str) -> list[str]:
    return re.findall(r'\d+', text)


def panels_of_old(page: str) -> list[str]:
    found = OLD_PANEL.findall(page)
    return [visible(body) for _, body in sorted(found, key=lambda pair: pair[0])]


def panels_of_new(page: str) -> tuple[list[str], list[str]]:
    return ([label.strip() for label in NEW_LABEL.findall(page)],
            [visible(body) for body in NEW_PANEL.findall(page)])


def errors_in(page: str) -> list[str]:
    return [marker for marker in ERROR_MARKERS if marker in page]


def compare(date: str, new_date: str | None = None) -> tuple[str, str]:
    """(verdict, detail) for one date.

    `new_date` renders the NEW widget for a different date than the old strip,
    which must fail. It is how --selftest shows this comparison can fail at
    all: a panel extractor that returned nothing would report every date as
    identical, and 366 green lines would mean nothing.
    """
    old = render(OLD_CALL % date)
    new = render(NEW_CALL % (new_date or date))

    for name, page in (('old', old), ('new', new)):
        found = errors_in(page)
        if found:
            return 'HOLLOW', f'{name} rendering contains {found}'

    old_panels = panels_of_old(old)
    labels, new_panels = panels_of_new(new)

    if len(old_panels) != 4:
        return 'HOLLOW', f'the old strip gave {len(old_panels)} panels, not 4'
    if len(new_panels) != 4:
        return 'FAIL', f'the tabber gave {len(new_panels)} panels, not 4'
    if labels != ['ליגה', 'גביע', 'אירופה', 'כל המסגרות']:
        return 'FAIL', f'labels are {labels}'

    for index, (before, after) in enumerate(zip(old_panels, new_panels)):
        if before != after:
            return 'FAIL', (f'panel {index + 1} ({labels[index]}) differs\n'
                            f'        old: {before}\n'
                            f'        new: {after}')
    # Every number the widget publishes, which is what --selftest compares
    # dates by: the first words of panel 1 are the same on every date, so a
    # pair chosen by those would be two dates that only LOOK identical.
    return 'ok', ','.join(numbers_in(' '.join(new_panels)))


def selftest() -> int:
    """Two dates whose numbers differ, compared crosswise. Must FAIL.

    Which dates those are depends on the dataset, so they are looked for
    rather than assumed: a pair picked by hand could easily be two quiet dates
    with identical zeroes, and crossing those proves nothing.
    """
    seen: dict[str, str] = {}
    for date in every_date():
        verdict, detail = compare(date)
        if verdict != 'ok':
            print(f'selftest: {date} does not even compare cleanly: {detail}')
            return 1
        seen[date] = detail
        differing = [other for other, text in seen.items() if text != detail]
        if not differing:
            continue

        verdict, detail = compare(differing[0], new_date=date)
        if verdict == 'ok':
            print(f'selftest FAILED: {differing[0]} vs {date} compared equal, '
                  'so this harness cannot fail')
            return 1
        print(f'selftest ok: {differing[0]} against {date} -> {verdict}')
        print(f'  {detail.splitlines()[0]}')
        return 0

    print('selftest inconclusive: every date renders the same text, so no '
          'crosswise pair exists in this dataset')
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dates', default='2021-08-22,2020-02-29,1900-01-01',
                        help='comma-separated dates to render')
    parser.add_argument('--all', action='store_true',
                        help='every day of the year (366 renders, slow)')
    parser.add_argument('--selftest', action='store_true',
                        help='show that a mismatch is reported as one')
    options = parser.parse_args()

    if options.selftest:
        sys.exit(selftest())

    dates = every_date() if options.all else options.dates.split(',')

    tally: dict[str, int] = {}
    for date in dates:
        verdict, detail = compare(date)
        tally[verdict] = tally.get(verdict, 0) + 1
        if verdict != 'ok' or not options.all:
            print(f'{verdict:7} {date}  {detail}')

    print('\n' + '  '.join(f'{verdict} {count}'
                           for verdict, count in sorted(tally.items())))
    sys.exit(0 if set(tally) <= {'ok'} else 1)


if __name__ == '__main__':
    main()
