"""The players portal's current-squad box: the template chain against
Module:FootballSeasonSquad's `portal` entry, on production.

    uv run python infra/football_queries/compare_portal_squad.py
    uv run python infra/football_queries/compare_portal_squad.py --selftest

READ-ONLY. Renders `{{פורטל שחקני כדורגל/הצגת סגל נוכחי |סגל נוכחי=…}}` and the
invoke with the same list (the module overridden by the repo file through
TemplateSandbox) and compares the HTML byte for byte. The one allowed
difference is the order of cards whose MainNumbers tie (MySQL left it
undefined; the module orders them by name) - checked as: same cards, same
positions, and the same order wherever the numbers differ. --selftest drops
the last player from the NEW list and must FAIL.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path('infra/football_queries')))
sys.path.insert(0, str(Path('infra/season_pages')))
from compare_stadium_leaderboards import page_text, parse  # noqa: E402

MODULE_FILE = Path('infra/football_queries/Module_FootballSeasonSquad.lua')
OLD = '{{פורטל שחקני כדורגל/הצגת סגל נוכחי |סגל נוכחי=%s }}'
NEW = '{{#invoke:FootballSeasonSquad|portal|סגל נוכחי=%s}}'
POSITION = re.compile(r'<div class="position-list-container">(.*?)(?=<div class="position-list-container">|\Z)', re.S)
CARD = re.compile(r'<div class="player-chip-container">.*?(?=<div class="player-chip-container">|</div>\s*</div>\s*\Z)', re.S)
NUMBER = re.compile(r'<div class="number">([^<]*)</div>')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--selftest', action='store_true')
    options = parser.parse_args()
    squad = page_text('תבנית:שחקני סגל נוכחי בכדורגל').strip()
    new_squad = ', '.join(squad.split(',')[:-1]) if options.selftest else squad
    old, old_wall = parse('ארגז חול', OLD % squad)
    new, new_wall = parse('ארגז חול', NEW % new_squad, {
        'templatesandboxtitle': 'Module:FootballSeasonSquad',
        'templatesandboxtext': MODULE_FILE.read_text(encoding='utf-8'),
        'templatesandboxcontentmodel': 'Scribunto'})
    for label, page in (('old', old), ('new', new)):
        if 'scribunto-error' in page or 'class="error"' in page:
            sys.exit(f'ERROR: the {label} render carries an error')
    if new.count('player-chip-container') == 0:
        sys.exit('FAIL: the new render has no cards - proves nothing')
    verdict = 'ok (byte-identical)'
    if old != new:
        old_positions, new_positions = POSITION.findall(old), POSITION.findall(new)
        if len(old_positions) != len(new_positions):
            verdict = f'FAIL: {len(old_positions)} position lists vs {len(new_positions)}'
        else:
            for index, (old_body, new_body) in enumerate(zip(old_positions, new_positions)):
                old_cards, new_cards = CARD.findall(old_body), CARD.findall(new_body)
                if sorted(old_cards) != sorted(new_cards):
                    verdict = f'FAIL: position {index + 1} holds different cards'
                    break
                numbers = [NUMBER.search(c).group(1) if NUMBER.search(c) else '' for c in new_cards]
                if [NUMBER.search(c).group(1) if NUMBER.search(c) else '' for c in old_cards] != numbers:
                    verdict = f'FAIL: position {index + 1} numbers in a different order'
                    break
            else:
                verdict = 'ok (the same cards; only ties in MainNumber reordered)'
    print(f'{"selftest: " if options.selftest else ""}{verdict}  ({old_wall:.2f}s -> {new_wall:.2f}s, '
          f'{new.count("player-chip-container")} cards)')
    sys.exit((0 if verdict.startswith('FAIL') else 1) if options.selftest else (0 if verdict.startswith('ok') else 1))


if __name__ == '__main__':
    main()
