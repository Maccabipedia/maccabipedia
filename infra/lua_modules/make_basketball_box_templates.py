"""The eight basketball box templates, rewritten as one invoke each, into
`wiki_templates/basketball_boxes/` - the wikitext that is LIVE on production, tracked
here because the repo is the source of truth for what the wiki runs and because the gate
needs it to run at all from a fresh checkout.

Regenerating needs the live bodies in `.claude/tmp/bb_boxes/` (`fetch_bb_boxes.py`); the
generated files are committed, so a checkout can gate without fetching anything.


Each one loses its signed <shtml> radio strip, its four query-template calls and the
`tab1-content`..`tab4-content` divs; `leaderboardBox` emits the whole box as a tabber.
The limit is taken from the LIVE template, because two boxes (איבודים, עבירות) hardcode
5 and ignore the page's `כמות שחקנים` - a difference this conversion must not quietly fix.

No str.format here: every brace in the body is wikitext, and doubling them to escape the
formatter is how the first version emitted `{#invoke` and swallowed `{{{כמות שחקנים|5}}}`.
"""
import re
import sys
from pathlib import Path

BOXES = Path('.claude/tmp/bb_boxes')
OUT = Path('infra/lua_modules/wiki_templates/basketball_boxes')
# The limit as the template writes it: a parameter with its default, or a bare number.
LIMIT = re.compile(r'\|כמות=(\{\{\{[^{}]*\}\}\}|\d+)')
BODY = ('<includeonly>{{#invoke:BasketballStatsBlock|leaderboardBox|בלוק=leaderboards'
        '|תיבה=WORD|כמות=LIMIT|עונה={{{עונה|}}}|שחקנים={{{שחקנים|}}}'
        '|יריבות={{{יריבות|}}}|מגרשים={{{מגרשים|}}}}}</includeonly>')


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for path in sorted(BOXES.glob('*.wiki')):
        live = path.read_text(encoding='utf-8')
        limits = set(LIMIT.findall(live))
        if len(limits) != 1:
            print(f'{path.stem}: {len(limits)} different limits {limits} - not converted')
            continue
        body = BODY.replace('WORD', path.stem).replace('LIMIT', limits.pop())
        (OUT / path.name).write_text(body, encoding='utf-8')
        print(f'{path.stem}: {len(live)} -> {len(body)} bytes')
    return 0


if __name__ == '__main__':
    sys.exit(main())
