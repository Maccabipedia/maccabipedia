"""מספרים עונתיים: today's container against the two-query sandbox, byte for byte.

    uv run python infra/season_pages/compare_season_numbers.py --wiki local 1939 2023/24
    uv run python infra/season_pages/compare_season_numbers.py --wiki prod           # every season page
    uv run python infra/season_pages/compare_season_numbers.py --wiki prod --selftest

OLD is {{עונת כדורגל/הצגת מספרים עונתיים |עונה=S}}, NEW the same under
/ארגז חול (written by convert_season_numbers.py --sandbox, and on production
only with approval). The change swaps queries for primed values and leaves
all formatting in the templates, so every season must come out identical -
action=parse&text=, uncached, read-only.

Refuses to pass over nothing: each render must hold the four tab lists, and
--selftest (one season's OLD against another's NEW) must FAIL.
"""
from __future__ import annotations

import argparse
import sys

from season_api import WIKIS, call

OLD = '{{עונת כדורגל/הצגת מספרים עונתיים |עונה=%s }}'
NEW = '{{עונת כדורגל/הצגת מספרים עונתיים/ארגז חול |עונה=%s }}'
ERRORS = ('scribunto-error', 'class="error"', 'nothing primed')


def api(wiki: str, params: dict, post: bool = False) -> dict:
    return call(wiki, params, post)  # paced for production, with 508 back-off


QUERY_TEMPLATE = 'סטטיסטיקה/שליפות/מתקדמות/כמות נתוני משחק'
MODULE = 'FootballStatsBlock'
MODULE_NAMESPACE = 828


def render(wiki: str, season: str, template: str) -> tuple[str, list[dict]]:
    """The HTML, and every page the render transcluded (modules included)."""
    parsed = api(wiki, {'action': 'parse', 'title': f'עונת {season}',
                        'text': template % season, 'contentmodel': 'wikitext',
                        'prop': 'text|templates', 'disablelimitreport': 1},
                 post=True)['parse']
    return parsed['text'], parsed.get('templates', [])


def uses(templates: list[dict], namespace: int, name: str) -> bool:
    return any(page['ns'] == namespace and page['title'].split(':', 1)[-1] == name
               for page in templates)


def season_pages(wiki: str) -> list[str]:
    seasons, params = [], {'action': 'query', 'list': 'embeddedin', 'einamespace': '0',
                           'eititle': 'תבנית:עונת כדורגל', 'eilimit': 'max'}
    while True:
        data = api(wiki, params)
        seasons += [page['title'].removeprefix('עונת ') for page in data['query']['embeddedin']
                    if page['title'].startswith('עונת ')]
        if 'continue' not in data:
            return sorted(seasons)
        params.update(data['continue'])


def compare(wiki: str, season: str, new_season: str | None = None) -> tuple[str, str]:
    """('identical' | 'differs' | 'broken', detail). Only a clean pair of
    renders can be identical or differ; anything else is broken."""
    old, old_templates = render(wiki, season, OLD)
    new, new_templates = render(wiki, new_season or season, NEW)
    for label, html in (('old', old), ('new', new)):
        errors = [marker for marker in ERRORS if marker in html]
        if errors:
            return 'broken', f'{label} rendering carries {errors}'
        if html.count('general-stats-list') != 4:
            return 'broken', f'{label} rendering has {html.count("general-stats-list")} tab lists, not 4'
    # Each side must actually be the code it claims to be: a sandbox that is
    # a stale copy of the old pair would otherwise compare "identical" with it.
    if uses(old_templates, MODULE_NAMESPACE, MODULE) or not uses(old_templates, 10, QUERY_TEMPLATE):
        return 'broken', 'the OLD side is not the 32-query templates'
    if not uses(new_templates, MODULE_NAMESPACE, MODULE) or uses(new_templates, 10, QUERY_TEMPLATE):
        return 'broken', 'the NEW side does not read the primed blocks'
    if old == new:
        return 'identical', ''
    at = next((i for i, (a, b) in enumerate(zip(old, new)) if a != b), min(len(old), len(new)))
    return 'differs', (f'at {at}:\n    old …{old[max(0, at - 100):at + 100]!r}\n'
                       f'    new …{new[max(0, at - 100):at + 100]!r}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('seasons', nargs='*')
    parser.add_argument('--wiki', choices=sorted(WIKIS), required=True)
    parser.add_argument('--selftest', action='store_true')
    options = parser.parse_intermixed_args()

    if options.selftest:
        # Must come out 'differs' - two clean renders of the right code that
        # disagree. 'broken' would "fail" for a reason that proves nothing.
        verdict, detail = compare(options.wiki, '2023/24', new_season='2021/22')
        print(f'selftest: 2023/24 old vs 2021/22 new -> {verdict} {detail}'[:300])
        sys.exit(0 if verdict == 'differs' else 1)

    seasons = options.seasons or season_pages(options.wiki)
    if not seasons:
        raise SystemExit('no seasons to compare - refusing to pass over nothing')
    failing = []
    for season in seasons:
        verdict, detail = compare(options.wiki, season)
        if verdict != 'identical':
            failing.append(season)
            print(f'FAIL  {season}: {verdict} {detail}', flush=True)
    print(f'\n{len(seasons) - len(failing)}/{len(seasons)} seasons identical')
    sys.exit(1 if failing else 0)


if __name__ == '__main__':
    main()
