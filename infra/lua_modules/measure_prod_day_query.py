"""Time the module's single merged query on production, and one of the
template's twenty-eight, for the same dates.

    uv run python infra/lua_modules/measure_prod_day_query.py

Read-only: action=cargoquery reads. Nothing on production invokes the modules
yet, so the page-level module timing cannot be measured there; what can be
measured is the query itself, which is where the cost is. The template pays 28
of these per page, the module one.
"""
import statistics
import subprocess
import sys
import time
import urllib.parse
import urllib.request

API = 'https://www.maccabipedia.co.il/api.php'
AGENT = 'MaccabipediaBot/1.0 (roeebaba@gmail.com) latency measurement'
PRINTER = 'infra/lua_modules/print_day_query.lua'

DATES = [
    '2021-01-14', '2021-02-09', '2021-03-15', '2021-08-22', '2021-09-16',
    '2021-11-07', '2021-12-31', '2022-02-24', '2022-03-05', '2022-04-02',
    '2022-08-29', '2022-12-26',
]
PAUSE_SECONDS = 1.0


def merged_query(date: str) -> dict:
    result = subprocess.run(
        ['lua5.1', PRINTER, f'"{date}"'], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(result.stderr)
    tables, join, where, fields = result.stdout.strip().split('\t')
    return {'tables': tables, 'join_on': join, 'where': where,
            'fields': fields, 'limit': '2'}


def one_template_query(date: str) -> dict:
    """What a single cell of the template costs: one count, one date."""
    return {
        'tables': 'Football_Games,Competitions',
        'join_on': 'Football_Games.Competition=Competitions.OriginalName',
        'where': f'DATE_FORMAT("{date}", "%d-%m") = '
                 'DATE_FORMAT(Football_Games.Date, "%d-%m") '
                 'AND Competitions.League = 1 AND Football_Games.ResultOpt = 1',
        'fields': 'COUNT(*)=n',
        'limit': '2',
    }


def timed(parameters: dict) -> float:
    data = urllib.parse.urlencode(
        {'action': 'cargoquery', 'format': 'json', **parameters}
    ).encode('utf-8')
    request = urllib.request.Request(
        API, data=data, headers={'User-Agent': AGENT,
                                 'Accept': 'application/json'})
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=180) as response:
        body = response.read()
    elapsed = (time.perf_counter() - started) * 1000
    if b'"error"' in body[:400]:
        raise SystemExit(body[:400])
    return elapsed


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def report(label: str, timings: list[float], per_page: int) -> None:
    print(f'\n{label}  (n={len(timings)})')
    print(f'  one query   p50 {percentile(timings, 0.50):7.0f} ms   '
          f'p95 {percentile(timings, 0.95):7.0f} ms')
    print(f'  x{per_page} per page  p50 '
          f'{percentile(timings, 0.50) * per_page:7.0f} ms   '
          f'p95 {percentile(timings, 0.95) * per_page:7.0f} ms')


def main() -> None:
    merged, single = [], []
    print(f'timing {len(DATES)} dates on production ...')
    for date in DATES:
        merged.append(timed(merged_query(date)))
        time.sleep(PAUSE_SECONDS)
        single.append(timed(one_template_query(date)))
        time.sleep(PAUSE_SECONDS)
        print(f'  {date}  merged {merged[-1]:7.0f} ms   '
              f'single {single[-1]:7.0f} ms')

    report('the module: ONE query, 24 conditional aggregates', merged, 1)
    report('the template: one cell of twenty-eight', single, 28)


if __name__ == '__main__':
    main()
