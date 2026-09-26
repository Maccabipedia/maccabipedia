"""Production gate for the basketball game template's awarded-game header (Trello #598).

Every page is rendered twice on production with nothing saved: with the live
תבנית:משחק כדורסל, and with the repo candidate through TemplateSandbox. A probe appended to
the page prints the variables the template hands to Cargo (ResultOpt, Technical) and the
two header scores that drive the winner class, so "the result did not change" is compared,
not assumed.

    uv run python infra/lua_modules/compare_basketball_game_technical.py awarded PAGES_FILE
    uv run python infra/lua_modules/compare_basketball_game_technical.py sample PAGES_FILE

awarded - pages with |תוצאה בטכני=. The probe, the categories, the winner classes and
          all HTML outside the two score spans must be identical; the score spans must
          show exactly what expected_scores() derives from the page's own params.
sample  - every other page: the full HTML (probe included) and the categories must be
          byte-identical. A mismatch is rendered again both ways, and only one that
          survives counts.

Both modes refuse to pass if the candidate changed no awarded header (sample mode checks a
canary first): an ignored sandbox override would otherwise pass every check vacuously.
"""
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, 'infra/lua_modules')
sys.path.insert(0, 'infra/season_pages')
from compare_module_swap import call_multipart  # noqa: E402
from compare_stadium_leaderboards import page_text  # noqa: E402
from season_api import call  # noqa: E402

TEMPLATE = 'תבנית:משחק כדורסל'
CANDIDATE = Path('infra/lua_modules/wiki_templates/basketball_game.wiki')
CANARY = 'כדורסל:09-12-1976 מכבי תל אביב נגד ברנו - גביע אירופה לאלופות'
PROBE = ('\n<div id="mp598-probe">ResultOpt={{#var: אופטימיזציית תוצאה}};Technical={{#var: תוצאה טכני}};'
         'host={{#var: תוצאה מארחת}};away={{#var: תוצאה אורחת}}</div>')
PROBE_OUT = re.compile(r'<div id="mp598-probe">(.*?)</div>')
TEAM = re.compile(r'<div class="team-container ?([^"]*)">.*?<span class="score">([^<]*)</span>', re.S)
SCORE_SPAN = re.compile(r'<span class="score">[^<]*</span>')


def render(title: str, text: str, candidate: str | None) -> tuple[str, list[str]]:
    """One render, retried after a minute when production answers with a non-JSON page (its
    508 resource-limit page) - call_multipart has no retry of its own."""
    for attempt in range(1, 4):
        try:
            return render_once(title, text, candidate)
        except requests.exceptions.JSONDecodeError:
            if attempt == 3:
                raise
            print(f'    production answered with a non-JSON page - waiting 60s (attempt {attempt})', flush=True)
            time.sleep(60)
    raise AssertionError('unreachable')


def render_once(title: str, text: str, candidate: str | None) -> tuple[str, list[str]]:
    params = {'action': 'parse', 'title': title, 'text': text + PROBE, 'contentmodel': 'wikitext',
              'prop': 'text|categories', 'disablelimitreport': '1'}
    if candidate is None:
        data = call('prod', params, post=True)['parse']
    else:
        data = call_multipart(dict(params, templatesandboxtitle=TEMPLATE, templatesandboxtext=candidate,
                                   templatesandboxcontentmodel='wikitext'))['parse']
    return data['text'], sorted(f"{row['category']}|{row.get('sortkey', '')}" for row in data['categories'])


def param(text: str, name: str) -> str:
    match = re.search(r'\|\s*' + name + r'\s*=([^|}\n]*)', text)
    return match.group(1).strip() if match else ''


def expected_scores(text: str) -> tuple[str, str]:
    """(host, away) as the header must show them, from the page's own params: the entered
    score when both sides are entered and it is not 0:0, else 20:0 for the awarded side."""
    maccabi, opponent = param(text, 'תוצאת משחק מכבי'), param(text, 'תוצאת משחק יריבה')
    if not (maccabi and opponent) or (maccabi, opponent) == ('0', '0'):
        won = param(text, 'תוצאה בטכני') in ('ניצחון', 'נצחון')
        maccabi, opponent = ('20', '0') if won else ('0', '20')
    return (opponent, maccabi) if param(text, 'בית חוץ') == 'חוץ' else (maccabi, opponent)


def awarded(titles: list[str], candidate: str) -> int:
    failures, changed = 0, 0
    for title in titles:
        text = page_text(title)
        (old, old_categories), (new, new_categories) = render(title, text, None), render(title, text, candidate)
        old_teams, new_teams = TEAM.findall(old), TEAM.findall(new)
        problems = []
        if PROBE_OUT.findall(old) != PROBE_OUT.findall(new):
            problems.append(f'probe {PROBE_OUT.findall(old)} -> {PROBE_OUT.findall(new)}')
        if old_categories != new_categories:
            problems.append(f'categories {set(old_categories) ^ set(new_categories)}')
        if [cls for cls, _ in old_teams] != [cls for cls, _ in new_teams] or len(new_teams) != 2:
            problems.append(f'winner class {old_teams} -> {new_teams}')
        if SCORE_SPAN.sub('', old) != SCORE_SPAN.sub('', new):
            problems.append('HTML differs outside the score spans')
        shown = tuple(score.strip() for _, score in new_teams)
        if shown != expected_scores(text):
            problems.append(f'shows {shown}, expected {expected_scores(text)}')
        changed += [score for _, score in old_teams] != [score for _, score in new_teams]
        failures += bool(problems)
        print(f"  {'FAIL' if problems else 'ok  '} {title}: {[s for _, s in old_teams]} -> {list(shown)} "
              f"{[c for c, _ in new_teams]} {PROBE_OUT.findall(new)}", flush=True)
        for problem in problems:
            print(f'      {problem}')
    print(f'{failures} awarded page(s) failed, {changed} header(s) changed')
    return 1 if failures or not changed else 0


def sample(titles: list[str], candidate: str) -> int:
    # An ignored override would make every page "identical": the canary, an awarded page
    # with an entered score, must change first.
    text = page_text(CANARY)
    if render(CANARY, text, None) == render(CANARY, text, candidate):
        print(f'the candidate did not change {CANARY} - the override was not applied; refusing')
        return 1
    failures, unstable = 0, 0
    for number, title in enumerate(titles, 1):
        text = page_text(title)
        old, new = render(title, text, None), render(title, text, candidate)
        verdict = 'identical'
        if old != new:
            old2, new2 = render(title, text, None), render(title, text, candidate)
            if old2 == new2:
                verdict = 'identical on rerun'
            elif old2 != old:
                verdict, unstable = 'UNSTABLE (two unchanged renders differ)', unstable + 1
            else:
                verdict, failures = 'DIFFERS', failures + 1
                a, b = old[0], new[0]
                index = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
                start = max(0, index - 80)
                print(f'    at {index}: OLD {a[start:index + 120]!r}\n           NEW {b[start:index + 120]!r}')
                if old[1] != new[1]:
                    print(f'    categories {set(old[1]) ^ set(new[1])}')
        print(f'  {number}/{len(titles)} {title}: {verdict}', flush=True)
    print(f'{failures} page(s) differ, {unstable} unstable, {len(titles)} compared')
    return 1 if failures or unstable else 0


def main() -> int:
    mode, pages_file = sys.argv[1:3]
    titles = [line.strip() for line in Path(pages_file).read_text(encoding='utf-8').split('\n') if line.strip()]
    if '--start' in sys.argv:
        # Resume a sample run that stopped: skip the pages already compared (1-based count).
        titles = titles[int(sys.argv[sys.argv.index('--start') + 1]) - 1:]
    candidate = CANDIDATE.read_text(encoding='utf-8')
    return {'awarded': awarded, 'sample': sample}[mode](titles, candidate)


if __name__ == '__main__':
    sys.exit(main())
