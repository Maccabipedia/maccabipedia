"""The baseline the rewrite has to reproduce, and a comparison that can fail.

    uv run python infra/football_queries/capture_golden_numbers.py capture
    uv run python infra/football_queries/capture_golden_numbers.py verify
    uv run python infra/football_queries/capture_golden_numbers.py selftest

This file answers one question: did migrating a page change any published
number? `capture` records what production renders now, per labelled statistic.
`verify` renders the same blocks on production again and compares label by
label, so it is run immediately AFTER a page is migrated.

It deliberately does not compare production with the local wiki: production
holds every season and the local wiki holds 2021/22-2024/25, so those numbers
differ for legitimate reasons and a comparison between them would be noise.
Equivalence on shared data is what compare_rendered_blocks.py proves, byte for
byte, and old-season behaviour is what verify_edge_cases.py proves by running
the module's own SQL against production.

The previous version of this file could not detect a wrong number: it rendered
production against production, so nothing under test was ever exercised, and
its selftest was one-sided - a harness that always reported a difference would
have passed it. This one:

  * anchors every number to its label instead of its position, because a block
    repeats each label once per tab and two statistics often hold the same
    value;
  * keeps thousands separators, since a formatting difference is a difference;
  * refuses a baseline with no statistics in it, which any candidate matches;
  * has a two-sided selftest that writes nothing: one player must match their
    own baseline, and must NOT match another player's.
"""
import json
import re
import sys
import time
from pathlib import Path

FIXTURE = Path('infra/football_queries/fixtures/golden_numbers.json')
# Each render of the four-tab block issues 32 Cargo queries, so six players is
# roughly 200 against production. Spaced out on purpose; this runs on migration
# day, not in a loop.
#
# For the record: a run that produced "number_format expects a number" errors
# looked exactly like production buckling under that load, and it was a
# variable-shadowing bug in verify() rendering a statistic label as a player
# name. Throttling is politeness, not a fix for that.
SECONDS_BETWEEN_PRODUCTION_RENDERS = 5.0

TABS_TEMPLATE = 'תבנית:סטטיסטיקה/תצוגה/שחקנים/סיכום אירועים'

# Players present in the local seed, so both sides can render the same block.
# Nine entity types are covered by verify_edge_cases.py; this file covers the
# one display family that has been migrated.
PLAYERS = [
    'ערן זהבי', 'גבי קניקובסקי', 'דור פרץ', "דור תורג'מן",
    'אופיר דוידזאדה', 'דן ביטון',
]

# Every statistic in the block carries a label in the rendered HTML, and the
# label is what identifies it - not its position.
LABELLED = re.compile(
    r'<div class="Top10RowName">(.{1,40}?)</div>'
    r'\s*<span class="Top10RowStat">(.{0,120}?)</span>')


def render_production(wikitext: str) -> str:
    from maccabipediabot.common.wiki_login import get_site

    site = get_site()
    parsed = site.simple_request(
        action='parse', text=wikitext, title='עונת 2021/22',
        contentmodel='wikitext', prop='text', formatversion=2,
        disablelimitreport=1, format='json').submit()
    return parsed['parse']['text']


def statistics(html: str) -> dict:
    """Label -> value, with the label made unique when it repeats."""
    found = {}
    for label, value in LABELLED.findall(html):
        label = re.sub(r'<[^>]+>', '', label).strip()
        value = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', value)).strip()
        key, index = label, 2
        while key in found:
            # A block renders its labels once per tab, so the same label
            # legitimately appears four times. Number them in document order.
            key = f'{label}#{index}'
            index += 1
        found[key] = value
    return found


def call(template: str, player: str) -> str:
    return '{{' + template + '|שחקן=' + player + '}}'


def provenance() -> dict:
    """What the baseline was captured from.

    Without this, a `capture` run after migrating freezes the NEW numbers as
    the baseline and `verify` then agrees with itself forever. The recorded
    revision of the template is what makes that visible.
    """
    import pywikibot as pw

    from maccabipediabot.common.wiki_login import get_site

    site = get_site()
    page = pw.Page(site, TABS_TEMPLATE)
    revision = page.latest_revision
    return {
        'captured': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'template': TABS_TEMPLATE,
        'revision': revision.revid,
        'revision_timestamp': str(revision.timestamp),
        'note': 'if the template revision has changed since, this baseline '
                'may already describe migrated output - re-read before '
                'trusting a pass',
    }


def capture() -> None:
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    fixture = {'__provenance__': provenance()}

    for index, player in enumerate(PLAYERS):
        if index:
            time.sleep(SECONDS_BETWEEN_PRODUCTION_RENDERS)
        html = render_production(call(TABS_TEMPLATE, player))
        values = statistics(html)
        if not values:
            raise SystemExit(
                f'no labelled statistics found for {player} - the baseline '
                'would be empty, which any candidate would match')
        fixture[player] = values
        print(f'{player}: {len(values)} labelled statistics')

    FIXTURE.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=1, sort_keys=True),
        encoding='utf-8')
    print(f'wrote {FIXTURE}')


def verify(players: list | None = None, render_as: str = '') -> int:
    """Render the block on production again and compare with the baseline.

    Run this right after migrating a page. Before migration it compares the
    templates with themselves and passes trivially - which is why `selftest`
    exists: a comparison that cannot fail proves nothing either way.
    """
    fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
    captured = fixture.pop('__provenance__', None)
    if captured:
        print(f'  baseline captured {captured["captured"]} from '
              f'{captured["template"]} revision {captured["revision"]}')
    if players:
        fixture = {name: values for name, values in fixture.items()
                   if name in players}

    failures = 0
    for index, (player, expected) in enumerate(sorted(fixture.items())):
        if index:
            time.sleep(SECONDS_BETWEEN_PRODUCTION_RENDERS)
        # `render_as` is only for the selftest, which renders one player
        # against another's baseline. The loop below must not reuse this name:
        # shadowing it made every player after the first render a statistic
        # label as if it were a player name, and the empty result showed up as
        # a template error that I briefly blamed on production.
        actual = statistics(render_production(call(TABS_TEMPLATE,
                                                   render_as or player)))

        differences = []
        for statistic, value in expected.items():
            if actual.get(statistic) != value:
                differences.append(
                    f'{statistic}: baseline {value!r} -> now '
                    f'{actual.get(statistic, "MISSING")!r}')
        missing = set(actual) - set(expected)
        if missing:
            differences.append(f'labels the baseline never had: {sorted(missing)}')

        if differences:
            failures += 1
            print(f'DIFF  {player}')
            for line in differences[:6]:
                print(f'        {line}')
        else:
            print(f'OK    {player}  ({len(expected)} statistics)')

    print(f'\n{len(fixture) - failures}/{len(fixture)} players match the baseline')
    return failures


def selftest() -> int:
    """Pass when the numbers match, fail when they do not. Both are required.

    No page is written anywhere: the failing half renders one player's block
    and compares it with ANOTHER player's baseline, which must differ. A
    harness that reports success there is comparing nothing, which is exactly
    what the previous version of this file did.
    """
    fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
    fixture.pop('__provenance__', None)
    names = sorted(fixture)
    if len(names) < 2:
        raise SystemExit('the selftest needs at least two players captured')

    print('--- part 1: a player must match their own baseline ---')
    same = verify(players=[names[0]])
    print(f'  {same} difference(s); expected 0')

    print(f'\n--- part 2: {names[0]} rendered against {names[1]}\'s baseline '
          'must differ ---')
    crossed = verify(players=[names[1]], render_as=names[0])
    print(f'  {crossed} difference(s); expected at least 1')

    if same == 0 and crossed > 0:
        print('\nSELFTEST PASSED: the baseline comparison can pass and fail')
        return 0
    print(f'\nSELFTEST FAILED: same={same} crossed={crossed} - this '
          'comparison is not evidence')
    return 1


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else 'capture'
    if command == 'capture':
        capture()
    elif command == 'verify':
        sys.exit(1 if verify() else 0)
    elif command == 'selftest':
        sys.exit(selftest())
    else:
        raise SystemExit(f'unknown command: {command}')


if __name__ == '__main__':
    main()
