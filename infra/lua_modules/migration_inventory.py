"""Who actually calls the templates this layer replaces, on production.

Read-only. Nothing is written to any wiki.

    uv run python infra/lua_modules/migration_inventory.py

Ranked by live callers, because that is what a migration is worth. An earlier
ranking used internal fan-out and put a template with ZERO callers first - the
one the renderer was built for.

Two sources, because neither is enough on its own:

  * `embeddedin` lists pages that transclude a template. It MISSES a
    transclusion that sits inside <includeonly> of another template, which is
    how most of this wiki's display templates are wired.
  * so the source of every page in namespace 10 is read as well, and searched
    for the template name.

The output is a table: template, pages that transclude it, templates whose
source names it, and how many queries a caller pays for it today.
"""
import re
import sys
from collections import defaultdict

sys.path.insert(0, 'packages/maccabipediabot/src')

from maccabipediabot.common.wiki_login import get_site  # noqa: E402

# The templates this layer can replace today, with what one call costs in
# Cargo queries. The cost is what makes a caller count worth acting on.
TARGETS = {
    'תבנית:סטטיסטיקה/שליפות/מתקדמות/כמות נתוני משחק': 1,
    'תבנית:סטטיסטיקה/שליפות/מתקדמות/כמות אירועי שחקן': 1,
    'תבנית:סטטיסטיקה/תצוגה/ימים/סיכום תוצאות לפי מפעל': 6,
    'תבנית:סטטיסטיקה/תצוגה/ימים/סיכום תוצאות': 28,
    'תבנית:סטטיסטיקה/תצוגה/שחקנים/סיכום אירועים לפי מפעל': 8,
    'תבנית:סטטיסטיקה/תצוגה/שחקנים/סיכום אירועים': 32,
}


def transcluding_pages(site, title: str) -> list[str]:
    """Pages that transclude the template, per the link tables."""
    pages = []
    parameters = {
        'action': 'query', 'list': 'embeddedin', 'eititle': title,
        'eilimit': 500, 'format': 'json',
    }
    while True:
        response = site.simple_request(**parameters).submit()
        pages += [row['title'] for row in response['query']['embeddedin']]
        if 'continue' not in response:
            return pages
        parameters.update(response['continue'])


def template_sources(site) -> dict[str, str]:
    """The wikitext of every template on the wiki, by title.

    embeddedin misses a call inside <includeonly>, and that is the normal
    shape here, so the sources are searched directly.
    """
    sources = {}
    parameters = {
        'action': 'query', 'generator': 'allpages', 'gapnamespace': 10,
        'gaplimit': 50, 'prop': 'revisions', 'rvprop': 'content',
        'rvslots': 'main', 'format': 'json',
    }
    while True:
        response = site.simple_request(**parameters).submit()
        for page in response.get('query', {}).get('pages', {}).values():
            revisions = page.get('revisions')
            if not revisions:
                continue
            sources[page['title']] = (
                revisions[0].get('slots', {}).get('main', {}).get('*', ''))
        if 'continue' not in response:
            return sources
        parameters.update(response['continue'])


def names_of(title: str) -> list[str]:
    """How a template can be written in a transclusion."""
    bare = title.removeprefix('תבנית:')
    return [f'{{{{{bare}', f'{{{{תבנית:{bare}', f'{{{{Template:{bare}']


def main() -> None:
    site = get_site()

    print('reading every template source in namespace 10 ...')
    sources = template_sources(site)
    print(f'  {len(sources)} templates\n')

    naming = defaultdict(list)
    for title, text in sources.items():
        for target in TARGETS:
            if any(name in text for name in names_of(target)):
                naming[target].append(title)

    rows = []
    for target, cost in TARGETS.items():
        pages = transcluding_pages(site, target)
        content = [page for page in pages if not page.startswith('תבנית:')]
        rows.append((target, cost, len(pages), len(content),
                     sorted(naming.get(target, []))))

    rows.sort(key=lambda row: row[3] * row[1], reverse=True)

    print(f'{"template":58} {"cost":>5} {"callers":>8} {"content":>8} '
          f'{"queries":>8}')
    for target, cost, callers, content, named_by in rows:
        short = target.removeprefix('תבנית:סטטיסטיקה/')
        print(f'{short:58} {cost:5} {callers:8} {content:8} '
              f'{content * cost:8}')

    print('\ntemplates whose SOURCE names each target '
          '(what embeddedin alone would miss):')
    for target, _, _, _, named_by in rows:
        short = target.removeprefix('תבנית:סטטיסטיקה/')
        print(f'  {short}:')
        for title in named_by:
            print(f'      {title}')
        if not named_by:
            print('      (none)')


if __name__ == '__main__':
    main()
