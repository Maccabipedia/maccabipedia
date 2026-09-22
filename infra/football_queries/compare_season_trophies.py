"""Production gate for Module:SeasonTrophies: does every season's trophy list survive?

`<ענף>/שליפות/רשימת זכיות לעונה` ran ONE #cargo_query per season (102 football + 75 basketball
+ 55 volleyball on `עונות`); it now calls {{#invoke:SeasonTrophies|list|ענף=…|עונה=…}}.

    seasons  every season each sport's page actually lists (read out of the LIVE rendered page,
             not re-queried - basketball and volleyball build their lists from categories),
             rendered OLD (the live template) and NEW (the candidate template, module published)
             and compared byte for byte, batched with markers. The selftest shifts the seasons on
             the NEW side by one: it must disagree. NEW must also list the module in prop=templates,
             or an ignored sandbox override would pass silently.
    pages     עונות, the three sport pages and עמוד ראשי: live vs candidate, one sport at a time
             (TemplateSandbox takes one title per request), comparing only the season rows.

Run from the repository root:
    uv run python infra/football_queries/compare_season_trophies.py seasons [ענף…]
    uv run python infra/football_queries/compare_season_trophies.py pages [ענף…]
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, 'infra/season_pages')
from season_api import call  # noqa: E402
from compare_stadium_leaderboards import page_text, parse  # noqa: E402

MODULE = 'Module:SeasonTrophies'
SPORTS = {
    'כדורגל': {'template': 'תבנית:כדורגל/שליפות/רשימת זכיות לעונה', 'page': 'כדורגל:עונות'},
    'כדורסל': {'template': 'תבנית:כדורסל/שליפות/רשימת זכיות לעונה', 'page': 'כדורסל:עונות'},
    'כדורעף': {'template': 'תבנית:כדורעף/שליפות/רשימת זכיות לעונה', 'page': 'כדורעף:עונות'},
}
SHARED_PAGES = ['עונות', 'עמוד ראשי']
BATCH = 40
SEASON = re.compile(r'<span>(\d{4}(?:/\d{2,4})?)</span>')


def candidate_of(sport: str, body: str) -> str:
    """The template with its #cargo_query replaced by the invoke, everything else kept."""
    query = re.search(r'\{\{#cargo_query:.*?\n\}\}', body, re.S)
    assert query, f'{sport}: no #cargo_query in the template'
    invoke = '{{#invoke:SeasonTrophies|list|ענף=' + sport + '|עונה={{{עונה|}}}}}'
    return body[:query.start()] + invoke + body[query.end():]


def seasons_of(sport: str) -> list[str]:
    """The seasons the sport's own page lists, read out of its live render."""
    page = SPORTS[sport]['page']
    html, _ = parse(page, page_text(page))
    seasons = list(dict.fromkeys(SEASON.findall(html)))
    assert len(seasons) > 40, f'{sport}: only {len(seasons)} seasons found on {page}'
    return seasons


def rendered(sport: str, seasons: list[str], candidate: str | None) -> tuple[list[str], str]:
    """Each season's list, from one parse, plus the templates that parse used."""
    text = ''.join(f'@@@{index}@@@{{{{{SPORTS[sport]["template"][len("תבנית:"):]} |עונה={season} }}}}'
                   for index, season in enumerate(seasons)) + f'@@@{len(seasons)}@@@'
    override = None if candidate is None else {
        'templatesandboxtitle': SPORTS[sport]['template'], 'templatesandboxtext': candidate,
        'templatesandboxcontentmodel': 'wikitext'}
    params = dict({'action': 'parse', 'title': 'ארגז חול', 'text': text, 'contentmodel': 'wikitext',
                   'prop': 'text|templates', 'disablelimitreport': '1'}, **(override or {}))
    data = call('prod', params, post=True)['parse']
    pieces = re.split(r'@@@(\d+)@@@', data['text'])
    found = {int(pieces[index]): pieces[index + 1] for index in range(1, len(pieces) - 1, 2)}
    assert sorted(found) == list(range(len(seasons) + 1)), 'markers lost'
    templates = ' '.join(entry['title'] for entry in data['templates'])
    return [found[index] for index in range(len(seasons))], templates


def compare_seasons(sport: str) -> int:
    seasons = seasons_of(sport)
    candidate = candidate_of(sport, page_text(SPORTS[sport]['template']))
    old: list[str] = []
    new: list[str] = []
    ran_module = False
    for start in range(0, len(seasons), BATCH):
        batch = seasons[start:start + BATCH]
        old += rendered(sport, batch, None)[0]
        pieces, templates = rendered(sport, batch, candidate)
        new += pieces
        ran_module = ran_module or 'SeasonTrophies' in templates or 'יחידה:SeasonTrophies' in templates
        print(f'  {sport} {len(old)}/{len(seasons)}', flush=True)
    problems = [f'{season}: OLD {before!r} NEW {after!r}'
                for season, before, after in zip(seasons, old, new) if before != after]
    with_trophies = sum(1 for piece in old if piece.strip())
    # The selftest: the same lists against the WRONG seasons must disagree, or the
    # comparison proves nothing (e.g. if every list came back empty).
    shifted = sum(1 for before, after in zip(old, new[1:]) if before != after)
    print(f'{sport}: {len(seasons) - len(problems)}/{len(seasons)} identical, '
          f'{with_trophies} seasons with trophies, module ran: {ran_module}, '
          f'selftest (shifted by one): {shifted} disagree')
    for line in problems[:10]:
        print('   ', line)
    ok = not problems and ran_module and with_trophies >= 20 and shifted >= 10
    return 0 if ok else 1


def compare_pages(sport: str) -> int:
    candidate = candidate_of(sport, page_text(SPORTS[sport]['template']))
    override = {'templatesandboxtitle': SPORTS[sport]['template'], 'templatesandboxtext': candidate,
                'templatesandboxcontentmodel': 'wikitext'}
    failed = 0
    for title in [SPORTS[sport]['page']] + SHARED_PAGES:
        text = page_text(title)
        old, old_wall = parse(title, text)
        new, new_wall = parse(title, text, override)
        # Only the season rows: the rest of עמוד ראשי (and the pages' galleries) differ
        # between two identical renders.
        old_rows = re.findall(r'<div class="season-list-item-container.*?</div>', old, re.S)
        new_rows = re.findall(r'<div class="season-list-item-container.*?</div>', new, re.S)
        same = old_rows == new_rows and old.count('שגיאת סקריפט') == new.count('שגיאת סקריפט')
        failed += not same
        print(f'  {title}: {len(old_rows)} season rows, '
              f'{"identical" if same else "DIFFERS"}  ({old_wall:.2f}s -> {new_wall:.2f}s)', flush=True)
        if not same:
            for before, after in list(zip(old_rows, new_rows))[:3]:
                if before != after:
                    print(f'    OLD {before[:200]!r}\n    NEW {after[:200]!r}')
    return failed


if __name__ == '__main__':
    mode, *wanted = sys.argv[1:] or ['seasons']
    sports = wanted or list(SPORTS)
    runner = compare_seasons if mode == 'seasons' else compare_pages
    sys.exit(sum(runner(sport) for sport in sports))
