"""Player page statistics columns: the query templates against Module:FootballPlayerStats - batched.

    uv run python infra/lua_modules/compare_player_stats.py [--limit N] [--batch 4]
    uv run python infra/lua_modules/compare_player_stats.py --selftest
    uv run python infra/lua_modules/compare_player_stats.py --print

READ-ONLY. Renders the column `{{פרופיל כדורגל/הצגת עמודת סטטיסטיקה/שחקן |שם להצגה=… |האם שוער=כן}}`
for several players per action=parse, separated by markers: OLD with the live
`…/שחקן/הצגה`, NEW with the candidate (its 15 query calls replaced by value calls
of the published module) through TemplateSandbox. As a keeper - that view holds
every row; the outfield view is the same template with the keeper rows left out.

Per player: the column byte-identical, and the official appearances number equal to a
direct Cargo COUNT(DISTINCT game) written here. NEW must really use the module: its
parse lists Module:FootballPlayerStats among the templates it used.
Allowed: the one player whose name carries a double quote (the templates' SQL broke on
it) - reported, checked against Cargo instead. --selftest renders two players swapped
on the NEW side and must FAIL.
"""
from __future__ import annotations

import argparse
import html as html_module
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path('infra/lua_modules')))
sys.path.insert(0, str(Path('infra/season_pages')))
from compare_stadium_leaderboards import page_text  # noqa: E402
from season_api import call  # noqa: E402

DISPLAY = 'תבנית:פרופיל כדורגל/הצגת עמודת סטטיסטיקה/שחקן/הצגה'
COLUMN = '{{פרופיל כדורגל/הצגת עמודת סטטיסטיקה/שחקן |שם להצגה=%s |האם שוער=כן}}'
CELL_OF = {'הופעות': 'appearances', 'הופעות כמחליף': 'substitutions', 'שערים': 'goals',
           'שערים בפנדל': 'penaltyGoals', 'בישולים': 'assists', 'בישולים-סחיטת פנדל': 'penaltiesWon',
           'ספיגות': 'conceded', 'שער נקי': 'cleanSheets', 'ספיגות פנדלים': 'penaltiesConceded',
           'הדיפות פנדלים': 'penaltySaves', 'צהובים': 'yellows', 'אדומים': 'reds',
           'ניצחונות': 'wins', 'תיקו': 'draws', 'הפסדים': 'losses'}
VARDEFINE = re.compile(r'\{\{#vardefine: ([^|]+?) \|\{\{[^\n]*\}\} \}\}')
MARKER = '@@@PLAYER-%d@@@'
APPEARANCES = re.compile(r'<span class="describe">הופעות</span>\s*<span class="info">(\d+) ')


def candidate_of(body: str) -> str:
    found = []

    def replace(match: re.Match) -> str:
        name = match.group(1).strip()
        if name not in CELL_OF:
            return match.group(0)
        found.append(name)
        return ('{{#vardefine: ' + name + ' |{{#invoke:FootballPlayerStats|value|שחקן={{#var: שם להצגה}}'
                '|קטגוריית מפעל={{{קטגוריית מפעל|}}}|תא=' + CELL_OF[name] + '}} }}')
    candidate = VARDEFINE.sub(replace, body)
    if sorted(found) != sorted(CELL_OF):
        raise SystemExit(f'expected the 15 number definitions once each, replaced {found} - refusing')
    return candidate


def render(names: list[str], override: dict | None) -> tuple[list[str], str]:
    text = ''.join(MARKER % index + COLUMN % name for index, name in enumerate(names)) + MARKER % len(names)
    params = {'action': 'parse', 'title': 'ארגז חול', 'contentmodel': 'wikitext', 'text': text,
              'prop': 'text|templates', 'disablelimitreport': '1'}
    data = call('prod', dict(params, **(override or {})), post=True)['parse']
    html = data['text']
    parts = [html.split(MARKER % index)[1].split(MARKER % (index + 1))[0] for index in range(len(names))]
    used = ' '.join(t['title'] for t in data.get('templates', []))
    return parts, used


def direct_appearances(names: list[str]) -> dict:
    literals = ', '.join('"' + html_module.unescape(n).replace('\\', '\\\\').replace('"', '\\"') + '"' for n in names)
    data = call('prod', {'action': 'cargoquery', 'tables': 'Football_Games=fg, Games_Events=ge, Competitions=c',
                         'join_on': 'fg._pageID=ge._pageID, fg.Competition=c.OriginalName',
                         'where': f'ge.Team=1 AND ge.EventType IN (1,5) AND c.Official=1 AND ge.PlayerName IN ({literals})',
                         'fields': 'ge.PlayerName=p, COUNT(DISTINCT fg._pageName)=n', 'group_by': 'ge.PlayerName',
                         'limit': '500'}, post=True)
    return {html_module.unescape(r['title']['p']): int(r['title']['n']) for r in data['cargoquery']}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--batch', type=int, default=4)
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--print', action='store_true')
    options = parser.parse_args()
    candidate = candidate_of(page_text(DISPLAY))
    if options.print:
        print(candidate)
        return
    override = {'templatesandboxtitle': DISPLAY, 'templatesandboxtext': candidate,
                'templatesandboxcontentmodel': 'wikitext'}
    players = [p for p in json.loads(Path('.claude/tmp/players.json').read_text(encoding='utf-8')) if 'name' in p]
    names = [p['name'] for p in players][:options.limit or None]
    if options.selftest:
        names = ['ערן זהבי', 'אבי כהן']
    tally, started = {'ok': 0, 'FAIL': 0, 'allowed': 0}, time.time()
    for start in range(0, len(names), options.batch):
        batch = names[start:start + options.batch]
        old, _ = render(batch, None)
        new, used = render(list(reversed(batch)) if options.selftest else batch, override)
        if 'FootballPlayerStats' not in used:
            sys.exit('FAIL: the NEW render did not use Module:FootballPlayerStats - proves nothing')
        direct = direct_appearances(batch)
        for name, old_html, new_html in zip(batch, old, new):
            shown = APPEARANCES.search(new_html)
            expected = direct.get(html_module.unescape(name), 0)
            if '"' in html_module.unescape(name):
                verdict = 'allowed' if shown and int(shown.group(1)) == expected else 'FAIL'
                detail = f'quoted name: NEW shows {shown.group(1) if shown else None}, Cargo {expected}'
            elif old_html != new_html:
                verdict, detail = 'FAIL', 'the column differs'
            elif not shown or int(shown.group(1)) != expected:
                verdict, detail = 'FAIL', f'official appearances {shown.group(1) if shown else None}, Cargo {expected}'
            else:
                verdict, detail = 'ok', f'{expected} official appearances'
            tally[verdict] += 1
            if verdict != 'ok' or options.selftest:
                print(f'{verdict:7} {name}: {detail}', flush=True)
        print(f'... {start + len(batch)}/{len(names)} ({time.time() - started:.0f}s) {tally}', flush=True)
    if options.selftest:
        sys.exit(0 if tally['FAIL'] else 1)
    sys.exit(0 if tally['FAIL'] == 0 else 1)


if __name__ == '__main__':
    main()
