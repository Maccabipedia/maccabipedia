"""Build a football-profile template candidate from the LIVE text plus one named change.

    uv run python infra/lua_modules/make_profile_candidates.py FIX

READ-ONLY on the wiki. Reads the live template, applies exactly one textual change,
refuses if the text it expects is not there once, and writes
infra/lua_modules/wiki_templates/football_profile/<FIX>.wiki plus <FIX>.sha1 (the live
revision it was derived from - the gate and switch_template_prod.py --expect-sha1 use it).

Fixes (each touches one template):
  gallery-player  תבנית:פרופיל כדורגל/שחקן     the photo gallery was rendered once inside
  gallery-staff   תבנית:פרופיל כדורגל/איש צוות  #תנאי to test for emptiness and again to show
                  it (4 renders on a player+coach page). Now it is rendered once into
                  the variable גלריית תמונות - by whichever of the two templates runs first
                  - and the test and the display both read the variable. The test call's
                  output (אין תוצאות= empty) is what the display call printed whenever the
                  category has files, which is the only case the display branch runs.
  shirt-once      תבנית:פרופיל כדורגל          the shirt-number query ran twice with the same
                  argument (once to test, once to fill the array); now once, into a variable.
  trophies-param  …/הרכבת רשימת זכיות/שחקן      accepts the player's seasons as |עונות= so the
                  caller can run that query once instead of once per list (6x); with no
                  |עונות= it queries as before, so this step alone changes no output.
  trophies-once   תבנית:פרופיל כדורגל          runs the seasons query once into עונות כשחקן and
                  passes it to the 6 player trophy lists (needs trophies-param live first).
                  The staff lists are kept: see trophies_once for why skipping them is not
                  output-neutral.
  coach-ratios    …/הצגת עמודת סטטיסטיקה/איש צוות/הצגה  a BUG FIX, not output-neutral: the
                  9 per-game ratios divided by משחקים unguarded, so a tab where the coach has
                  0 games printed 9 number_format errors. Each ratio span now sits inside
                  #ifexpr משחקים > 0, as in the player column. Gate with --removed-errors.
  keeper-cells    …/הצגת עמודת סטטיסטיקה/שחקן/הצגה  the four goalkeeper cells were
                  #vardefine'd for every player, so Module:FootballPlayerStats ran its keeper
                  query (~80 ms) on outfield pages too. They are read only inside the
                  template's own #תנאי האם שוער branch, so they are now defined only there.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path('infra/season_pages')))
from season_api import call  # noqa: E402

OUT = Path('infra/lua_modules/wiki_templates/football_profile')

GALLERY_OLD = ('{{#תנאי: {{הצגת גלריה לפי קטגוריה |שם קטגוריה={{#var: שם להצגה}}/תמונות |אין תוצאות=}}\n'
               '|{{פרק\n'
               '|כותרת=תמונות של {{#var: שם להצגה}}\n'
               '|טקסט=<div class="gallery-container">\n'
               '{{הצגת גלריה לפי קטגוריה |שם קטגוריה={{#var: שם להצגה}}/תמונות }}\n')
GALLERY_NEW = ('{{#varexists: גלריית תמונות ||{{#vardefine: גלריית תמונות |{{הצגת גלריה לפי קטגוריה '
               '|שם קטגוריה={{#var: שם להצגה}}/תמונות |אין תוצאות=}} }} }}<!--\n'
               '-->{{#תנאי: {{#var: גלריית תמונות}}\n'
               '|{{פרק\n'
               '|כותרת=תמונות של {{#var: שם להצגה}}\n'
               '|טקסט=<div class="gallery-container">\n'
               '{{#var: גלריית תמונות}}\n')

SHIRT_QUERY = '{{פרופיל כדורגל/שליפת מספרי חולצה |שם={{#var: שם להצגה}} }}'
SHIRT_OLD = ('-->{{#תנאי: {{{מספר חולצה|}}}%s |{{#arraydefine: מספר חולצה |{{{מספר חולצה|}}}, %s }} '
             '{{#arrayunique: מספר חולצה}} }}<!--' % (SHIRT_QUERY, SHIRT_QUERY))
SHIRT_NEW = ('-->{{#vardefine: מספרי חולצה משליפה |%s }}<!--\n'
             '-->{{#תנאי: {{{מספר חולצה|}}}{{#var: מספרי חולצה משליפה}} |{{#arraydefine: מספר חולצה '
             '|{{{מספר חולצה|}}}, {{#var: מספרי חולצה משליפה}} }} {{#arrayunique: מספר חולצה}} }}<!--'
             % SHIRT_QUERY)

SEASONS_QUERY = '{{סטטיסטיקה/שליפות/מתקדמות/עונות שבהן שיחק שחקן |שחקן=%s |שלוף לספירה=כן}}'
TROPHY_SEASONS_OLD = '-->{{#arraydefine:עונות |%s }}<!--' % (SEASONS_QUERY % '{{{שם|}}}')
TROPHY_SEASONS_NEW = ('-->{{#arraydefine:עונות |{{#if: {{{עונות|}}} |{{{עונות|}}} |%s }} }}<!--'
                      % (SEASONS_QUERY % '{{{שם|}}}'))

KEEPER_CELLS = ''.join(
    '-->{{#vardefine: %s |{{#invoke:FootballPlayerStats|value|שחקן={{#var: שם להצגה}}'
    '|קטגוריית מפעל={{{קטגוריית מפעל|}}}|תא=%s}} }}<!--\n' % pair
    for pair in (('ספיגות', 'conceded'), ('שער נקי', 'cleanSheets'),
                 ('ספיגות פנדלים', 'penaltiesConceded'), ('הדיפות פנדלים', 'penaltySaves')))

FIXES = {
    'gallery-player': ('תבנית:פרופיל כדורגל/שחקן', GALLERY_OLD, GALLERY_NEW),
    'gallery-staff': ('תבנית:פרופיל כדורגל/איש צוות', GALLERY_OLD, GALLERY_NEW),
    'shirt-once': ('תבנית:פרופיל כדורגל', SHIRT_OLD, SHIRT_NEW),
    'trophies-param': ('תבנית:פרופיל כדורגל/הרכבת רשימת זכיות/שחקן', TROPHY_SEASONS_OLD, TROPHY_SEASONS_NEW),
    'keeper-cells': ('תבנית:פרופיל כדורגל/הצגת עמודת סטטיסטיקה/שחקן/הצגה', KEEPER_CELLS,
                     '-->{{#תנאי: {{{האם שוער|}}} |<!--\n' + KEEPER_CELLS + '-->}}<!--\n'),
}


PLAYER_TROPHY_CALL = '{{פרופיל כדורגל/הרכבת רשימת זכיות/שחקן |'
FIRST_PLAYER_TROPHIES = '-->{{#arraydefine: זכיות באליפות כשחקן |'


def trophies_once(text: str) -> str:
    """Seasons query once for the 6 player trophy lists.

    The 6 staff lists stay on every profile: the trophy templates all write the page-wide
    array עונות, and הצגת פרטי שחקן counts it when its own seasons list is empty - so the
    last staff list decides that number today (its "ללא תוצאות" text counts as 1 season;
    אורי עזו, 2026-09-23). Skipping them changed his count from 1 to 2.
    """
    if text.count(PLAYER_TROPHY_CALL) != 6 or text.count(FIRST_PLAYER_TROPHIES) != 1:
        raise SystemExit('trophies-once: expected 6 player trophy calls and one first list - refusing')
    text = text.replace(PLAYER_TROPHY_CALL, PLAYER_TROPHY_CALL + 'עונות={{#var: עונות כשחקן}} |')
    text = text.replace(FIRST_PLAYER_TROPHIES, '-->{{#vardefine: עונות כשחקן |%s }}<!--\n%s'
                        % (SEASONS_QUERY % '{{#var: שם להצגה}}', FIRST_PLAYER_TROPHIES))
    return text


COACH_RATIO = re.compile(r'(<span class="small">\{\{#number_format: .*?</span>)(</span>)')


def coach_ratios(text: str) -> str:
    """Show the coach column's per-game ratios only when the tab has games, as the player column does."""
    guarded, count = COACH_RATIO.subn(r'{{#ifexpr: {{#var: משחקים}} > 0 |\1}}\2', text)
    if count != 9:
        raise SystemExit(f'coach-ratios: expected 9 ratio spans, found {count} - refusing')
    return guarded


def live(title: str) -> tuple[str, str]:
    data = call('prod', {'action': 'query', 'titles': title, 'prop': 'revisions',
                         'rvprop': 'content|sha1', 'rvslots': 'main'})
    revision = data['query']['pages'][0]['revisions'][0]
    return revision['slots']['main']['content'], revision['sha1']


def main() -> None:
    fix = sys.argv[1]
    if fix == 'trophies-once':
        title = 'תבנית:פרופיל כדורגל'
        text, sha1 = live(title)
        candidate = trophies_once(text)
    elif fix == 'coach-ratios':
        title = 'תבנית:פרופיל כדורגל/הצגת עמודת סטטיסטיקה/איש צוות/הצגה'
        text, sha1 = live(title)
        candidate = coach_ratios(text)
    else:
        title, old, new = FIXES[fix]
        text, sha1 = live(title)
        if text.count(old) != 1:
            raise SystemExit(f'{title}: expected the old text exactly once, found {text.count(old)} - refusing')
        candidate = text.replace(old, new)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f'{fix}.wiki').write_text(candidate, encoding='utf-8')
    (OUT / f'{fix}.sha1').write_text(f'{title}\n{sha1}\n', encoding='utf-8')
    print(f'{fix}: {title} from sha1 {sha1} -> {OUT / (fix + ".wiki")}')


if __name__ == '__main__':
    main()
