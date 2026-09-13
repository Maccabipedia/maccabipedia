"""Capture what the current football statistics templates render, as a fixture.

The fixture is the baseline the Lua rewrite must reproduce. It renders a
template call on production and stores the numbers it produced, so a later
run can diff against it.

Usage:
    uv run python infra/football_queries/capture_golden_numbers.py capture
    uv run python infra/football_queries/capture_golden_numbers.py verify
    uv run python infra/football_queries/capture_golden_numbers.py selftest

`selftest` corrupts a stored number and asserts that `verify` reports it.
A harness that cannot fail is not evidence, so run it before trusting a pass.
"""
import json
import re
import sys
import time
from pathlib import Path

from maccabipediabot.common.wiki_login import get_site

FIXTURE = Path('infra/football_queries/fixtures/golden_numbers.json')
SECONDS_BETWEEN_RENDERS = 3.0

# Each target renders one display block for one real entity. Parameter keys
# are the Hebrew ones the templates already accept - they are the callers'
# contract and are not translated.
TARGETS = [
    {
        'label': 'player-events-by-competition/eran-zahavi',
        'template': 'סטטיסטיקה/תצוגה/שחקנים/סיכום אירועים לפי מפעל',
        'params': {'שחקן': 'ערן זהבי', 'קטגוריית מפעל': 'ליגה'},
    },
    {
        'label': 'player-events-by-competition/avi-cohen',
        'template': 'סטטיסטיקה/תצוגה/שחקנים/סיכום אירועים לפי מפעל',
        'params': {'שחקן': 'אבי כהן', 'קטגוריית מפעל': 'ליגה'},
    },
]

TAG = re.compile(r'<[^>]+>')
NUMBER = re.compile(r'-?\d[\d,]*(?:\.\d+)?')


def call_text(target: dict) -> str:
    """The wikitext that invokes one block, exactly as a page would."""
    params = ''.join(f'|{key}={value}' for key, value in target['params'].items())
    return f'{{{{{target["template"]}{params}}}}}'


def render(site, target: dict) -> dict:
    request = site.simple_request(
        action='parse', text=call_text(target), title='עונת 2021/22',
        contentmodel='wikitext', prop='text', formatversion=2,
        disablelimitreport=1, format='json')
    html = request.submit()['parse']['text']

    plain = re.sub(r'\s+', ' ', TAG.sub(' ', html)).strip()
    numbers = [match.group().replace(',', '') for match in NUMBER.finditer(plain)]
    return {'numbers': numbers, 'text': plain}


def capture(site) -> None:
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    fixture = {}

    for index, target in enumerate(TARGETS):
        if index:
            time.sleep(SECONDS_BETWEEN_RENDERS)
        rendered = render(site, target)
        fixture[target['label']] = {
            'template': target['template'],
            'params': target['params'],
            'call': call_text(target),
            'numbers': rendered['numbers'],
            'text': rendered['text'],
        }
        print(f'{target["label"]}: {len(rendered["numbers"])} numbers '
              f'{rendered["numbers"][:12]}')

    FIXTURE.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'wrote {FIXTURE}')


def verify(site) -> int:
    fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
    failures = 0

    for index, (label, expected) in enumerate(fixture.items()):
        if index:
            time.sleep(SECONDS_BETWEEN_RENDERS)
        target = {'template': expected['template'], 'params': expected['params']}
        actual = render(site, target)['numbers']

        if actual == expected['numbers']:
            print(f'OK    {label}  ({len(actual)} numbers)')
            continue

        failures += 1
        print(f'DIFF  {label}')
        for position, (was, now) in enumerate(
                zip(expected['numbers'], actual)):
            if was != now:
                print(f'        #{position}: fixture {was} -> rendered {now}')
        if len(actual) != len(expected['numbers']):
            print(f'        count: fixture {len(expected["numbers"])} '
                  f'-> rendered {len(actual)}')

    print(f'\n{len(fixture) - failures}/{len(fixture)} blocks match')
    return failures


def selftest(site) -> int:
    """Prove verify() fails on a wrong number before trusting it."""
    original = FIXTURE.read_text(encoding='utf-8')
    fixture = json.loads(original)
    label = next(iter(fixture))
    numbers = fixture[label]['numbers']
    if not numbers:
        raise RuntimeError(f'{label} captured no numbers - nothing to corrupt')

    numbers[0] = str(int(float(numbers[0])) + 1)
    FIXTURE.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'corrupted {label} number #0 -> {numbers[0]}, expecting a DIFF')

    try:
        failures = verify(site)
    finally:
        FIXTURE.write_text(original, encoding='utf-8')
        print('fixture restored')

    if failures:
        print('SELFTEST PASSED: the harness reports a wrong number')
        return 0
    print('SELFTEST FAILED: the harness compared nothing')
    return 1


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else 'capture'
    site = get_site()

    if command == 'capture':
        capture(site)
    elif command == 'verify':
        sys.exit(1 if verify(site) else 0)
    elif command == 'selftest':
        sys.exit(selftest(site))
    else:
        raise SystemExit(f'unknown command: {command}')


if __name__ == '__main__':
    main()
