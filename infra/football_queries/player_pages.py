"""The football player pages and the name their statistics column receives - batched.

    uv run python infra/football_queries/player_pages.py > players.json

Reads, 50 pages per request, every page using תבנית:פרופיל כדורגל/שחקן. Pages call
the wrapper `{{פרופיל כדורגל …}}`, which hands the column `שם להצגה` (its own
parameter, else PAGENAME) and `האם שוער` (from עמדה OR a Cargo check). The keeper
flag is NOT derived here: a comparison renders each player both ways, which
covers both display branches without re-implementing that check.
סוג פרופיל: איש צוות pages show no player column; שחקן / משולב / empty do.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import mwparserfromhell

sys.path.insert(0, str(Path('infra/season_pages')))
from season_api import call  # noqa: E402

TEMPLATE = 'תבנית:פרופיל כדורגל/שחקן'
NAMES = ('פרופיל כדורגל', 'תבנית:פרופיל כדורגל')


def player_titles() -> list[str]:
    titles, cont = [], {}
    while True:
        data = call('prod', dict({'action': 'query', 'list': 'embeddedin', 'eititle': TEMPLATE,
                                  'eilimit': 'max'}, **cont))
        titles += [row['title'] for row in data['query']['embeddedin']]
        if 'continue' not in data:
            return sorted(titles)
        cont = data['continue']


def column_parameters(titles: list[str]) -> list[dict]:
    """[{title, name, keeper}] for every page whose wikitext calls the template once."""
    players = []
    for start in range(0, len(titles), 50):
        data = call('prod', {'action': 'query', 'titles': '|'.join(titles[start:start + 50]),
                             'prop': 'revisions', 'rvprop': 'content', 'rvslots': 'main'}, post=True)
        for page in data['query']['pages']:
            text = page['revisions'][0]['slots']['main']['content'] if 'revisions' in page else ''
            calls = [node for node in mwparserfromhell.parse(text).filter_templates()
                     if node.name.strip().replace('_', ' ') in NAMES]
            if len(calls) != 1:
                players.append({'title': page['title'], 'error': f'{len(calls)} template calls'})
                continue
            value = lambda key: str(calls[0].get(key).value).strip() if calls[0].has(key) else ''  # noqa: E731
            players.append({'title': page['title'], 'name': value('שם להצגה') or page['title'],
                            'type': value('סוג פרופיל')})
    return players


if __name__ == '__main__':
    print(json.dumps(column_parameters(player_titles()), ensure_ascii=False, indent=1))
