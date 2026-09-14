"""Byte-identical comparison of a rendered block, template path vs module path.

Drops the module in place of the query template a display block calls, renders
both versions of the block on the local wiki, and diffs the HTML byte for byte.
Decision 5 of the design: any difference at all is a defect.

    uv run python infra/football_queries/compare_rendered_blocks.py --seed
    uv run python infra/football_queries/compare_rendered_blocks.py
    uv run python infra/football_queries/compare_rendered_blocks.py --selftest

`--seed` copies the templates this needs from production (read-only) into the
local wiki. `--selftest` proves the comparison can fail, which is the whole
point of it existing: of nine defects in an earlier attempt at this work, all
nine were in the checking and five reported success while comparing nothing.
"""
import argparse
import difflib
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request

API = 'http://localhost:8080/api.php'
COMPOSE_FILE = 'infra/local-wiki/docker-compose.yml'

BLOCK = 'תבנית:סטטיסטיקה/תצוגה/שחקנים/סיכום אירועים לפי מפעל'
QUERY_TEMPLATE = 'תבנית:סטטיסטיקה/שליפות/מתקדמות/כמות אירועי שחקן'

# The sandbox copies this harness owns. Suffixed so nothing here can be
# mistaken for a real page.
SANDBOX_QUERY = QUERY_TEMPLATE + '/ארגז חול מודול'
SANDBOX_BLOCK = BLOCK + '/ארגז חול מודול'
SANDBOX_QUERY_BODY = ('<includeonly>{{#invoke:FootballQueries|playerEventCount}}'
                      '</includeonly>')

# Pages the block needs, fetched from production when --seed is given.
DEPENDENCIES = [BLOCK, QUERY_TEMPLATE,
                'תבנית:סטטיסטיקה/תצוגה/שחקנים/סיכום אירועים',
                'תבנית:סטטיסטיקה/תצוגה/ימים/סיכום תוצאות לפי מפעל',
                'תבנית:סטטיסטיקה/תצוגה/ימים/סיכום תוצאות',
                'תבנית:סטטיסטיקה/שליפות/מתקדמות/כמות נתוני משחק',
                'תבנית:סטטיסטיקה/יחס',
                'תבנית:סטטיסטיקה/אחוזים', 'תבנית:המרות/שם ללא גרש וגרשיים']

# The four-tab parent: 8 queries per tab, 32 for the page.
TABS_TEMPLATE = 'תבנית:סטטיסטיקה/תצוגה/שחקנים/סיכום אירועים'
SANDBOX_TABS = TABS_TEMPLATE + '/ארגז חול מודול'
TAB_CASES = [
    {'שחקן': 'ערן זהבי'},
    {'שחקן': 'גבי קניקובסקי'},
    {'שחקן': 'דור פרץ'},
    {'שחקן': "דור תורג'מן"},
]

DAY_BLOCK = 'תבנית:סטטיסטיקה/תצוגה/ימים/סיכום תוצאות לפי מפעל'
SANDBOX_DAY = DAY_BLOCK + '/ארגז חול מודול'
DAY_BODY = ('<includeonly>{{#invoke:FootballStatsBlock|block'
            '|בלוק=day-results}}</includeonly>')
# Dates that fall inside the local seed, one per competition category.
DAY_CASES = [
    {'תאריך': '"2021-08-22"', 'קטגוריית מפעל': 'ליגה'},
    {'תאריך': '"2022-03-05"', 'קטגוריית מפעל': 'ליגה'},
    {'תאריך': '"2023-01-14"', 'קטגוריית מפעל': 'רשמי'},
    {'תאריך': '"2021-09-16"', 'קטגוריית מפעל': 'בינלאומי'},
    {'תאריך': '"2022-02-09"', 'קטגוריית מפעל': 'גביע'},
]

# Players present in the local seed (football 2021/22-2024/25).
CASES = [
    {'שחקן': 'ערן זהבי', 'קטגוריית מפעל': 'ליגה'},
    {'שחקן': 'ערן זהבי', 'קטגוריית מפעל': 'גביע'},
    {'שחקן': 'גבי קניקובסקי', 'קטגוריית מפעל': 'ליגה'},
    {'שחקן': 'דור פרץ', 'קטגוריית מפעל': 'ליגה'},
    {'שחקן': "דור תורג'מן", 'קטגוריית מפעל': 'ליגה'},
    {'שחקן': 'אופיר דוידזאדה', 'קטגוריית מפעל': 'רשמי'},
    # A player with no events in this category at all: the zero-denominator
    # branch, which prints a bare 0 rather than 0.00.
    {'שחקן': 'דן ביטון', 'קטגוריית מפעל': 'בינלאומי'},
]


def api(**params) -> dict:
    params.setdefault('format', 'json')
    request = urllib.request.Request(
        API, data=urllib.parse.urlencode(params).encode('utf-8'))
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode('utf-8'))


def write_local(title: str, text: str) -> None:
    result = subprocess.run(
        ['docker', 'compose', '-f', COMPOSE_FILE, 'exec', '-T', 'mediawiki',
         'php', 'maintenance/edit.php', '--user', 'Admin',
         '--summary', 'football_queries comparison harness', title],
        input=text, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'edit.php failed for {title}: {result.stderr[:300]}')


def read_local(title: str) -> str | None:
    result = subprocess.run(
        ['docker', 'compose', '-f', COMPOSE_FILE, 'exec', '-T', 'mediawiki',
         'php', 'maintenance/getText.php', title],
        capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


def seed_from_production() -> None:
    """Copy the pages this comparison needs from prod. Read-only on prod."""
    import pywikibot as pw

    from maccabipediabot.common.wiki_login import get_site

    site = get_site()
    for title in DEPENDENCIES:
        page = pw.Page(site, title)
        if not page.exists():
            print(f'  MISSING on prod: {title}')
            continue
        write_local(title, page.text)
        print(f'  seeded {len(page.text.encode("utf-8")):>6} bytes  {title}')


def assert_wiki_matches_repo() -> None:
    """Refuse to report a result about code that is not the code in the repo.

    Without this, a green comparison can describe modules deployed three edits
    ago - the harness would be measuring something nobody can review.
    """
    result = subprocess.run(
        ['uv', 'run', 'python', 'infra/football_queries/deploy_modules.py',
         '--status'], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'could not check deployment: {result.stderr[:300]}')
    # Parse the count instead of matching a substring. "10 page(s) would
    # change" CONTAINS "0 page(s) would change", so the obvious check passed
    # when nothing was deployed at all - the exact case it exists to catch,
    # and the guard would then certify a green comparison about code on no
    # wiki.
    match = re.search(r'^(\d+) page\(s\) would change', result.stdout,
                      re.MULTILINE)
    if not match:
        raise SystemExit(
            'could not read the deployment status:\n' + result.stdout)
    changed = int(match.group(1))
    if changed:
        raise SystemExit(
            f'{changed} page(s) differ between the wiki and the repo - run '
            'deploy_modules.py before comparing:\n' + result.stdout)
    print('  (deployed modules match the repo)')


def render(wikitext: str) -> str:
    parsed = api(action='parse', text=wikitext, title='עונת 2021/22',
                 contentmodel='wikitext', prop='text', formatversion=2,
                 disablelimitreport=1)
    return parsed['parse']['text']


def call(template: str, params: dict) -> str:
    arguments = ''.join(f'|{name}={value}' for name, value in params.items())
    return '{{' + template + arguments + '}}'


RENDERER_BODY = '<includeonly>{{#invoke:FootballStatsBlock|block}}</includeonly>'


def build_renderer_candidate() -> None:
    """The renderer path: the whole block from one query, in Lua.

    This is the real target - not the query template swapped out underneath the
    template, but the block itself replaced. Byte-identical output is the
    requirement, so the candidate is simply the invoke.
    """
    write_local(SANDBOX_BLOCK, RENDERER_BODY)


def build_tabs_candidate() -> None:
    """The whole four-tab block from one query.

    The signed <shtml> strip is copied through byte-for-byte from the page on
    this wiki - its hash is an HMAC under a per-wiki secret and cannot be
    regenerated, so it is never rebuilt, only surrounded. `prime` runs before
    it and each tab body becomes a variable read.
    """
    original = read_local(TABS_TEMPLATE)
    if not original:
        raise SystemExit(
            f'{TABS_TEMPLATE} is not on the local wiki - run with --seed')

    body = original.replace(
        '<includeonly>\n',
        '<includeonly>{{#invoke:FootballStatsBlock|prime}}\n', 1)
    if body == original:
        raise SystemExit('could not place prime before the tab strip')

    # Each tab call becomes a variable read for that category.
    for category in ['רשמי', 'ליגה', 'גביע', 'בינלאומי']:
        call = ('{{תבנית: סטטיסטיקה/תצוגה/שחקנים/סיכום אירועים לפי מפעל| '
                f'קטגוריית מפעל={category}| שחקן={{{{{{שחקן}}}}}} }}}}')
        replacement = ('{{#invoke:FootballStatsBlock|tab|'
                       f'קטגוריית מפעל={category}|שחקן={{{{{{שחקן}}}}}}}}}}')
        if call not in body:
            raise SystemExit(f'tab call for {category} not found as expected')
        body = body.replace(call, replacement, 1)

    write_local(SANDBOX_TABS, body)


def build_candidate(corrupt: bool = False) -> None:
    """The shim path: the block, with its query template swapped for the shim."""
    write_local(SANDBOX_QUERY, SANDBOX_QUERY_BODY)

    original = read_local(BLOCK)
    if not original:
        raise SystemExit(
            f'{BLOCK} is not on the local wiki - run with --seed first')

    # The block calls the query template as "תבנית: סטטיסטיקה/..." with a space
    # after the namespace, so match on the part after it.
    body = original.replace(QUERY_TEMPLATE.removeprefix('תבנית:'),
                            SANDBOX_QUERY.removeprefix('תבנית:'))
    if body == original:
        raise SystemExit('the query template name was not found in the block')

    if corrupt:
        # One cell asks for the wrong event. The comparison MUST notice.
        body = body.replace('מספר אירוע=4', 'מספר אירוע=3', 1)

    write_local(SANDBOX_BLOCK, body)


def compare(params: dict, original: str = BLOCK,
            candidate: str = SANDBOX_BLOCK) -> tuple[bool, str]:
    before = render(call(original, params))
    after = render(call(candidate, params))
    if before == after:
        return True, ''

    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile='template path', tofile='module path', lineterm='', n=1)
    return False, '\n'.join(list(diff)[:14])


def assert_renderer_is_in_the_path() -> None:
    body = read_local(SANDBOX_BLOCK) or ''
    if 'FootballStatsBlock' not in body:
        raise SystemExit(
            'the candidate block does not invoke the renderer - this '
            'comparison would be the template path against itself')
    print('  (renderer is the candidate)')


def assert_module_is_in_the_path() -> None:
    """Refuse to report anything until the module is proven to be in the loop.

    The previous harness in this directory compared production against
    production and reported success while nothing rendered the module. So check
    that the shim answers with a number and that the candidate block reaches
    it, before any comparison result is believable.
    """
    probe = render(call(SANDBOX_QUERY,
                        {'שחקן': 'ערן זהבי', 'מספר אירוע': '3'}))
    number = ''.join(character for character in probe if character.isdigit())
    if not number or 'שגיאת' in probe or 'error' in probe.lower():
        raise SystemExit(
            f'the module shim did not answer with a number: {probe[:200]!r}')

    body = read_local(SANDBOX_BLOCK) or ''
    if 'ארגז חול מודול' not in body:
        raise SystemExit(
            'the candidate block does not call the shim - this comparison '
            'would be the template path against itself')
    print(f'  (module reachable: shim returned {number})')


def run_cases(renderer: bool = False) -> int:
    # Every path, not just --tabs: a comparison that might be describing stale
    # code is not evidence whichever mode produced it.
    assert_wiki_matches_repo()
    if renderer:
        assert_renderer_is_in_the_path()
    else:
        assert_module_is_in_the_path()
    failures = 0
    for params in CASES:
        label = ' '.join(f'{name}={value}' for name, value in params.items())
        identical, diff = compare(params)
        if identical:
            print(f'OK    {label}')
        else:
            failures += 1
            print(f'DIFF  {label}\n{diff}')
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', action='store_true',
                        help='copy the needed templates from prod (read-only)')
    parser.add_argument('--selftest', action='store_true',
                        help='prove the comparison passes when identical and '
                             'fails when a single cell is wrong')
    parser.add_argument('--renderer', action='store_true',
                        help='compare the Lua renderer instead of the shim')
    parser.add_argument('--tabs', action='store_true',
                        help='compare the whole four-tab block: 32 queries vs 1')
    parser.add_argument('--day', action='store_true',
                        help='compare the day-results block, the one with 366 '
                             'live callers')
    options = parser.parse_args()

    if options.seed:
        print('seeding from production:')
        seed_from_production()

    if options.selftest and not options.tabs:
        print('--- part 1: identical input must report no difference ---')
        build_candidate(corrupt=False)
        clean_failures = run_cases()
        print(f'  {clean_failures} difference(s); expected 0')

        print('\n--- part 2: one wrong cell must be reported ---')
        build_candidate(corrupt=True)
        corrupt_failures = run_cases()
        print(f'  {corrupt_failures} difference(s); expected at least 1')

        build_candidate(corrupt=False)
        if clean_failures == 0 and corrupt_failures > 0:
            print('\nSELFTEST PASSED: the comparison can both pass and fail')
            sys.exit(0)
        print('\nSELFTEST FAILED: this harness is not evidence')
        sys.exit(1)

    if options.day:
        assert_wiki_matches_repo()
        write_local(SANDBOX_DAY, DAY_BODY)
        failures = 0
        for params in DAY_CASES:
            label = ' '.join(f'{n}={v}' for n, v in params.items())
            identical, diff = compare(params, DAY_BLOCK, SANDBOX_DAY)
            if identical:
                print(f'OK    {label}')
            else:
                failures += 1
                print(f'DIFF  {label}\n{diff}')
        print(f'\n{len(DAY_CASES) - failures}/{len(DAY_CASES)} day blocks '
              'byte-identical')
        sys.exit(1 if failures else 0)

    if options.tabs:
        assert_wiki_matches_repo()

        def run_tabs() -> int:
            # The baseline must be the template, not another copy of the
            # module: comparing the module with itself passes for free.
            baseline = read_local(TABS_TEMPLATE) or ''
            if 'FootballStatsBlock' in baseline:
                raise SystemExit(
                    'the baseline template already invokes the module - this '
                    'would be the module compared with itself')
            candidate = read_local(SANDBOX_TABS) or ''
            if 'FootballStatsBlock' not in candidate:
                raise SystemExit('the candidate does not invoke the module')

            inner = 0
            for params in TAB_CASES:
                label = ' '.join(f'{n}={v}' for n, v in params.items())
                identical, diff = compare(params, TABS_TEMPLATE, SANDBOX_TABS)
                if identical:
                    print(f'OK    {label}  (4 tabs, one query)')
                else:
                    inner += 1
                    print(f'DIFF  {label}\n{diff}')
            return inner

        if options.selftest:
            print('--- part 1: the real candidate must match ---')
            build_tabs_candidate()
            clean = run_tabs()
            print(f'  {clean} difference(s); expected 0')

            print('\n--- part 2: one wrong tab must be reported ---')
            build_tabs_candidate()
            broken = (read_local(SANDBOX_TABS) or '').replace(
                'קטגוריית מפעל=גביע', 'קטגוריית מפעל=ליגה', 1)
            write_local(SANDBOX_TABS, broken)
            corrupt = run_tabs()
            print(f'  {corrupt} difference(s); expected at least 1')

            build_tabs_candidate()
            if clean == 0 and corrupt > 0:
                print('\nSELFTEST PASSED: the tab comparison can pass and fail')
                sys.exit(0)
            print('\nSELFTEST FAILED: this comparison is not evidence')
            sys.exit(1)

        build_tabs_candidate()
        failures = run_tabs()
        print(f'\n{len(TAB_CASES) - failures}/{len(TAB_CASES)} four-tab blocks '
              'byte-identical')
        sys.exit(1 if failures else 0)

    if options.renderer:
        build_renderer_candidate()
        failures = run_cases(renderer=True)
    else:
        build_candidate()
        failures = run_cases()
    print(f'\n{len(CASES) - failures}/{len(CASES)} blocks byte-identical')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
