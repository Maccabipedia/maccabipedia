"""Convert and verify EVERY radio tab strip on the local wiki.

    uv run python infra/tabs/batch_verify.py
    uv run python infra/tabs/batch_verify.py --min-words 15

One sandbox page per strip on the local wiki; nothing else is written, and
production is never touched.

A strip whose panels hold almost no text is reported WEAK rather than ok: on
the local wiki many statistics panels render "no records" for both the old and
the new markup, and two identical empty panels prove nothing - the same trap
the football edge cases call HOLLOW.
"""
import argparse
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
from verify_tabs import (  # noqa: E402
    OLD_PANEL, PANEL_TEXT, SANDBOX_SUFFIX, error_panels, render, words_of,
    write_local,
)

API = 'http://localhost:8080/api.php'


def local_strips() -> list[str]:
    """Every local page carrying a radio tab strip."""
    titles, parameters = [], {
        'action': 'query', 'generator': 'allpages', 'gapnamespace': 10,
        'gaplimit': 50, 'prop': 'revisions', 'rvprop': 'content',
        'rvslots': 'main', 'format': 'json', 'formatversion': '2',
    }
    while True:
        url = API + '?' + urllib.parse.urlencode(parameters)
        with urllib.request.urlopen(url, timeout=120) as response:
            body = json.loads(response.read().decode('utf-8'))
        for page in body.get('query', {}).get('pages', []):
            revisions = page.get('revisions')
            if not revisions:
                continue
            text = revisions[0].get('slots', {}).get('main', {}).get(
                'content', '')
            if '<shtml' in text and re.search(r'name="[^"]*tab-control', text) \
                    and SANDBOX_SUFFIX not in page['title']:
                titles.append(page['title'])
        if 'continue' not in body:
            return sorted(titles)
        parameters.update(body['continue'])


def check(title: str, min_words: int) -> tuple[str, str]:
    """('ok' | 'WEAK' | 'FAIL' | 'REFUSED', detail)."""
    original = local_text(title)
    try:
        converted = convert(original, fallback_context(title))
    except Refused as refusal:
        return 'REFUSED', str(refusal)

    sandbox = title + SANDBOX_SUFFIX
    write_local(sandbox, converted)

    try:
        old_html = render('{{%s}}' % title.removeprefix('תבנית:'))
        # The SAME template again. Some of these queries have ties and no
        # deterministic tiebreak, so their rows come back in a different order
        # each time - three volleyball strips reported "panel 1 text differs"
        # when compared against a target that was moving on its own.
        again_html = render('{{%s}}' % title.removeprefix('תבנית:'))
        new_html = render('{{%s}}' % sandbox.removeprefix('תבנית:'))
    except SystemExit as error:
        return 'FAIL', f'render failed: {error}'

    first = [words_of(m.group('body')) for m in OLD_PANEL.finditer(old_html)]
    second = [words_of(m.group('body')) for m in OLD_PANEL.finditer(again_html)]
    if first != second:
        return 'UNSTABLE', ('the original renders differently each time - '
                            'nothing can be concluded about the conversion')

    if 'tabber__panel' not in new_html:
        return 'FAIL', 'no tabber panels in the output'
    for leak in ('<input', '<shtml', '&lt;label'):
        if leak in new_html:
            return 'FAIL', f'{leak} survived into the output'

    old_panels = [match.group('body') for match in OLD_PANEL.finditer(old_html)]
    new_panels = [match.group('body') for match in PANEL_TEXT.finditer(new_html)]
    if not old_panels:
        return 'FAIL', 'no panels found in the ORIGINAL rendering'
    if len(old_panels) != len(new_panels):
        return 'FAIL', f'{len(old_panels)} panels before, {len(new_panels)} after'

    total = 0
    for index, (before, after) in enumerate(zip(old_panels, new_panels), 1):
        words = words_of(before)
        total += len(words)
        if words != words_of(after):
            # Two matching renders do not prove a template is stable: the
            # volleyball strips with tied rows agreed twice by chance on CI and
            # then the conversion's render came out in another order - a FAIL
            # on a pull request that never touched them. Before blaming the
            # conversion, render the original a few more times.
            for _ in range(4):
                again = [words_of(m.group('body'))
                         for m in OLD_PANEL.finditer(render(
                             '{{%s}}' % title.removeprefix('תבנית:')))]
                if again != first:
                    return 'UNSTABLE', (
                        f'panel {index} differed, and the original itself '
                        'renders differently on repeat - nothing can be '
                        'concluded about the conversion')
            return 'FAIL', f'panel {index} text differs'

    # An error renders identically on both sides, so agreement means nothing.
    # Reported before the word count, because the count is ANTI-correlated
    # with it: the wordiest pages in this corpus are the ones whose panels are
    # full of Cargo errors.
    if error_panels(old_html):
        return 'HOLLOW', (f'{len(old_panels)} panels agree, but the original '
                          'rendering contains an error - nothing is proven')

    if total < min_words:
        return 'WEAK', f'only {total} word(s) across {len(old_panels)} panels'
    return 'ok', f'{len(old_panels)} panels, {total} words identical'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--min-words', type=int, default=20,
                        help='below this, the comparison is reported WEAK')
    parser.add_argument('--limit', type=int)
    options = parser.parse_args()

    strips = local_strips()
    if options.limit:
        strips = strips[:options.limit]
    print(f'{len(strips)} strip(s) on the local wiki\n')

    tally = {}
    for title in strips:
        verdict, detail = check(title, options.min_words)
        tally[verdict] = tally.get(verdict, 0) + 1
        print(f'{verdict:8} {title}\n         {detail}', flush=True)

    print('\n' + '  '.join(f'{verdict}={count}'
                           for verdict, count in sorted(tally.items())))
    sys.exit(1 if tally.get('FAIL') else 0)


if __name__ == '__main__':
    main()
