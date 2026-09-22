"""The published numbers on every day page, before and after migrating them.

    uv run python infra/lua_modules/capture_day_pages.py capture
    uv run python infra/lua_modules/capture_day_pages.py verify
    uv run python infra/lua_modules/capture_day_pages.py selftest

Read-only in every mode. Nothing is written to any wiki.

תבנית:סטטיסטיקה/תצוגה/ימים/סיכום תוצאות is transcluded by 366 pages, one per
day of the year, and costs 28 Cargo queries per page. It is the largest single
migration available, and a template edit reaches all 366 at once - there is no
canary page to try it on, because they all share the template.

So the safety net is this: record what production renders on every one of them
BEFORE the edit, then re-render all of them immediately after and require every
labelled number, on every page, to be identical. One differing number means
revert.

What is recorded per page: the four tab headers ("ליגה (N משחקים)") and every
label/value row inside the four tabs. Labels rather than positions, because the
same label appears once per tab.
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, 'packages/maccabipediabot/src')

DAY_TEMPLATE = 'תבנית:סטטיסטיקה/תצוגה/ימים/סיכום תוצאות'
FIXTURE = Path('infra/lua_modules/fixtures/day_pages_baseline.json')
# Each page is appended here as it is fetched, so an interrupted walk resumes
# instead of asking production for all 366 pages again.
PARTIAL = FIXTURE.with_suffix('.partial.jsonl')

# Between page renders. A day page costs 28 Cargo queries on production, so
# this walks rather than runs.
PAUSE_SECONDS = 0.4

LABELLED = re.compile(
    r'<div class="Top10RowName">(.{1,40}?)</div>'
    r'\s*<span class="Top10RowStat">(.{0,120}?)</span>')
HEADER = re.compile(r'<div class="tab-header">(.{1,80}?)</div>')


def site():
    from maccabipediabot.common.wiki_login import get_site

    return get_site()


def day_pages(connection) -> list[str]:
    pages, parameters = [], {
        'action': 'query', 'list': 'embeddedin', 'eititle': DAY_TEMPLATE,
        'eilimit': 500, 'einamespace': 0, 'format': 'json',
    }
    while True:
        response = connection.simple_request(**parameters).submit()
        pages += [row['title'] for row in response['query']['embeddedin']]
        if 'continue' not in response:
            return sorted(pages)
        parameters.update(response['continue'])


def numbers_on(connection, title: str) -> dict:
    """Every published number of the day block on one page."""
    parsed = connection.simple_request(
        action='parse', page=title, prop='text', formatversion=2,
        disablelimitreport=1, format='json').submit()
    html = parsed['parse']['text']

    found = {}
    for index, header in enumerate(HEADER.findall(html), start=1):
        found[f'header#{index}'] = re.sub(
            r'\s+', ' ', re.sub(r'<[^>]+>', '', header)).strip()
    for label, value in LABELLED.findall(html):
        label = re.sub(r'<[^>]+>', '', label).strip()
        value = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', value)).strip()
        key, index = label, 2
        while key in found:
            key = f'{label}#{index}'
            index += 1
        found[key] = value
    return found


def provenance(connection) -> dict:
    """What this baseline describes, so a capture taken AFTER a migration
    cannot pass itself off as the before picture."""
    import pywikibot as pw

    page = pw.Page(connection, DAY_TEMPLATE)
    revision = page.latest_revision
    return {
        'captured': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'template': DAY_TEMPLATE,
        'revision': revision.revid,
        'revision_timestamp': str(revision.timestamp),
        'note': 'if the template revision has changed since, this baseline '
                'may already describe migrated output - re-read before '
                'trusting a pass',
    }


def load_partial() -> dict:
    if not PARTIAL.exists():
        return {}
    collected = {}
    for line in PARTIAL.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        collected[entry['title']] = entry['numbers']
    return collected


def walk(connection, pages: list[str], label: str, resume: bool = False) -> dict:
    collected = load_partial() if resume else {}
    if collected:
        print(f'  resuming: {len(collected)} page(s) already fetched')
    if resume:
        PARTIAL.parent.mkdir(parents=True, exist_ok=True)

    for index, title in enumerate(pages, start=1):
        if title in collected:
            continue
        collected[title] = numbers_on(connection, title)
        if resume:
            with PARTIAL.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(
                    {'title': title, 'numbers': collected[title]},
                    ensure_ascii=False) + '\n')
        if index % 25 == 0 or index == len(pages):
            print(f'  {label} {index}/{len(pages)}')
        time.sleep(PAUSE_SECONDS)
    return collected


def capture() -> None:
    connection = site()
    pages = day_pages(connection)
    print(f'{len(pages)} day page(s) transclude {DAY_TEMPLATE}')

    fixture = {'__provenance__': provenance(connection)}
    fixture.update(walk(connection, pages, 'captured', resume=True))

    numbers = sum(len(values) for title, values in fixture.items()
                  if title != '__provenance__')
    if numbers == 0:
        raise SystemExit('captured no numbers at all - a baseline like that '
                         'matches any candidate')

    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=1, sort_keys=True),
        encoding='utf-8')
    PARTIAL.unlink(missing_ok=True)
    print(f'\nwrote {numbers} number(s) across {len(pages)} page(s) '
          f'to {FIXTURE}')


def compare(baseline: dict, current: dict) -> int:
    differences = 0
    for title, expected in sorted(baseline.items()):
        if title == '__provenance__':
            continue
        actual = current.get(title)
        if actual is None:
            print(f'MISSING  {title} did not render')
            differences += 1
            continue
        for label, value in sorted(expected.items()):
            if actual.get(label) != value:
                print(f'DIFF  {title}  {label}: '
                      f'{value!r} -> {actual.get(label)!r}')
                differences += 1
        for label in sorted(set(actual) - set(expected)):
            print(f'NEW   {title}  {label}: {actual[label]!r}')
            differences += 1
    return differences


def purge() -> int:
    """Re-parse every day page, so a later verify cannot read a stale cache.

    After the template edit the parser cache still holds each page as it
    rendered BEFORE it, and action=parse serves that. Verifying against it
    would compare the old output with itself and pass no matter what the
    modules do. Batches of ten: fifty exceeds this host's API time limit.
    """
    import pywikibot as pw

    connection = site()
    pages = day_pages(connection)
    print(f'purging {len(pages)} day page(s), ten at a time')

    purged = 0
    for start in range(0, len(pages), 10):
        batch = pages[start:start + 10]
        response = connection.simple_request(
            action='purge', forcelinkupdate=1, titles='|'.join(batch),
            format='json').submit()
        purged += len(response.get('purge', []))
        print(f'  {purged}/{len(pages)}', flush=True)
        time.sleep(PAUSE_SECONDS)

    if purged != len(pages):
        print(f'only {purged} of {len(pages)} were purged - a verify now '
              'could read a stale cache')
        return 1
    return 0


def verify() -> int:
    if not FIXTURE.exists():
        raise SystemExit(f'no baseline at {FIXTURE} - run capture first')
    baseline = json.loads(FIXTURE.read_text(encoding='utf-8'))

    connection = site()
    pages = [title for title in baseline if title != '__provenance__']
    print(f'{baseline["__provenance__"]["template"]} was revision '
          f'{baseline["__provenance__"]["revision"]} when this was captured '
          f'({baseline["__provenance__"]["captured"]})')

    current = walk(connection, pages, 'rendered')
    differences = compare(baseline, current)

    print(f'\n{differences} difference(s) across {len(pages)} page(s)')
    return 1 if differences else 0


def selftest() -> int:
    """A comparison that cannot fail is not a safety net."""
    if not FIXTURE.exists():
        raise SystemExit(f'no baseline at {FIXTURE} - run capture first')
    baseline = json.loads(FIXTURE.read_text(encoding='utf-8'))

    pages = {title: values for title, values in baseline.items()
             if title != '__provenance__'}
    if not pages:
        raise SystemExit('the baseline holds no pages')

    if compare(baseline, dict(pages)) != 0:
        print('SELFTEST FAILED: the baseline does not match itself')
        return 1

    title = sorted(pages)[0]
    corrupted = {name: dict(values) for name, values in pages.items()}
    label = sorted(corrupted[title])[0]
    corrupted[title][label] = str(corrupted[title][label]) + '9'
    if compare(baseline, corrupted) == 0:
        print('SELFTEST FAILED: a changed number was not reported')
        return 1

    print('\nSELFTEST PASSED: identical matches, one changed number does not')
    return 0


def main() -> None:
    modes = {'capture': capture, 'verify': verify, 'selftest': selftest,
             'purge': purge}
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode not in modes:
        raise SystemExit(f'usage: {sys.argv[0]} {"|".join(modes)}')
    sys.exit(modes[mode]() or 0)


if __name__ == '__main__':
    main()
