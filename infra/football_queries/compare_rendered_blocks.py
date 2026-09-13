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
SANDBOX_QUERY_BODY = '<includeonly>{{#invoke:FootballQueries|gameDataCount}}</includeonly>'

# Pages the block needs, fetched from production when --seed is given.
DEPENDENCIES = [BLOCK, QUERY_TEMPLATE, 'תבנית:סטטיסטיקה/יחס',
                'תבנית:סטטיסטיקה/אחוזים', 'תבנית:המרות/שם ללא גרש וגרשיים']

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


def render(wikitext: str) -> str:
    parsed = api(action='parse', text=wikitext, title='עונת 2021/22',
                 contentmodel='wikitext', prop='text', formatversion=2,
                 disablelimitreport=1)
    return parsed['parse']['text']


def call(template: str, params: dict) -> str:
    arguments = ''.join(f'|{name}={value}' for name, value in params.items())
    return '{{' + template + arguments + '}}'


RENDERER_BODY = '<includeonly>{{#invoke:FootballPlayerEvents|block}}</includeonly>'


def build_renderer_candidate() -> None:
    """The renderer path: the whole block from one query, in Lua.

    This is the real target - not the query template swapped out underneath the
    template, but the block itself replaced. Byte-identical output is the
    requirement, so the candidate is simply the invoke.
    """
    write_local(SANDBOX_BLOCK, RENDERER_BODY)


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


def compare(params: dict) -> tuple[bool, str]:
    before = render(call(BLOCK, params))
    after = render(call(SANDBOX_BLOCK, params))
    if before == after:
        return True, ''

    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile='template path', tofile='module path', lineterm='', n=1)
    return False, '\n'.join(list(diff)[:14])


def assert_renderer_is_in_the_path() -> None:
    body = read_local(SANDBOX_BLOCK) or ''
    if 'FootballPlayerEvents' not in body:
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
    options = parser.parse_args()

    if options.seed:
        print('seeding from production:')
        seed_from_production()

    if options.selftest:
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
