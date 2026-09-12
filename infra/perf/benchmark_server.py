"""Tier A benchmark: server-side timing + MediaWiki parser counters.

Two independent signals per page:

  * wall-clock TTFB of a normal anonymous request (what a repeat visitor pays)
  * the NewPP limit report, which is stored WITH the parser-cache entry and so
    reports the cost of the parse that filled the cache -- i.e. the expensive
    cold path, readable without purging anything.

`real_time - cpu_time` is time blocked on MySQL, which separates query cost
from template-expansion cost.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from wiki_api import DEFAULT_BASE_URL, DEFAULT_OUT_DIR, USER_AGENT, WikiApi, WikiApiError

# Structured counters from action=parse&prop=limitreportdata. Values are
# [used] or [used, limit]; the limit lets us report headroom.
COUNTER_KEYS = {
    "limitreport-cputime": "cpu_time",
    "limitreport-walltime": "real_time",
    "limitreport-ppvisitednodes": "pp_visited_nodes",
    "limitreport-postexpandincludesize": "post_expand_size",
    "limitreport-templateargumentsize": "template_arg_size",
    "limitreport-expansiondepth": "expansion_depth",
    "limitreport-expensivefunctioncount": "expensive_fn_count",
    "limitreport-unstrip-depth": "unstrip_depth",
    "limitreport-unstrip-size": "unstrip_size",
}


@dataclass
class PageResult:
    label: str
    title: str
    ttfb_samples: list[float] = field(default_factory=list)
    total_samples: list[float] = field(default_factory=list)
    size_bytes: int = 0
    counters: dict[str, Any] = field(default_factory=dict)
    cache: dict[str, Any] = field(default_factory=dict)
    top_templates: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ttfb_median(self) -> float:
        return statistics.median(self.ttfb_samples) if self.ttfb_samples else float("nan")

    @property
    def ttfb_worst(self) -> float:
        """Slowest sample seen.

        Deliberately NOT called p90: at the default 5 samples any percentile
        above the 80th resolves to the maximum, so naming it p90 would dress a
        single outlier up as a tail statistic. The outlier is the interesting
        part -- it is usually a parser-cache expiry caught mid-run -- so it is
        reported for what it is.
        """
        return max(self.ttfb_samples) if self.ttfb_samples else float("nan")

    @property
    def total_median(self) -> float:
        """Median time to finish reading the body; `total - ttfb` is transfer cost."""
        return statistics.median(self.total_samples) if self.total_samples else float("nan")

    @property
    def db_wait(self) -> float | None:
        cpu, real = self.counters.get("cpu_time"), self.counters.get("real_time")
        if cpu is None or real is None:
            return None
        return round(float(real) - float(cpu), 3)


def parse_limit_report(api: WikiApi, title: str) -> dict[str, Any]:
    """Structured parser counters for one page."""
    payload = api.get(action="parse", page=title, prop="limitreportdata")
    counters: dict[str, Any] = {}
    for entry in payload.get("parse", {}).get("limitreportdata", []):
        name = entry.get("name")
        if name not in COUNTER_KEYS:
            continue
        values = [entry[key] for key in sorted(entry) if key != "name"]
        counters[COUNTER_KEYS[name]] = values[0] if len(values) == 1 else values
    return counters


TEMPLATE_ROW = re.compile(
    r"^\s*(?P<pct>[\d.]+)%\s+(?P<ms>[\d.]+)\s+(?P<calls>\d+)\s+(?P<template>.+?)\s*$"
)


def scrape_html_extras(session: requests.Session, base_url: str,
                       title: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Cache state + per-template expansion ranking.

    Both live only in the rendered HTML comment; neither has an API equivalent.
    """
    url = f"{base_url}/{quote(title.replace(' ', '_'))}"
    response = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=180)
    response.raise_for_status()
    html = response.text

    cache: dict[str, Any] = {}
    for key, field_name in (("Cached time", "cached_time"),
                            ("Cache expiry", "cache_expiry"),
                            ("Reduced expiry", "reduced_expiry")):
        match = re.search(rf"{key}: (\S+)", html)
        if match:
            cache[field_name] = match.group(1)

    templates: list[dict[str, Any]] = []
    block = re.search(r"Transclusion expansion time report.*?-->", html, re.S)
    if block:
        for line in block.group(0).splitlines():
            row = TEMPLATE_ROW.match(line)
            if row and "-total" not in row.group("template"):
                templates.append({
                    "pct": float(row.group("pct")),
                    "ms": float(row.group("ms")),
                    "calls": int(row.group("calls")),
                    "template": row.group("template"),
                })
    return cache, templates[:10]


def time_request(session: requests.Session, base_url: str,
                 title: str) -> tuple[float, float, int]:
    """Return (ttfb_seconds, total_seconds, bytes) for one anonymous page view.

    The session is passed in so samples reuse a keep-alive connection. Building
    a fresh one per sample would fold a full DNS+TCP+TLS handshake into
    `Response.elapsed`, which measures around `adapter.send()` -- that is not
    what a repeat visitor pays, and it would sit as a constant floor under every
    number, making real improvements look smaller than they are.
    """
    url = f"{base_url}/{quote(title.replace(' ', '_'))}"
    started = time.monotonic()
    with session.get(url, headers={"User-Agent": USER_AGENT},
                     timeout=180, stream=True) as response:
        response.raise_for_status()
        ttfb = response.elapsed.total_seconds()
        body = response.content
    return ttfb, time.monotonic() - started, len(body)


def measure(session: requests.Session, base_url: str, api: WikiApi,
            page: dict[str, str], samples: int, pace: float) -> PageResult:
    result = PageResult(label=page["label"], title=page["title"])
    for _ in range(samples):
        ttfb, total, size = time_request(session, base_url, page["title"])
        result.ttfb_samples.append(ttfb)
        result.total_samples.append(total)
        result.size_bytes = size
        time.sleep(pace)
    # Special:, search and category pages are never parser-cached, so they have
    # no limit report. Their wall-clock is still meaningful — and it is all
    # they have, since every request re-runs the work.
    try:
        result.counters = parse_limit_report(api, page["title"])
    except WikiApiError as exc:
        result.counters = {"unavailable": str(exc)[:80]}
    try:
        result.cache, result.top_templates = scrape_html_extras(
            session, base_url, page["title"])
    except requests.RequestException as exc:
        result.cache = {"unavailable": str(exc)[:80]}
    return result


def render_report(results: list[PageResult]) -> str:
    lines = [
        "",
        f"{'page':16s} {'title':22s} {'warm TTFB':>11s} {'worst':>7s} "
        f"{'cold CPU':>9s} {'cold real':>10s} {'DB wait':>8s} {'expensive':>10s} {'KB':>6s}",
        "-" * 110,
    ]
    for result in results:
        title = result.title[:21]
        cpu = result.counters.get("cpu_time", "?")
        real = result.counters.get("real_time", "?")
        expensive = result.counters.get("expensive_fn_count", "?")
        if isinstance(expensive, list):
            expensive = expensive[0]
        db_wait = result.db_wait
        lines.append(
            f"{result.label:16s} {title:22s} "
            f"{result.ttfb_median:10.3f}s {result.ttfb_worst:6.3f}s "
            f"{str(cpu):>8s}s {str(real):>9s}s "
            f"{(f'{db_wait:.3f}' if db_wait is not None else '?'):>7s}s "
            f"{str(expensive):>10s} {result.size_bytes / 1024:5.0f}"
        )
    return "\n".join(lines)


def as_payload(results: list[PageResult], base_url: str, samples: int) -> dict[str, Any]:
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "samples_per_page": samples,
        "pages": [
            {
                "label": r.label, "title": r.title,
                "ttfb_median": round(r.ttfb_median, 4),
                "ttfb_worst": round(r.ttfb_worst, 4),
                "ttfb_samples": [round(s, 4) for s in r.ttfb_samples],
                "total_median": round(r.total_median, 4),
                "size_bytes": r.size_bytes,
                "counters": r.counters,
                "db_wait": r.db_wait,
                "cache": r.cache,
                "top_templates": r.top_templates,
            }
            for r in results
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--page-set", type=Path, default=DEFAULT_OUT_DIR / "page_set.json")
    parser.add_argument("--samples", type=int, default=5,
                        help="warm samples per page; median and worst are reported")
    parser.add_argument("--pace", type=float, default=3.0,
                        help="seconds between requests (shared hosting has CPU caps)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR / "run.json")
    args = parser.parse_args()

    pages = json.loads(args.page_set.read_text(encoding="utf-8"))
    api = WikiApi(args.base_url)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    # One session for every sample, so requests reuse a keep-alive connection
    # instead of paying a TLS handshake per sample.
    session = requests.Session()

    results: list[PageResult] = []
    for index, page in enumerate(pages, start=1):
        print(f"  [{index}/{len(pages)}] {page['label']} — {page['title']}", flush=True)
        try:
            results.append(measure(session, args.base_url, api, page,
                                   args.samples, args.pace))
        except (requests.RequestException, WikiApiError) as exc:
            # A run takes many minutes; one 503 from the shared host must not
            # discard every page measured so far.
            print(f"      SKIPPED — {exc}", flush=True)
            continue
        # Written after every page, for the same reason.
        args.out.write_text(
            json.dumps(as_payload(results, args.base_url, args.samples),
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(render_report(results))
    print(f"\nwrote {args.out}  ({len(results)}/{len(pages)} pages measured)")


if __name__ == "__main__":
    main()
