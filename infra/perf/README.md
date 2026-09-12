# Performance benchmark

Measures how long MaccabiPedia pages take to serve, and where the time goes.
Runs against prod by default; `--base-url http://localhost:8080` points it at
the local wiki.

```bash
cd infra/perf
uv run python pages.py                 # derive the page set from live Cargo
uv run python benchmark_server.py      # measure it
```

Both write to `.claude/tmp/perf/` by default. Archive a blessed run under
`~/maccabipedia-performance/<date>_<what>/`.

## What it measures, and why two signals

**Warm TTFB** — wall-clock for a normal anonymous request. This is what a
visitor pays when the page is already in the parser cache.

**Cold parse cost** — read from the `NewPP limit report`, which MediaWiki stores
*with* the parser-cache entry. It therefore describes the parse that filled the
cache: the expensive path, readable **without purging anything**.

`real_time - cpu_time` is time blocked on MySQL, which separates query cost from
template-expansion cost. On MaccabiPedia the database is the dominant term on
every slow page, so this split is the point of the tool.

## Judge fixes on the counters, not the clock

Wall-clock on shared CloudLinux hosting swings with whatever else is running on
the account. These counters do not move unless the wikitext changed:

- `expensive_fn_count`
- `post_expand_size`
- `template_arg_size`
- `pp_visited_nodes`

Hold a change to those. Wall-clock is the headline, not the proof.

`top_templates` — the per-template millisecond ranking — is how you tell *which*
edit moved a number. It is scraped from the HTML comment because it has no API
equivalent, unlike the counters (`action=parse&prop=limitreportdata`).

## The page set is derived, not hardcoded

`pages.py` picks pages from live Cargo so the set tracks the real data
distribution as the wiki grows:

- players with the most / mid-range / fewest `Games_Events` rows, which shows
  whether cost scales with row count
- the earliest season and the latest **complete** season — a season that has
  only just started has almost no games and would be a misleading "heavy" page
- the most recent game page, the most numerous page type on the wiki
- every portal, found by title prefix (they are hand-built, so not derivable
  from Cargo — and one of them is the slowest page on the site)

## Pages with no parser cache

`Special:`, search and category pages report `Cache expiry: none`. They are never
parser-cached, so every request re-runs the work and there is no warm path at
all. They have no limit report, and the runner records `counters.unavailable`
rather than failing. Their wall-clock is the only signal — and the only one that
matters, since it is always the "cold" number.

## Local wiki caveat

`--base-url http://localhost:8080` works, but local timings are **not**
comparable to prod: the local stack runs `CACHE_NONE` on MariaDB 10.11 against
prod's 10.0.38, and only holds seeded seasons. Local is valid for the
deterministic counters and for correctness checks, not for wall-clock.
