"""Football profile pages rendered with the live template vs a candidate - byte for byte.

    uv run python infra/lua_modules/compare_profile_template.py FIX [--extra TITLE ...] [--seed N]
    uv run python infra/lua_modules/compare_profile_template.py FIX --selftest

READ-ONLY. FIX names a candidate written by make_profile_candidates.py
(wiki_templates/football_profile/FIX.wiki + FIX.sha1). Refuses if the live template is
no longer the revision the candidate was derived from.

Each sampled page's own wikitext is parsed twice on production, paced: OLD as live,
NEW with the candidate swapped in through TemplateSandbox. Page HTML and category list
must be identical. Also prints both build times (limit report walltime).

The sample covers the edges, not just the average: every player+coach page, keepers,
staff-only pages, pages with and without a photo gallery, pages without a profile
photo, plus a seeded random draw and any --extra titles.

--removed-errors is for a bug fix that is meant to change output: OLD with every
erroring ratio span (<span class="small"> holding a class="error") cut out must equal
NEW, and NEW must hold no error at all. Pages without such errors stay byte-identical.

--selftest swaps in the candidate with a visible marker right after its <includeonly>,
on three player+coach pages (they use every profile template): it must FAIL, which
proves the NEW side really renders the candidate.
"""
from __future__ import annotations

import argparse
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path('infra/season_pages')))
from season_api import call  # noqa: E402

CANDIDATES = Path('infra/lua_modules/wiki_templates/football_profile')
# A ratio span whose number_format failed: <span class="small"><span class="error">…</span> למשחק…</span>
ERROR_RATIO = re.compile(r'<span class="small"><span class="error">[^<]*</span>[^<]*</span>')
PROFILES = 'קטגוריה:פרופילי כדורגל'


def members(category: str) -> set[str]:
    titles, params = set(), {'action': 'query', 'list': 'categorymembers', 'cmtitle': category,
                             'cmlimit': 'max', 'cmnamespace': '0'}
    while True:
        data = call('prod', params)
        titles |= {m['title'] for m in data['query']['categorymembers']}
        if 'continue' not in data:
            return titles
        params.update(data['continue'])


def with_gallery(titles: list[str]) -> set[str]:
    found = set()
    for i in range(0, len(titles), 50):
        data = call('prod', {'action': 'query', 'prop': 'categoryinfo',
                             'titles': '|'.join(f'קטגוריה:{t}/תמונות' for t in titles[i:i + 50])}, post=True)
        for page in data['query']['pages']:
            if page.get('categoryinfo', {}).get('files', 0) > 0:
                found.add(page['title'].split(':', 1)[1].rsplit('/', 1)[0])
    return found


def sample(seed: int, extra: list[str]) -> list[str]:
    profiles = members(PROFILES)
    players, staff = members('קטגוריה:שחקני כדורגל'), members('קטגוריה:אנשי צוות כדורגל')
    keepers = members('קטגוריה:שוערים') & profiles
    no_photo = members('קטגוריה:פרופיל כדורגל ללא תמונה') & profiles
    gallery = with_gallery(sorted(profiles))
    draw = random.Random(seed)

    def some(pool: set[str], count: int) -> list[str]:
        pool_list = sorted(pool)
        return draw.sample(pool_list, min(count, len(pool_list)))

    chosen = (sorted(players & staff) + some(keepers & gallery, 5) + some(keepers - gallery, 3)
              + some(staff - players, 6) + some((players - staff) & gallery, 12)
              + some((players - staff) - gallery, 8) + some(no_photo, 5) + some(profiles, 10) + extra)
    return list(dict.fromkeys(chosen))


def render(title: str, wikitext: str, sandbox: tuple[str, str] | None) -> tuple[str, list[str], float]:
    params = {'action': 'parse', 'title': title, 'text': wikitext, 'contentmodel': 'wikitext',
              'prop': 'text|categories|limitreportdata', 'disablelimitreport': '1'}
    if sandbox:
        params.update(templatesandboxtitle=sandbox[0], templatesandboxtext=sandbox[1],
                      templatesandboxcontentmodel='wikitext')
    data = call('prod', params, post=True)['parse']
    report = {row['name']: row for row in data['limitreportdata']}
    categories = sorted(c['category'] for c in data['categories'])
    return data['text'], categories, float(report['limitreport-walltime']['0'])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('fix')
    parser.add_argument('--extra', nargs='*', default=[])
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--removed-errors', action='store_true',
                        help='a bug-fix gate: NEW must equal OLD minus its erroring ratio spans, with no errors left')
    options = parser.parse_args()
    template, sha1 = (CANDIDATES / f'{options.fix}.sha1').read_text(encoding='utf-8').splitlines()[:2]
    candidate = (CANDIDATES / f'{options.fix}.wiki').read_text(encoding='utf-8')
    live = call('prod', {'action': 'query', 'titles': template, 'prop': 'revisions', 'rvprop': 'sha1'})
    if live['query']['pages'][0]['revisions'][0]['sha1'] != sha1:
        raise SystemExit(f'{template} changed since the candidate was built - rebuild it')
    titles = sample(options.seed, options.extra)
    if options.selftest:
        if candidate.count('<includeonly>') < 1:
            raise SystemExit('selftest needs an <includeonly> to mark')
        candidate = candidate.replace('<includeonly>', '<includeonly>SELFTEST', 1)
        titles = sorted(members('קטגוריה:שחקני כדורגל') & members('קטגוריה:אנשי צוות כדורגל'))[:3]
    print(f'{options.fix}: {template} @ {sha1[:10]}, {len(titles)} pages', flush=True)
    failures, old_total, new_total = [], 0.0, 0.0
    for title in titles:
        wikitext = call('prod', {'action': 'parse', 'page': title, 'prop': 'wikitext'})['parse']['wikitext']
        old_html, old_categories, old_wall = render(title, wikitext, None)
        new_html, new_categories, new_wall = render(title, wikitext, (template, candidate))
        expected_html = ERROR_RATIO.sub('', old_html) if options.removed_errors else old_html
        same = expected_html == new_html and old_categories == new_categories
        if options.removed_errors and 'class="error' in new_html:
            same = False
        old_total, new_total = old_total + old_wall, new_total + new_wall
        if not same:
            failures.append(title)
        print(f'  {"same" if same else "DIFFERENT"}  {old_wall:.2f}s -> {new_wall:.2f}s  {title}', flush=True)
    print(f'build time over the sample: {old_total:.1f}s -> {new_total:.1f}s')
    if options.selftest:
        print('SELFTEST PASSED (the altered candidate was caught)' if failures else
              'SELFTEST FAILED - the altered candidate rendered identical; the NEW side is not the candidate')
        sys.exit(0 if failures else 1)
    print('PASS' if not failures else f'FAIL on {len(failures)}: {failures}')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
