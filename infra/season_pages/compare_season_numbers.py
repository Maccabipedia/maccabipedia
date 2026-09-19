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

from wiki_api import WIKIS, call

OLD = '{{עונת כדורגל/הצגת מספרים עונתיים |עונה=%s }}'
NEW = '{{עונת כדורגל/הצגת מספרים עונתיים/ארגז חול |עונה=%s }}'
ERRORS = ('scribunto-error', 'class="error"', 'nothing primed')


def api(wiki: str, params: dict, post: bool = False) -> dict:
    return call(wiki, params, post)  # paced for production, with 508 back-off


def render(wiki: str, season: str, template: str) -> str:
    return api(wiki, {'action': 'parse', 'title': f'עונת {season}', 'text': template % season,
                      'contentmodel': 'wikitext', 'prop': 'text',
                      'disablelimitreport': 1}, post=True)['parse']['text']


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


def compare(wiki: str, season: str, new_season: str | None = None) -> str | None:
    old = render(wiki, season, OLD)
    new = render(wiki, new_season or season, NEW)
    for label, html in (('old', old), ('new', new)):
        errors = [marker for marker in ERRORS if marker in html]
        if errors:
            return f'{label} rendering carries {errors}'
        if html.count('general-stats-list') != 4:
            return f'{label} rendering has {html.count("general-stats-list")} tab lists, not 4'
    if old == new:
        return None
    at = next((i for i, (a, b) in enumerate(zip(old, new)) if a != b), min(len(old), len(new)))
    return (f'differs at {at}:\n    old …{old[max(0, at - 100):at + 100]!r}\n'
            f'    new …{new[max(0, at - 100):at + 100]!r}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('seasons', nargs='*')
    parser.add_argument('--wiki', choices=sorted(WIKIS), required=True)
    parser.add_argument('--selftest', action='store_true')
    options = parser.parse_intermixed_args()

    if options.selftest:
        problem = compare(options.wiki, '2023/24', new_season='2021/22')
        print(f'selftest: 2023/24 old vs 2021/22 new -> {problem or "IDENTICAL"}'[:300])
        sys.exit(0 if problem else 1)

    seasons = options.seasons or season_pages(options.wiki)
    failing = []
    for season in seasons:
        problem = compare(options.wiki, season)
        if problem:
            failing.append(season)
            print(f'FAIL  {season}: {problem}', flush=True)
    print(f'\n{len(seasons) - len(failing)}/{len(seasons)} seasons identical')
    sys.exit(1 if failing else 0)


if __name__ == '__main__':
    main()
