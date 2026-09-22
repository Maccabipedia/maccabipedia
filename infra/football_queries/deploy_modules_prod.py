"""Publish the Lua modules to PRODUCTION. Separate flow, separate approval.

    uv run python infra/football_queries/deploy_modules_prod.py --check
    uv run python infra/football_queries/deploy_modules_prod.py --publish
    uv run python infra/football_queries/deploy_modules_prod.py --publish --with-docs
    uv run python infra/football_queries/deploy_modules_prod.py --probe

The local deployer (deploy_modules.py) writes through maintenance/edit.php in
the container and cannot reach production even by accident. This one can, so
it is deliberately separate, writes nothing without --publish, and does only
one thing: put the module pages on the wiki.

Publishing a module changes what readers see on EVERY page that already
invokes it - since #193 the day pages and since #195 the referee pages. Each
publish marks those pages for re-rendering and their next view runs the new
code, so a publish is a live change to them, not an inert upload. Before
publishing, capture an uncached render of a few of those pages' converted
sections (action=parse with text=, not page=, which can return the cache);
after publishing, render them again and diff. --check lists who calls each
module so the size of that is visible; --probe renders the entry points,
leaderboards included, from raw text on production without saving anything.

Order matters in both directions. Forward, the blocks data goes first: the
old renderer ignores fields it does not know. Rolling back is the reverse
case - republish ONLY Module:FootballStatsBlock from the previous commit. Its
old code ignores the newer blocks data, whereas publishing the old blocks
data first leaves the NEW renderer reading fields that are gone, and every
page using it errors until the second write lands. One exception: once the
season pages' מספרים עונתיים template reads the rowless season-results /
season-cards blocks, a renderer older than them fails on those blocks - so
revert those two templates first (.claude/season_pages.md), then the module.

Two production facts this has to survive:

  * PHP notices on production can make a save's API response non-JSON even
    when the save succeeded, so every page is read back and compared byte for
    byte instead of trusting the response.
  * A module page carries its category from its /תיעוד subpage, inside
    <includeonly>, so the module page must be purged after the doc is written
    or the category stays empty and looks broken.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, 'packages/maccabipediabot/src')

SOURCE_DIR = Path('infra/football_queries')
WIKI_PAGES_DIR = SOURCE_DIR / 'wiki_pages'

# The Lua itself. `Module` is the canonical name of namespace 828; the wiki
# shows it localised as יחידה.
MODULES = {
    'Module_FootballQueries.lua': 'Module:FootballQueries',
    'Module_FootballQueries_Fields.lua': 'Module:FootballQueries/Fields',
    'Module_FootballStatsBlocks.lua': 'Module:FootballStatsBlocks',
    'Module_FootballStatsBlock.lua': 'Module:FootballStatsBlock',
    'Module_FootballSeasonSquad.lua': 'Module:FootballSeasonSquad',
    'Module_FootballSeasonTable.lua': 'Module:FootballSeasonTable',
    'Module_FootballPlayerStats.lua': 'Module:FootballPlayerStats',
}

# The documentation that goes with them. Wikitext, inert, and the standard
# MediaWiki arrangement: Scribunto shows the /תיעוד subpage at the top of the
# module page, and because it is wikitext it can carry the category the module
# page itself cannot.
DOCS = {
    'Category_Lua_modules.wiki': 'קטגוריה:יחידות לואה',
    'Category_Football_statistics_modules.wiki':
        'קטגוריה:יחידות לואה/סטטיסטיקת כדורגל',
    'Category_Module_doc_pages.wiki': 'קטגוריה:דפי תיעוד של יחידות',
    'Module_FootballQueries_tiud.wiki': 'Module:FootballQueries/תיעוד',
    'Module_FootballQueries_Fields_tiud.wiki':
        'Module:FootballQueries/Fields/תיעוד',
    'Module_FootballStatsBlocks_tiud.wiki': 'Module:FootballStatsBlocks/תיעוד',
    'Module_FootballStatsBlock_tiud.wiki': 'Module:FootballStatsBlock/תיעוד',
    'Module_FootballSeasonSquad_tiud.wiki': 'Module:FootballSeasonSquad/תיעוד',
}

SUMMARY = ('עדכון יחידות סטטיסטיקת הכדורגל '
           '(deployed from infra/football_queries)')


def site():
    import pywikibot

    # Fail fast. A POST the wiki's WAF refuses comes back as a non-JSON body,
    # which pywikibot treats as a transient error and retries every two
    # minutes, forever - so a blocked edit is indistinguishable from a hang.
    # One short retry covers a real blip; anything worse should be reported,
    # not waited out.
    pywikibot.config.max_retries = 1
    pywikibot.config.retry_wait = 5
    pywikibot.config.retry_max = 15

    from maccabipediabot.common.wiki_login import get_site

    return get_site()


def targets(with_docs: bool = True) -> list[tuple[Path, str]]:
    """The pages to publish. The Lua always; the documentation only when asked.

    They are separable because they are separate decisions: the modules are
    the thing that was reviewed and tested, while the documentation pages also
    create three new categories, which is a visible change to the wiki's
    category tree even though nothing links to them.
    """
    pages = [(SOURCE_DIR / name, title) for name, title in MODULES.items()]
    if with_docs:
        pages += [(WIKI_PAGES_DIR / name, title) for name, title in DOCS.items()]
    return pages


def current_text(connection, title: str) -> str | None:
    import pywikibot as pw

    page = pw.Page(connection, title)
    return page.text if page.exists() else None


def publish(connection, title: str, wanted: str) -> str:
    """Write one page as multipart/form-data, and prove it landed.

    NOT page.save(). pywikibot sends an edit as an urlencoded body, and the
    wiki's web application firewall refuses these particular bodies that way -
    302 to the host's abuse page - then pywikibot reads the refusal as a
    transient non-JSON response and retries every two minutes forever, so a
    blocked edit is indistinguishable from a hung wiki.

    Measured against production, writing nothing: Module:FootballQueries and
    Module:FootballStatsBlock are refused urlencoded and accepted as multipart,
    byte for byte the same text. So the edit goes through pywikibot's own
    session - same login, same cookies - with `files=`, which makes requests
    encode it as multipart.
    """
    import pywikibot as pw
    from pywikibot.comms import http as pw_http

    token = connection.tokens['csrf']
    fields = {
        'action': (None, 'edit'),
        'title': (None, title),
        'text': (None, wanted),
        'summary': (None, SUMMARY),
        'token': (None, token),
        'format': (None, 'json'),
        'bot': (None, '1'),
        # Never silently overwrite: this flow only ever creates these pages or
        # updates ones it already owns, so a concurrent edit should fail here
        # rather than be clobbered.
        'nocreate' if page_exists(connection, title) else 'createonly':
            (None, '1'),
    }

    response = pw_http.session.post(
        connection.base_url('/api.php'), files=fields,
        headers={'Accept': 'application/json'}, timeout=120)

    if 'application/json' not in response.headers.get('Content-Type', ''):
        return (f'REFUSED ({response.status_code}, '
                f'{response.headers.get("Content-Type", "?")})')

    answer = response.json()
    if 'error' in answer:
        return f'ERROR {answer["error"].get("code")}'

    # Read back rather than trust the response: production emits PHP notices
    # that can make a successful save's body unusable.
    time.sleep(1)
    fresh = pw.Page(connection, title)
    if not fresh.exists():
        return 'MISSING AFTER SAVE'
    fresh.get(force=True)
    if fresh.text.strip() != wanted.strip():
        return 'MISMATCH'
    return 'ok'


def page_exists(connection, title: str) -> bool:
    import pywikibot as pw

    return pw.Page(connection, title).exists()


def callers(connection, title: str) -> list[str]:
    pages, parameters = [], {
        'action': 'query', 'list': 'embeddedin', 'eititle': title,
        'eilimit': 500, 'format': 'json',
    }
    while True:
        response = connection.simple_request(**parameters).submit()
        pages += [row['title'] for row in response['query']['embeddedin']]
        if 'continue' not in response:
            return pages
        parameters.update(response['continue'])


def purge(connection, titles: list[str]) -> None:
    connection.simple_request(
        action='purge', forcelinkupdate=1, titles='|'.join(titles),
        format='json').submit()


def check(connection) -> int:
    """What is on the wiki now, and whether anything calls it."""
    problems = 0
    for source, title in targets(with_docs=True):
        wanted = source.read_text(encoding='utf-8')
        current = current_text(connection, title)
        if current is None:
            state = 'ABSENT  '
        elif current.strip() == wanted.strip():
            state = 'ok      '
        else:
            state = 'DIFFERS '
            problems += 1
        print(f'{state}{title}')

    # Callers are expected (day and referee pages invoke these), so they are
    # reported, not counted as problems: the number is how many live pages a
    # publish re-renders.
    print('\nwho calls these modules (every one re-renders on publish):')
    for title in MODULES.values():
        using = callers(connection, title)
        print(f'  {title}: {len(using)} page(s)'
              + (f' -> {using[:5]}' if using else ''))
    return problems


def probe(connection) -> int:
    """Run the modules on production WITHOUT any page using them.

    action=parse with text= renders wikitext that is never saved, so this
    exercises Scribunto and Cargo on production while leaving every page
    exactly as it was.
    """
    cases = [
        ('a single count through the query layer',
         '{{#invoke:FootballQueries|count|שחקן=ערן זהבי|מספר אירוע=3'
         '|קטגוריית מפעל=ליגה}}'),
        # Not `block`: that entry point reads the PARENT frame on purpose, and
        # a preview parse of raw text has no parent, so it would fail for a
        # reason that says nothing about production. aggregateProbe takes its
        # arguments directly and exercises the same merge primitive - several
        # numbers from one query.
        ('several cells from one query (the merge primitive)',
         '{{#invoke:FootballQueries|aggregateProbe|cells=goals:3,assists:4'
         '|שחקן=ערן זהבי|קטגוריית מפעל=ליגה}}'),
        ('an unsupported filter must raise, not return a total',
         '{{#invoke:FootballQueries|count|בית או חוץ=בית}}'),
        # The entry point the referee pages run live, and the one the season
        # pages will: four boxes each, from one query.
        ('referee-assistant leaderboards: four boxes',
         '{{#invoke:FootballStatsBlock|leaderboards|בלוק=referee-assistant'
         '|שופט=דודו ביטון}}'),
        ('season leaderboards: four boxes',
         '{{#invoke:FootballStatsBlock|leaderboards|בלוק=season|עונה=2023/24}}'),
    ]

    failures = 0
    for description, wikitext in cases:
        parsed = connection.simple_request(
            action='parse', text=wikitext, title='ארגז חול',
            contentmodel='wikitext', prop='text', formatversion=2,
            disablelimitreport=1, format='json').submit()
        html = parsed['parse']['text']
        error = 'scribunto-error' in html
        expected_error = 'must raise' in description

        boxes = html.count('records-list-tabs-container')
        if error != expected_error:
            failures += 1
            print(f'FAIL  {description}\n      {html[:300]}')
        elif 'four boxes' in description and boxes != 4:
            failures += 1
            print(f'FAIL  {description}: {boxes} boxes rendered')
        else:
            body = html.replace('\n', ' ')[:160]
            print(f'OK    {description}\n      {body}')
    return failures


def refuse_uncommitted_sources(with_docs: bool) -> None:
    """Publish only what is committed. The module files on disk are not always
    what git holds: tests/mutate.py rewrites them in place, and two runs at
    once can leave a mutation behind - one did, 2026-09-19, silently deleting
    the &quot; entry from FootballQueries' entity table."""
    import subprocess

    paths = [str(source) for source, _ in targets(with_docs=with_docs)]
    dirty = subprocess.run(['git', 'status', '--porcelain', '--', *paths],
                           capture_output=True, text=True, check=True).stdout
    if dirty.strip():
        raise SystemExit('refusing to publish: these files differ from the last '
                         f'commit -\n{dirty}commit or restore them first')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='compare the wiki with the repo and list callers')
    parser.add_argument('--publish', action='store_true',
                        help='write the module pages (the Lua only)')
    parser.add_argument('--with-docs', action='store_true',
                        help='also write the /תיעוד pages and their '
                             'categories')
    parser.add_argument('--probe', action='store_true',
                        help='run the modules via a preview parse, saving '
                             'nothing')
    options = parser.parse_args()

    if not (options.check or options.publish or options.probe):
        parser.error('nothing to do - pass --check, --publish or --probe')

    if options.publish:
        refuse_uncommitted_sources(options.with_docs)

    connection = site()
    print(f'connected to {connection}\n')

    if options.publish:
        for source, title in targets(with_docs=options.with_docs):
            wanted = source.read_text(encoding='utf-8')
            current = current_text(connection, title)
            if current is not None and current.strip() == wanted.strip():
                print(f'ok      {title} (unchanged)')
                continue
            action = 'CREATE' if current is None else 'UPDATE'
            print(f'{action}  {title}')
            result = publish(connection, title, wanted)
            print(f'    {result}')
            if result != 'ok':
                raise SystemExit(
                    f'{title} did not land as written - stopping before '
                    'anything else is published')

        # The category lives inside <includeonly> on the doc page, so the
        # module page only picks it up when it is re-parsed.
        purge(connection, list(MODULES.values()))
        print('\npurged the module pages so their category applies')

    exit_code = 0
    if options.check:
        print()
        exit_code += check(connection)
    if options.probe:
        print()
        exit_code += probe(connection)
    sys.exit(min(exit_code, 100))


if __name__ == '__main__':
    main()
