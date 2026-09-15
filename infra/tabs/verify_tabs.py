"""Verify one converted tab strip on the LOCAL wiki.

    uv run python infra/tabs/verify_tabs.py 'תבנית:כדורסל/סטטיסטיקה/שיאני נקודות'

Writes one sandbox page on the local wiki and nothing else. Never touches
production.

Byte comparison is not available for this work - the markup changes by design -
so this runs the checks that replace it, cheapest first
(`.claude/shtml_free_tabs_design.md` §6):

1. the converted wikitext survives the sanitizer, asserted by the PRESENCE of
   the tab elements rather than only the absence of `<input>`. Checking only
   the absence is what let an earlier design ship a markup contract in which
   `<label>` came back as escaped text;
2. the panels' text is unchanged, compared panel by panel, failing on a count
   mismatch rather than zipping the shorter list;
3. no `<input>` and no `<shtml>` remain in the output.

What it cannot prove, and what still needs a browser: that clicking a tab
switches panels, that arrow keys move the right way in RTL, and that the strip
still looks right. Those are Playwright's job.
"""
import argparse
import html
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, 'infra/tabs')

from convert_strip import (  # noqa: E402
    Refused, convert, fallback_context, local_text,
)

API = 'http://localhost:8080/api.php'
COMPOSE = 'infra/local-wiki/docker-compose.yml'
SANDBOX_SUFFIX = '/ארגז חול טאבים'

TAG = re.compile(r'<[^>]+>')
PANEL_TEXT = re.compile(
    r'<(?P<tag>div|article|section)[^>]*class="[^"]*tabber__panel[^"]*"[^>]*>'
    r'(?P<body>.*?)(?=<\1[^>]*class="[^"]*tabber__panel|\Z)', re.DOTALL)
OLD_PANEL = re.compile(
    r'<div id="tab(?P<index>\d+)-content">(?P<body>.*?)'
    r'(?=<div id="tab\d+-content"|\Z)', re.DOTALL)


def write_local(title: str, text: str) -> None:
    result = subprocess.run(
        ['docker', 'compose', '-f', COMPOSE, 'exec', '-T', 'mediawiki',
         'php', 'maintenance/edit.php', '--user', 'Admin', '--summary',
         'tab conversion sandbox', title],
        input=text, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'could not write {title}: {result.stderr[:300]}')


def render(wikitext: str) -> str:
    data = urllib.parse.urlencode({
        'action': 'parse', 'text': wikitext, 'title': 'ארגז חול',
        'contentmodel': 'wikitext', 'prop': 'text',
        'disablelimitreport': 1, 'format': 'json', 'formatversion': 2,
    }).encode('utf-8')
    with urllib.request.urlopen(
            urllib.request.Request(API, data=data), timeout=180) as response:
        body = json.loads(response.read().decode('utf-8'))
    if 'error' in body:
        raise SystemExit(body['error'])
    return body['parse']['text']


def words_of(fragment: str) -> list[str]:
    """Visible text, as a list of words - whitespace and markup ignored."""
    text = html.unescape(TAG.sub(' ', fragment))
    return text.split()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('title', help='template to convert and check')
    parser.add_argument('--parameters', default='',
                        help='extra template parameters, e.g. "|עונה=2021/22"')
    options = parser.parse_args()

    original = local_text(options.title)
    try:
        converted = convert(original, fallback_context(options.title))
    except Refused as refusal:
        raise SystemExit(f'REFUSED: {refusal}')

    sandbox = options.title + SANDBOX_SUFFIX
    write_local(sandbox, converted)

    call = '{{%s%s}}'
    old_html = render(call % (options.title.removeprefix('תבנית:'),
                              options.parameters))
    new_html = render(call % (sandbox.removeprefix('תבנית:'),
                              options.parameters))

    failures = 0

    print('1. the converted markup survives the sanitizer')
    present = [needle for needle in ('tabber__tab', 'tabber__panel',
                                     'tabber__header')
               if needle in new_html]
    if len(present) < 2:
        print(f'   FAIL  expected tabber elements, found {present or "none"}')
        print(f'         {new_html[:400]}')
        failures += 1
    else:
        print(f'   ok    found {", ".join(present)}')

    print('2. no raw-HTML machinery remains')
    for needle in ('<input', '<shtml', '&lt;label', '&lt;input'):
        if needle in new_html:
            print(f'   FAIL  {needle} is still in the output')
            failures += 1
    else:
        print('   ok    no <input>, no <shtml>, nothing escaped into text')

    print('3. the panels say the same thing')
    old_panels = [match.group('body') for match in OLD_PANEL.finditer(old_html)]
    new_panels = [match.group('body') for match in PANEL_TEXT.finditer(new_html)]
    if not old_panels:
        print('   FAIL  found no panels in the ORIGINAL rendering - the '
              'comparison would be vacuous')
        failures += 1
    elif len(old_panels) != len(new_panels):
        print(f'   FAIL  {len(old_panels)} panel(s) before, '
              f'{len(new_panels)} after')
        failures += 1
    else:
        for index, (before, after) in enumerate(
                zip(old_panels, new_panels), start=1):
            if words_of(before) != words_of(after):
                only_before = set(words_of(before)) - set(words_of(after))
                only_after = set(words_of(after)) - set(words_of(before))
                print(f'   FAIL  panel {index} differs')
                print(f'         only before: {sorted(only_before)[:12]}')
                print(f'         only after:  {sorted(only_after)[:12]}')
                failures += 1
            else:
                print(f'   ok    panel {index}: '
                      f'{len(words_of(before))} words identical')

    print(f'\n{failures} failure(s). sandbox: {sandbox}')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
