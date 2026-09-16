"""Compare the day page on PRODUCTION data: live template against the module.

    uv run python infra/football_queries/compare_prod_day_pages.py --publish
    uv run python infra/football_queries/compare_prod_day_pages.py --compare
    uv run python infra/football_queries/compare_prod_day_pages.py --compare --limit 20

`--publish` writes ONE page: a sandbox copy of the day template whose four
header queries and four block transclusions are replaced by one prime plus
reads of it. Nothing transcludes that page, so it changes nothing a reader
sees; it exists so the module can be rendered against real production data
before the live template is touched.

`--compare` renders both, for every day of the year, and compares byte for
byte. This is the one thing the local harness cannot prove: the local wiki
holds 2021/22-2024/25 while production holds every season back to 1906, and
the day block is exactly where old data is odd - games with no events,
technical results, and sums over nothing.

It also times both paths, which is the real before/after for this migration.

Resumable: each date's verdict is appended as it is measured, because a run
over 366 dates against production should not have to start again.
"""
import argparse
import datetime
import difflib
import json
import statistics
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, 'packages/maccabipediabot/src')

API = 'https://www.maccabipedia.co.il/api.php'
AGENT = 'MaccabipediaBot/1.0 (roeebaba@gmail.com) module parity check'

TEMPLATE = 'תבנית:סטטיסטיקה/תצוגה/ימים/סיכום תוצאות'
SANDBOX = TEMPLATE + '/ארגז חול מודול'

RESULTS = Path('infra/football_queries/fixtures/prod_day_parity.jsonl')
PAUSE_SECONDS = 0.4

SUMMARY = ('ארגז חול להשוואת מודול הלואה מול התבנית - אף דף אינו קורא לו '
           '(deployed from infra/football_queries)')


def site():
    import pywikibot

    pywikibot.config.max_retries = 1
    pywikibot.config.retry_wait = 5

    from maccabipediabot.common.wiki_login import get_site

    return get_site()


def read_page(connection, title: str) -> str:
    import pywikibot as pw

    page = pw.Page(connection, title)
    if not page.exists():
        raise SystemExit(f'{title} does not exist on production')
    return page.text


def candidate_of(body: str) -> str:
    """The live template with its 28 queries replaced by one.

    Built by EDITING the real text: the <shtml> tab strip is signed with an
    HMAC under the wiki's own secret and can only be surrounded, never
    rebuilt. Every substitution must match exactly once, or this refuses -
    a candidate that silently changed nothing would compare the template with
    itself and pass.
    """
    def replace_once(text: str, old: str, new: str, what: str) -> str:
        if text.count(old) != 1:
            raise SystemExit(
                f'{what}: expected exactly one match, found {text.count(old)} '
                '- refusing to build a candidate that may change nothing')
        return text.replace(old, new)

    body = replace_once(
        body, '<includeonly>',
        '<includeonly>{{#invoke:FootballStatsBlock|prime|בלוק=day-results}}',
        'the prime call')

    for category, variable in (
            ('ליגה', 'משחקים בליגה'),
            ('גביע', 'משחקים בגביע המדינה'),
            ('בינלאומי', 'משחקים באירופה'),
            ('רשמי', 'משחקים בכל המסגרות')):
        old = ('{{סטטיסטיקה/שליפות/מתקדמות/כמות נתוני משחק| '
               f'קטגוריית מפעל={category}| תאריך={{{{{{תאריך|}}}}}}| '
               'פורמט תאריך="%d-%m"}}')
        new = ('{{#invoke:FootballStatsBlock|value|בלוק=day-results|תא=games'
               f'|קטגוריית מפעל={category}|תאריך={{{{{{תאריך|}}}}}}}}}}')
        body = replace_once(body, old, new, f'the {variable} header query')

    for category in ('ליגה', 'גביע', 'בינלאומי', 'רשמי'):
        for spacing in (
                '{{סטטיסטיקה/תצוגה/ימים/סיכום תוצאות לפי מפעל| '
                f'תאריך={{{{{{תאריך|}}}}}}| קטגוריית מפעל={category} }}}}',
                '{{סטטיסטיקה/תצוגה/ימים/סיכום תוצאות לפי מפעל| '
                f'תאריך={{{{{{תאריך|}}}}}} |קטגוריית מפעל={category} }}}}'):
            if spacing in body:
                body = replace_once(body, spacing, (
                    '{{#invoke:FootballStatsBlock|tab|בלוק=day-results'
                    f'|קטגוריית מפעל={category}'
                    '|תאריך={{{תאריך|}}}}}'), f'the {category} tab body')
                break
        else:
            raise SystemExit(f'the {category} tab body is not where this '
                             'expects it')

    return body


def publish(connection, title: str, wanted: str,
            summary: str = SUMMARY) -> str:
    """Multipart, because the WAF refuses these bodies urlencoded."""
    import pywikibot as pw
    from pywikibot.comms import http as pw_http

    response = pw_http.session.post(
        connection.base_url('/api.php'),
        files={
            'action': (None, 'edit'),
            'title': (None, title),
            'text': (None, wanted),
            'summary': (None, summary),
            'token': (None, connection.tokens['csrf']),
            'format': (None, 'json'),
            'bot': (None, '1'),
        },
        headers={'Accept': 'application/json'}, timeout=120)

    if 'application/json' not in response.headers.get('Content-Type', ''):
        return (f'REFUSED ({response.status_code}, '
                f'{response.headers.get("Content-Type", "?")})')
    answer = response.json()
    if 'error' in answer:
        return f'ERROR {answer["error"].get("code")}'

    time.sleep(1)
    fresh = pw.Page(connection, title)
    if not fresh.exists():
        return 'MISSING AFTER SAVE'
    fresh.get(force=True)
    return 'ok' if fresh.text.strip() == wanted.strip() else 'MISMATCH'


def render(title: str, date: str) -> tuple[str, float]:
    text = '{{%s| תאריך="%s" }}' % (title.removeprefix('תבנית:'), date)
    data = urllib.parse.urlencode({
        'action': 'parse', 'text': text, 'title': 'ארגז חול',
        'contentmodel': 'wikitext', 'prop': 'text',
        'disablelimitreport': 1, 'format': 'json',
    }).encode('utf-8')
    request = urllib.request.Request(
        API, data=data,
        headers={'User-Agent': AGENT, 'Accept': 'application/json'})
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=180) as response:
        body = json.loads(response.read().decode('utf-8'))
    elapsed = (time.perf_counter() - started) * 1000
    if 'error' in body:
        raise SystemExit(body['error'])
    return body['parse']['text'], elapsed


def every_day_of_year() -> list[str]:
    """One date per day of the year. 2020 is a leap year, so all 366 exist.

    The block matches on %d-%m across every season, so the year in the input
    is only a carrier for the day and month.
    """
    start = datetime.date(2020, 1, 1)
    return [(start + datetime.timedelta(days=offset)).isoformat()
            for offset in range(366)]


def done_already() -> dict:
    if not RESULTS.exists():
        return {}
    verdicts = {}
    for line in RESULTS.read_text(encoding='utf-8').splitlines():
        if line.strip():
            entry = json.loads(line)
            verdicts[entry['date']] = entry
    return verdicts


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def compare(limit: int | None) -> int:
    dates = every_day_of_year()
    if limit:
        dates = dates[:limit]

    verdicts = done_already()
    if verdicts:
        print(f'resuming: {len(verdicts)} date(s) already compared')
    RESULTS.parent.mkdir(parents=True, exist_ok=True)

    differences = 0
    for index, date in enumerate(dates, start=1):
        if date in verdicts:
            continue

        template_html, template_ms = render(TEMPLATE, date)
        time.sleep(PAUSE_SECONDS)
        module_html, module_ms = render(SANDBOX, date)
        time.sleep(PAUSE_SECONDS)

        identical = template_html == module_html
        entry = {'date': date, 'identical': identical,
                 'template_ms': round(template_ms, 1),
                 'module_ms': round(module_ms, 1)}
        with RESULTS.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + '\n')
        verdicts[date] = entry

        if not identical:
            differences += 1
            diff = '\n'.join(list(difflib.unified_diff(
                template_html.splitlines(), module_html.splitlines(),
                'template', 'module', lineterm='', n=1))[:24])
            print(f'DIFF  {date}\n{diff}')
        if index % 25 == 0 or index == len(dates):
            print(f'  {index}/{len(dates)} compared', flush=True)

    measured = [entry for entry in verdicts.values()
                if entry['date'] in set(dates)]
    differing = [entry['date'] for entry in measured if not entry['identical']]
    template_ms = [entry['template_ms'] for entry in measured]
    module_ms = [entry['module_ms'] for entry in measured]

    print(f'\n{len(measured) - len(differing)}/{len(measured)} day pages '
          'byte-identical on production data')
    if differing:
        print(f'differing: {differing[:20]}')

    print(f'\nrender time on production (n={len(measured)}):')
    print(f'  template  p50 {percentile(template_ms, 0.50):7.0f} ms   '
          f'p95 {percentile(template_ms, 0.95):7.0f} ms   '
          f'mean {statistics.mean(template_ms):7.0f} ms')
    print(f'  module    p50 {percentile(module_ms, 0.50):7.0f} ms   '
          f'p95 {percentile(module_ms, 0.95):7.0f} ms   '
          f'mean {statistics.mean(module_ms):7.0f} ms')
    return 1 if differing else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true',
                        help='write the sandbox copy (one page, unused)')
    parser.add_argument('--compare', action='store_true',
                        help='render both for every day of the year')
    parser.add_argument('--limit', type=int,
                        help='compare only the first N dates')
    options = parser.parse_args()

    if not (options.publish or options.compare):
        parser.error('pass --publish or --compare')

    if options.publish:
        connection = site()
        body = read_page(connection, TEMPLATE)
        candidate = candidate_of(body)
        print(f'{TEMPLATE}: {len(body)} chars -> candidate '
              f'{len(candidate)} chars')
        print(f'writing {SANDBOX}')
        print(f'  {publish(connection, SANDBOX, candidate)}')

    sys.exit(compare(options.limit) if options.compare else 0)


if __name__ == '__main__':
    main()
