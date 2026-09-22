"""Publish the Lua modules from the repo to a wiki.

The repo is the source of truth: the wiki copy is deployed from here and never
edited on the wiki and copied back.

    uv run python infra/lua_modules/deploy_modules.py --dry-run
    uv run python infra/lua_modules/deploy_modules.py
    uv run python infra/lua_modules/deploy_modules.py --status
    uv run python infra/lua_modules/deploy_modules.py --delete

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
SUMMARY = 'Deployed from infra/lua_modules (repo is source of truth)'

# repo file -> wiki page. `Module` is the canonical name of namespace 828; the
# wiki displays it localised as יחידה.
MODULES = {
    # Shared first: the football pages below are shims that require these, so
    # a fresh wiki (and a rollback) needs them in place before the shims land.
    'Module_SportQueries.lua': 'Module:SportQueries',
    'Module_StatsBlock.lua': 'Module:StatsBlock',
    # Data before the shim that reads it (the shim's error prefix is Fields.name).
    'Module_FootballQueries_Fields.lua': 'Module:FootballQueries/Fields',
    'Module_FootballQueries.lua': 'Module:FootballQueries',
    'Module_FootballStatsBlocks.lua': 'Module:FootballStatsBlocks',
    'Module_FootballStatsBlock.lua': 'Module:FootballStatsBlock',
    'Module_FootballSeasonSquad.lua': 'Module:FootballSeasonSquad',
    'Module_FootballSeasonTable.lua': 'Module:FootballSeasonTable',
    'Module_FootballPlayerStats.lua': 'Module:FootballPlayerStats',
    'Module_FootballDate.lua': 'Module:FootballDate',
    'Module_SeasonTrophies.lua': 'Module:SeasonTrophies',
    # Basketball: schema, then its query shim, then block data, then its renderer shim.
    'Module_BasketballQueries_Fields.lua': 'Module:BasketballQueries/Fields',
    'Module_BasketballQueries.lua': 'Module:BasketballQueries',
    'Module_BasketballStatsBlocks.lua': 'Module:BasketballStatsBlocks',
    'Module_BasketballStatsBlock.lua': 'Module:BasketballStatsBlock',
}
SOURCE_DIR = Path('infra/lua_modules')

# Wikitext pages that go with the modules.
#
# The documentation subpage is the standard MediaWiki arrangement: Scribunto
# shows it at the top of the module page, and because it is wikitext it can
# carry the category that the module page itself cannot.
#
# Its name is LOCALISED. The `scribunto-doc-page-name` message on this wiki is
# `Module:$1/תיעוד`, so `/doc` is not a doc page here - it stays Scribunto
# content and wikitext cannot be saved on it at all, which is what "Lua error:
# unexpected symbol" means when saving one. `/תיעוד` reports contentmodel
# wikitext, as it should.
WIKI_PAGES = {
    'Category_Lua_modules.wiki': 'קטגוריה:יחידות לואה',
    'Category_Football_statistics_modules.wiki':
        'קטגוריה:יחידות לואה/סטטיסטיקת כדורגל',
    # The /תיעוד pages file themselves here, so it must exist or they sit in a
    # red-linked category.
    'Category_Module_doc_pages.wiki': 'קטגוריה:דפי תיעוד של יחידות',
    'Module_FootballQueries_tiud.wiki': 'Module:FootballQueries/תיעוד',
    'Module_FootballQueries_Fields_tiud.wiki':
        'Module:FootballQueries/Fields/תיעוד',
    'Module_FootballStatsBlocks_tiud.wiki':
        'Module:FootballStatsBlocks/תיעוד',
    'Module_FootballStatsBlock_tiud.wiki':
        'Module:FootballStatsBlock/תיעוד',
    'Module_FootballSeasonSquad_tiud.wiki':
        'Module:FootballSeasonSquad/תיעוד',
}
WIKI_PAGES_DIR = SOURCE_DIR / 'wiki_pages'

# Site-wide pages the tab widgets depend on, deployed LOCALLY only so the local
# wiki and CI run the repo's copy rather than whatever the DB snapshot holds.
# Common.js carries the jump-to-anchor exclusion for tabber tabs; without it
# the snapshot's copy scrolls the page on every tab click and the browser test
# for that fails. On production these need interface-admin rights the bot
# does not have, so they are pasted by hand. Never deleted by --delete.
SITE_PAGES = {
    'MediaWiki_Common.js': 'MediaWiki:Common.js',
}
SITE_PAGES_DIR = Path('infra/site_pages')


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


def purge_modules() -> None:
    """Re-parse the module pages so the category from their doc applies."""
    import json
    import urllib.parse
    import urllib.request

    titles = '|'.join(MODULES.values())
    data = urllib.parse.urlencode({
        'action': 'purge', 'forcelinkupdate': 1, 'titles': titles,
        'format': 'json',
    }).encode('utf-8')
    try:
        with urllib.request.urlopen(
                urllib.request.Request('http://localhost:8080/api.php',
                                       data=data), timeout=60) as response:
            purged = json.loads(response.read().decode('utf-8'))
        count = len(purged.get('purge', []))
        print(f'purged {count} module page(s) so their category applies')
    except Exception as error:  # noqa: BLE001 - report, do not fail the deploy
        print(f'could not purge ({error}) - the category may look empty until '
              'the module pages are re-parsed')


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
    if not options.delete:
        everything += [(SITE_PAGES_DIR / name, title)
                       for name, title in SITE_PAGES.items()]

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
        return

    print(f'\n{changed} page(s) written')

    if changed:
        # A documentation page carries the module's category inside
        # <includeonly>, so the category only lands on the module page when
        # that page is re-parsed. Editing the doc does not re-parse it, so
        # without this the category stays empty and looks broken.
        purge_modules()


if __name__ == '__main__':
    main()
