"""Publish the Lua modules from the repo to a wiki.

The repo is the source of truth: the wiki copy is deployed from here and never
edited on the wiki and copied back.

    uv run python infra/football_queries/deploy_modules.py --dry-run
    uv run python infra/football_queries/deploy_modules.py
    uv run python infra/football_queries/deploy_modules.py --status
    uv run python infra/football_queries/deploy_modules.py --delete

Local only, on purpose. It writes through `maintenance/edit.php` in the local
wiki container, so it needs no credentials and cannot reach production even by
accident. Production deployment is a separate, approved flow.
"""
import argparse
import subprocess
import sys
from pathlib import Path

COMPOSE_FILE = Path('infra/local-wiki/docker-compose.yml')
SERVICE = 'mediawiki'
USER = 'Admin'
SUMMARY = 'Deployed from infra/football_queries (repo is source of truth)'

# repo file -> wiki page. `Module` is the canonical name of namespace 828; the
# wiki displays it localised as יחידה.
MODULES = {
    'Module_FootballQueries.lua': 'Module:FootballQueries',
    'Module_FootballQueries_Fields.lua': 'Module:FootballQueries/Fields',
    'Module_FootballStatsBlocks.lua': 'Module:FootballStatsBlocks',
    'Module_FootballPlayerEvents.lua': 'Module:FootballPlayerEvents',
}
SOURCE_DIR = Path('infra/football_queries')

# Wikitext pages that go with the modules.
#
# The four /doc pages are written and ready in wiki_pages/ but are NOT deployed,
# because on this wiki the whole Module namespace is Scribunto content -
# `Module:X/doc` reports contentmodel "Scribunto" too, so wikitext cannot be
# saved there: edit.php answers "Lua error: unexpected symbol". The usual
# MediaWiki arrangement, where a /doc subpage is wikitext and carries the
# category, needs the doc-subpage exemption in site configuration, and there is
# no changeContentModel.php in this install to convert a page after the fact.
#
# Until that is decided, a module cannot carry a category at all here.
WIKI_PAGES = {
    'Category_Lua_modules.wiki': 'קטגוריה:יחידות לואה',
    'Category_Football_statistics_modules.wiki':
        'קטגוריה:יחידות לואה/סטטיסטיקת כדורגל',
}
BLOCKED_DOC_PAGES = {
    'Module_FootballQueries_doc.wiki': 'Module:FootballQueries/doc',
    'Module_FootballQueries_Fields_doc.wiki':
        'Module:FootballQueries/Fields/doc',
    'Module_FootballStatsBlocks_doc.wiki': 'Module:FootballStatsBlocks/doc',
    'Module_FootballPlayerEvents_doc.wiki':
        'Module:FootballPlayerEvents/doc',
}
WIKI_PAGES_DIR = SOURCE_DIR / 'wiki_pages'


def compose(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    command = ['docker', 'compose', '-f', str(COMPOSE_FILE), 'exec', '-T',
               SERVICE, *args]
    return subprocess.run(
        command, input=stdin, capture_output=True, text=True)


def read_page(title: str) -> str | None:
    """Current wiki text, or None when the page does not exist."""
    result = compose('php', 'maintenance/getText.php', title)
    if result.returncode != 0:
        return None
    return result.stdout


def write_page(title: str, text: str) -> None:
    result = compose('php', 'maintenance/edit.php', '--user', USER,
                     '--summary', SUMMARY, title, stdin=text)
    if result.returncode != 0:
        raise SystemExit(
            f'edit.php failed for {title}:\n{result.stderr.strip()[:500]}')


def delete_page(title: str) -> None:
    result = compose('php', 'maintenance/deleteBatch.php', '--u', USER,
                     '--r', 'Removing locally deployed module', stdin=title)
    if result.returncode != 0:
        raise SystemExit(
            f'deleteBatch.php failed for {title}:\n{result.stderr.strip()[:400]}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true',
                        help='report what would change, write nothing')
    parser.add_argument('--status', action='store_true',
                        help='compare wiki against repo, write nothing')
    parser.add_argument('--delete', action='store_true',
                        help='remove the deployed module pages')
    options = parser.parse_args()

    if compose('true').returncode != 0:
        raise SystemExit(
            'the local wiki container is not reachable - '
            f'docker compose -f {COMPOSE_FILE} up -d')

    everything = [(SOURCE_DIR / name, title)
                  for name, title in MODULES.items()]
    everything += [(WIKI_PAGES_DIR / name, title)
                   for name, title in WIKI_PAGES.items()]

    changed = 0
    for source, title in everything:
        wanted = source.read_text(encoding='utf-8')

        if options.delete:
            print(f'delete  {title}')
            if not options.dry_run:
                delete_page(title)
            continue

        current = read_page(title)
        if current is None:
            state = 'CREATE  '
        elif current.strip() == wanted.strip():
            state = 'ok      '
        else:
            state = 'UPDATE  '

        print(f'{state}{title}  <- {source}')
        if state != 'ok      ':
            changed += 1
            if not (options.dry_run or options.status):
                write_page(title, wanted)

    if options.status or options.dry_run:
        print(f'\n{changed} page(s) would change')
    else:
        print(f'\n{changed} page(s) written')


if __name__ == '__main__':
    main()
