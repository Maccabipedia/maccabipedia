"""How long does a day summary take to render on production, today?

    uv run python infra/lua_modules/measure_prod_day_pages.py

Read-only: every request is action=parse with wikitext, which renders without
saving anything. A preview parse is not served from the parser cache either,
so each measurement is a real render rather than a cache hit - which is the
number that matters, because a page with 28 Cargo queries pays them again
every time its cache is invalidated.

Reports p50 and p95 over a spread of dates, and the same dates' query count
for reference. Paced deliberately: this is production.
"""
import statistics
import sys
import time
import urllib.parse
import urllib.request

API = 'https://www.maccabipedia.co.il/api.php'
AGENT = 'MaccabipediaBot/1.0 (roeebaba@gmail.com) latency measurement'
TEMPLATE = sys.argv[1] if len(sys.argv) > 1 else 'סטטיסטיקה/תצוגה/ימים/סיכום תוצאות'

# A spread across the calendar: league-season dates, summer dates with almost
# no games, and the European-night months.
DATES = [
    '2021-01-14', '2021-02-09', '2021-03-15', '2021-04-02', '2021-05-24',
    '2021-06-11', '2021-07-04', '2021-08-22', '2021-09-16', '2021-10-30',
    '2021-11-07', '2021-12-31', '2022-01-22', '2022-02-24', '2022-03-05',
    '2022-04-02', '2022-05-15', '2022-06-08', '2022-07-19', '2022-08-29',
    '2022-09-30', '2022-10-12', '2022-11-06', '2022-12-26',
]
PAUSE_SECONDS = 1.0


def render_ms(wikitext: str) -> float:
    data = urllib.parse.urlencode({
        'action': 'parse', 'text': wikitext, 'title': 'ארגז חול',
        'contentmodel': 'wikitext', 'prop': 'text',
        'disablelimitreport': 1, 'format': 'json',
    }).encode('utf-8')
    request = urllib.request.Request(
        API, data=data, headers={'User-Agent': AGENT,
                                 'Accept': 'application/json'})
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=180) as response:
        body = response.read()
    elapsed = (time.perf_counter() - started) * 1000
    if b'"error"' in body[:200]:
        raise SystemExit(body[:300])
    return elapsed


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1,
                max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def main() -> None:
    timings = []
    print(f'rendering {{{{{TEMPLATE}}}}} for {len(DATES)} dates on '
          f'production ...')
    for index, date in enumerate(DATES, start=1):
        wikitext = '{{%s| תאריך="%s" }}' % (TEMPLATE, date)
        elapsed = render_ms(wikitext)
        timings.append(elapsed)
        print(f'  {date}  {elapsed:8.0f} ms')
        if index != len(DATES):
            time.sleep(PAUSE_SECONDS)

    print(f'\nn={len(timings)}')
    print(f'  min  {min(timings):8.0f} ms')
    print(f'  p50  {percentile(timings, 0.50):8.0f} ms')
    print(f'  p95  {percentile(timings, 0.95):8.0f} ms')
    print(f'  max  {max(timings):8.0f} ms')
    print(f'  mean {statistics.mean(timings):8.0f} ms')


if __name__ == '__main__':
    main()
