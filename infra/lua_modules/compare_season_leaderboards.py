"""Old season leaderboard boxes against the one-invoke tabbers, locally.

    uv run python infra/lua_modules/compare_season_leaderboards.py
    uv run python infra/lua_modules/compare_season_leaderboards.py --selftest
    uv run python infra/lua_modules/compare_season_leaderboards.py --prod

--prod is the gate before switching production's template: a READ-ONLY sweep
(action=parse&text=, nothing saved, one parse at a time) of every season page
production has, OLD from production's own template chain against NEW from the
published module. The local run covers only the fixture's four seasons.

Renders ONLY the שיאנים section - not the whole season page - through the
REAL wrapper templates and the real invoke, for every season in the local
data, and compares each box and tab: title, heading (with its distinct-player
count), the ranked rows, and whether there is an "עוד" link. Shares its
comparison rules with compare_referee_leaderboards.py (same allowed
differences, §4.5 of the referee spec; see .claude/lua_modules.md,
"Leaderboards"):

  1. tied players may be ordered differently, and at the top-10 boundary a
     different member of the tie may be shown - the counts must still match;
  4. a tab with exactly ten players has a link today and none now.

Rendering only the section, not the whole page, is deliberate: a season page
carries other <shtml> strips above (seasonal numbers) and below (the games
list) this section, which would break the referee harness's box/tab
extraction if reused unmodified here (found by adversarial review before this
ran once). The OLD and NEW section
texts are extracted from the LIVE template by convert_season_section.section_texts,
never hand-copied, so they cannot drift from production.

Refuses to pass over nothing: a run in which no season shows a single row, or
any rendering carries an error, fails. Production has five seasons with no
games at all (1921, 1923, 1924, 1937/38, 1943); the local fixture's own
seasons all have games, so the zero-row path is added explicitly (an empty
season and a season that does not exist) rather than assumed to be covered.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path('infra/lua_modules')))
sys.path.insert(0, str(Path('infra/tabs')))
from convert_season_section import read_local, section_texts, TEMPLATE  # noqa: E402
from compare_referee_leaderboards import (  # noqa: E402
    API, compare_tab, TITLE, HEADER, ROW, MORE,
)
from verify_tabs import ERROR_MARKERS, render  # noqa: E402

VARDEFINE = '{{#vardefine:עונה להצגה|%s}}'

# The season section's box wrapper carries no id (id="שיאנים" is on the
# PARENT container the real page wraps this section in), unlike the referee
# boxes.
BOX = re.compile(r'<div class="records-list-tabs-container">(.*?)'
                 r'(?=<div class="records-list-tabs-container"|\Z)', re.S)
OLD_PANEL = re.compile(r'<div id="tab\d-content">(.*?)(?=<div id="tab\d-content">|\Z)', re.S)
NEW_PANEL = re.compile(r'<article[^>]*class="tabber__panel"[^>]*>(.*?)</article>', re.S)


def boxes_of_season(page: str, panel: re.Pattern) -> list[dict]:
    """Same field extraction as compare_referee_leaderboards.boxes_of, but
    matched against the id-less season wrapper (BOX above), not the
    referee/module BOX regex, which requires id="שיאנים"."""
    boxes = []
    for box in BOX.findall(page):
        tabs = []
        for body in panel.findall(box):
            header = HEADER.search(body)
            rows = [(name.strip(), count.strip()) for name, count in ROW.findall(body)]
            link = MORE.search(body)
            tabs.append({'header': header.group(1).strip() if header else None,
                         'rows': rows, 'more': bool(link),
                         'href': link.group(1) if link else None})
        title = TITLE.search(box)
        boxes.append({'title': title.group(1) if title else None, 'tabs': tabs})
    return boxes


def local_seasons() -> list[str]:
    params = {'action': 'cargoquery', 'format': 'json', 'limit': '500',
              'tables': 'Football_Games', 'fields': 'Season',
              'group_by': 'Season', 'order_by': 'Season'}
    with urllib.request.urlopen(f'{API}?{urllib.parse.urlencode(params)}') as response:
        rows = json.loads(response.read())['cargoquery']
    seasons = sorted({row['title']['Season'] for row in rows if row['title'].get('Season')})
    if not seasons:
        raise SystemExit('no seasons in the local data - nothing to compare')
    # Production has five seasons with no games at all; the local fixture's
    # own seasons do not include one, so the zero-row path is added here
    # explicitly rather than assumed to be exercised.
    return seasons + ['1921', 'עונה שלא קיימת - ארגז חול']


PROD_API = 'https://www.maccabipedia.co.il/api.php'
PROD_UA = {'User-Agent': 'MaccabipediaBot/season-parity (infra/lua_modules)'}
# Pause between production renders: this is a read-only sweep of ~100
# seasons, two parses each, on a shared host - sequential, never concurrent.
PROD_PAUSE_SECONDS = 1.0


def prod_api(params: dict, post: bool = False) -> dict:
    params = dict(params, format='json', formatversion='2')
    body = urllib.parse.urlencode(params).encode('utf-8')
    request = (urllib.request.Request(PROD_API, data=body, headers=PROD_UA) if post else
               urllib.request.Request(f'{PROD_API}?{body.decode()}', headers=PROD_UA))
    with urllib.request.urlopen(request, timeout=180) as response:
        data = json.loads(response.read().decode('utf-8'))
    if 'error' in data:
        raise SystemExit(f'production API error: {data["error"]}')
    return data


def prod_render(wikitext: str) -> str:
    """The same uncached action=parse&text= render as verify_tabs.render, on
    production. Saves nothing; only the Lua modules must already be there."""
    time.sleep(PROD_PAUSE_SECONDS)
    data = prod_api({'action': 'parse', 'text': wikitext, 'title': 'ארגז חול',
                     'contentmodel': 'wikitext', 'prop': 'text',
                     'disablelimitreport': 1}, post=True)
    return data['parse']['text']


def prod_template() -> str:
    data = prod_api({'action': 'query', 'titles': TEMPLATE, 'prop': 'revisions',
                     'rvprop': 'content', 'rvslots': 'main'})
    return data['query']['pages'][0]['revisions'][0]['slots']['main']['content']


def prod_seasons() -> list[str]:
    """Every season whose page uses the season template on production -
    the pages Gate B switches, empty seasons included."""
    seasons, params = [], {'action': 'query', 'list': 'embeddedin',
                           'eititle': TEMPLATE, 'einamespace': '0', 'eilimit': 'max'}
    while True:
        data = prod_api(params)
        for page in data['query']['embeddedin']:
            if page['title'].startswith('עונת '):
                seasons.append(page['title'][len('עונת '):])
        if 'continue' not in data:
            break
        params.update(data['continue'])
    if not seasons:
        raise SystemExit('production lists no season pages - nothing to compare')
    return sorted(seasons)


def compare(season: str, old_text: str, new_text: str,
            new_season: str | None = None,
            renderer=render) -> tuple[str, str, int]:
    old_page = renderer(VARDEFINE % season + old_text)
    new_page = renderer(VARDEFINE % (new_season or season) + new_text)
    for label, page in (('old', old_page), ('new', new_page)):
        errors = [marker for marker in ERROR_MARKERS if marker in page]
        if errors:
            return 'ERROR', f'{label} rendering carries {errors}', 0
    if 'tabber__panel' not in new_page or 'slim-tabs' in new_page:
        return 'FAIL', 'the new section is not the tabber version', 0
    if re.search(r'</article>\s*<p class="mw-empty-elt">', new_page) or \
            re.search(r'עוד</a></p>', new_page):
        return 'FAIL', 'the parser wrapped the "עוד" link in a paragraph', 0
    old_boxes = boxes_of_season(old_page, OLD_PANEL)
    new_boxes = boxes_of_season(new_page, NEW_PANEL)
    if len(old_boxes) != 4 or len(new_boxes) != 4:
        return 'FAIL', f'{len(old_boxes)} old boxes, {len(new_boxes)} new', 0
    rows = 0
    for old_box, new_box in zip(old_boxes, new_boxes):
        if old_box['title'] != new_box['title']:
            return 'FAIL', f'title {old_box["title"]!r} vs {new_box["title"]!r}', rows
        if len(old_box['tabs']) != 4 or len(new_box['tabs']) != 4:
            return 'FAIL', f'{old_box["title"]}: tab counts', rows
        for old_tab, new_tab in zip(old_box['tabs'], new_box['tabs']):
            rows += len(old_tab['rows'])
            problem = compare_tab(old_tab, new_tab)
            if problem:
                return 'FAIL', f'{old_box["title"]} / {old_tab["header"]}: {problem}', rows
    return 'ok', f'{rows} rows', rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selftest', action='store_true',
                        help='old text of one season vs new text of another must FAIL')
    parser.add_argument('--prod', action='store_true',
                        help='READ-ONLY sweep of every production season page '
                             '(after the modules are published, before the '
                             'template is switched)')
    options = parser.parse_args()

    if options.prod:
        old_text, new_text = section_texts(prod_template())
        seasons, renderer = prod_seasons(), prod_render
    else:
        old_text, new_text = section_texts(read_local(TEMPLATE))
        seasons, renderer = local_seasons(), render

    if options.selftest:
        # Two seasons with games, not the empty ones that sort first on prod.
        pair = [s for s in seasons if s.startswith('20')][:2] or seasons[:2]
        verdict, detail, _ = compare(pair[0], old_text, new_text,
                                     new_season=pair[1], renderer=renderer)
        print(f'selftest: {pair[0]} old vs {pair[1]} new -> {verdict}: {detail}')
        sys.exit(0 if verdict == 'FAIL' else 1)

    tally, total_rows = {}, 0
    for season in seasons:
        verdict, detail, rows = compare(season, old_text, new_text, renderer=renderer)
        tally[verdict] = tally.get(verdict, 0) + 1
        total_rows += rows
        if verdict != 'ok':
            print(f'{verdict:5} {season}: {detail}')
    print(f'\n{len(seasons)} seasons, {total_rows} rows compared: '
          + '  '.join(f'{k} {v}' for k, v in sorted(tally.items())))
    if total_rows == 0:
        raise SystemExit('not a single row was compared - proves nothing')
    sys.exit(0 if set(tally) == {'ok'} else 1)


if __name__ == '__main__':
    main()
