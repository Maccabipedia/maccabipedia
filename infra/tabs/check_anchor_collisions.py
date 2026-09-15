"""Two tabs on one page must not share an anchor.

    uv run python infra/tabs/check_anchor_collisions.py
    uv run python infra/tabs/check_anchor_collisions.py --selftest
    uv run python infra/tabs/check_anchor_collisions.py --page 'שם הדף'

Local wiki, read-only except for --selftest, which writes one sandbox page.

Why this exists. This wiki writes a panel's id into the address bar on every
tab click, so if two panels on a page shared an id, a link would open whichever
came first and show the wrong numbers with no sign anything was wrong.

Measured: that cannot happen as configured. A panel's id is the tab label plus
the INDEX OF ITS BOX on the page, so two boxes with identical labels still get
`אלף-0` and `אלף-1`. The first version of this file asserted the opposite and
its own selftest disproved it.

It is kept as an invariant rather than deleted, because the id scheme is not
ours: it would change if $wgTabberNeueUseLegacyTabIds were ever switched on
(today it throws for any box with two or more tabs) or if the pinned extension
changed how ids are built. This is the check that would notice.
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from collections import Counter

API = 'http://localhost:8080/api.php'
COMPOSE = 'infra/local-wiki/docker-compose.yml'

PANEL_ID = re.compile(r'<article[^>]+id="(?P<id>tabber-tabpanel-[^"]*)"')
SELFTEST_PAGE = 'ארגז חול/טאבים/התנגשות עוגנים'


def get(parameters: dict) -> dict:
    url = API + '?' + urllib.parse.urlencode(parameters)
    try:
        with urllib.request.urlopen(url, timeout=180) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as failure:
        # A page whose render throws server-side comes back as HTTP 500, not
        # as an API error object. One template here does, through DPL and a
        # gallery that reaches for production images. Treated as "no output"
        # so the sweep continues and reports the skip.
        if failure.code == 500:
            return {'error': {'code': 'http500', 'info': url[-80:]}}
        raise


def rendered(page: str) -> str:
    body = get({'action': 'parse', 'page': page, 'prop': 'text',
                'formatversion': '2', 'format': 'json'})
    if 'error' in body:
        return ''
    return body['parse']['text']


def rendered_text(wikitext: str, strict: bool = True) -> str:
    body = get({'action': 'parse', 'text': wikitext, 'title': 'ארגז חול',
                'contentmodel': 'wikitext', 'prop': 'text',
                'formatversion': '2', 'format': 'json'})
    if 'error' in body:
        if strict:
            raise SystemExit(body['error'])
        # A page can fail to render for reasons that have nothing to do with
        # tabs - one template here pulls images through ForeignAPIRepo, which
        # throws on the local wiki when it cannot reach production. Skipping
        # it beats aborting the sweep, as long as the skip is reported.
        return ''
    return body['parse']['text']


def pages_with_tabber() -> list[str]:
    """Articles whose wikitext contains a tabber, by reading the sources.

    Not `generator=search`: this wiki has no CirrusSearch, so `insource:` is
    unavailable and a plain search for "tabber" matches nothing. The first
    version of this function used it and reported "0 pages to check", which
    looks exactly like a clean result.
    """
    found = []
    for namespace in ('0', '10'):
        parameters = {
            'action': 'query', 'generator': 'allpages',
            'gapnamespace': namespace, 'gaplimit': '50',
            'prop': 'revisions', 'rvprop': 'content', 'rvslots': 'main',
            'format': 'json', 'formatversion': '2',
        }
        while True:
            body = get(parameters)
            for page in body.get('query', {}).get('pages', []):
                revisions = page.get('revisions')
                if not revisions:
                    continue
                text = revisions[0].get('slots', {}).get('main', {}).get(
                    'content', '')
                if '<tabber' in text:
                    found.append(page['title'])
            if 'continue' not in body:
                break
            parameters.update(body['continue'])
    return sorted(found)


def collisions_in(html: str) -> dict:
    ids = PANEL_ID.findall(html)
    repeated = {value: count for value, count
                in Counter(ids).items() if count > 1}
    return repeated


def write_local(title: str, text: str) -> None:
    result = subprocess.run(
        ['docker', 'compose', '-f', COMPOSE, 'exec', '-T', 'mediawiki',
         'php', 'maintenance/edit.php', '--user', 'Admin', '--summary',
         'anchor collision selftest', title],
        input=text, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'could not write {title}: {result.stderr[:300]}')


def selftest() -> int:
    """A checker that has never reported anything is not evidence.

    The detector is exercised on synthetic HTML, because a real page cannot
    produce a duplicate while the positional suffix exists - see the second
    part, which records that rather than assuming it.
    """
    duplicated = (
        '<article id="tabber-tabpanel-אלף-0" class="tabber__panel">x</article>'
        '<article id="tabber-tabpanel-בית-0" class="tabber__panel">y</article>'
        '<article id="tabber-tabpanel-אלף-0" class="tabber__panel">z</article>')
    found = collisions_in(duplicated)
    if not found:
        print('SELFTEST FAILED: a duplicated id was not reported')
        return 1
    print(f'  synthetic duplicate: reported {list(found)}')

    unique = duplicated.replace('אלף-0" class="tabber__panel">z',
                                'גימל-0" class="tabber__panel">z')
    if collisions_in(unique):
        print('SELFTEST FAILED: reported a collision among unique ids')
        return 1
    print('  synthetic unique ids: nothing reported')

    # And what the wiki actually does with the worst case: two boxes whose
    # labels are identical. They do NOT collide, because the suffix numbers
    # the box. This is the reason the check is an invariant rather than a
    # rename guard - and it is measured here so the claim cannot rot.
    worst = rendered_text(
        '<tabber>|-|אלף=one|-|בית=two</tabber>\n\n'
        '<tabber>|-|אלף=three|-|בית=four</tabber>')
    ids = PANEL_ID.findall(worst)
    if collisions_in(worst):
        print(f'SELFTEST FAILED: the wiki produced duplicate ids: {ids}')
        return 1
    print(f'  two boxes, identical labels, on the wiki: {ids} - distinct')

    print('\nSELFTEST PASSED: the detector fires on a duplicate and not '
          'otherwise, and the suffix keeps real pages free of them')
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--page', help='check one page')
    options = parser.parse_args()

    if options.selftest:
        sys.exit(selftest())

    targets = [options.page] if options.page else pages_with_tabber()
    print(f'checking {len(targets)} page(s) for shared tab anchors')

    failures = skipped = 0
    for title in targets:
        # A TEMPLATE renders as nothing on its own - its body is inside
        # <includeonly> - so it is transcluded instead. Checking only
        # namespace 0 meant no conversion target was ever checked, since every
        # one of them is a template.
        html = (rendered_text('{{%s}}' % title.removeprefix('תבנית:'),
                              strict=False)
                if title.startswith('תבנית:') else rendered(title))
        if not html:
            print(f'SKIP       {title}  (did not render)')
            skipped += 1
            continue
        if 'tabber-tabpanel-' not in html:
            continue
        found = collisions_in(html)
        panels = len(PANEL_ID.findall(html))
        if found:
            failures += 1
            print(f'COLLISION  {title}')
            for value, count in sorted(found.items()):
                print(f'           {urllib.parse.unquote(value)} x{count}')
        else:
            print(f'ok         {title}  ({panels} panels)')

    print(f'\n{failures} page(s) with shared anchors, {skipped} skipped')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
