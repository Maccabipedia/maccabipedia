# MaccabiPedia Lua Modules

Wiki content is not in this repository — except this. The Lua that renders
statistics on MaccabiPedia lives in `infra/perf/wiki/*.lua`, and **the repo is
the source of truth**: the wiki copy is deployed from here, never edited on the
wiki and copied back.

## 1. Why Lua at all

The wiki's statistics were built from parser-function templates, and the cost is
not the queries — it is how many of them there are. A Cargo query on this wiki
costs roughly 0.7 ms of SQL and about eight times that in per-query bookkeeping
(`tableExists`, `cargo_backlinks`), so **fewer queries beats cheaper queries**,
every time. See `.claude/maccabipedia_structure_knowledge.md` §15.

Templates cannot hold a result between two uses of it. Lua can — within limits
that are the single most important thing to understand here.

## 2. The one rule that shapes every module

**Scribunto does not keep module state between `#invoke` calls.** Measured: 1
call 0.035 s CPU, 5 calls 0.100 s, 20 calls 0.341 s, 65 calls 0.968 s — exactly
linear. A module that caches a query result in a local re-queries on every call
and saves nothing.

Three things do survive, and every optimisation here is one of them:

| mechanism | scope | takes arguments? |
|---|---|---|
| a local inside one `#invoke` | that call | yes |
| `mw.loadData('Module:X')` | the whole parse | **no** |
| `frame:callParserFunction('#vardefine', …)` | the rest of the page | yes |

So the shape of a fast module is: **one `#invoke` does all the work for a whole
block**, not one per number. `Module:שיאנים|section` renders four tabs and their
four counts from one query, where the template ran eight.

`mw.loadData` caches by *module name*, so it can only serve the unfiltered case.
A stadium or opponent page has nowhere to put its filter and runs its own query.

## 3. The modules

| module | what it renders | replaces |
|---|---|---|
| `יחידה:שיאנים` | leaderboards — a whole records block per query | `…/שיאני כמות אירועי שחקן/עיצוב חדש` |
| `יחידה:שיאנים/נתונים` | data module: per-player event counts, one query per page | — |
| `יחידה:סטטיסטיקה משחקים` | the general-numbers block, four tabs from two queries | `…/כמות נתוני משחק` |
| `יחידה:סטטיסטיקה שחקן` | a player's whole stats column from one query | `…/כמות אירועי שחקן` |
| `יחידה:המרות` + `/נתונים` | stadium and opponent alias lookups | `המרות/המרות …` |
| `יחידה:גיל` | age from `os.date`, so the page is not time-dependent | `תבנית:גיל` |

## 4. Guidelines

**Comments in English.** Identifiers stay Hebrew — template names, parameter
names and Cargo values are the real names on the wiki and translating them makes
the code wrong. The prose explaining them is English.

**One `#invoke` per block, never per number.** If a template calls the module in
a loop, the module is the wrong shape. See §2.

**Never silently ignore a parameter.** A filter that is dropped does not look
like a failure, it looks like a number. Every module declares what it supports
and returns a visible error otherwise — *and* the wrapper template must forward
every parameter, or the guard never sees the one it would have rejected. That
bug shipped once: an opponent page asking for its own yellow cards was handed
the wiki-wide total of 425. `check_shim_parity.py` exists to catch it.

**Check the row limit.** Cargo truncates at the limit silently — no error, no
warning — and a leaderboard built from a cut-off result is a normal-looking
table of wrong numbers. Compare `#rows` against the cap and error out.
`check_query_limits.py` measures the real sizes against production.

**Know which columns store quotes.** `Opponent`, `Stadium` and `Competition`
are stored stripped (`ביתר ירושלים`); `PlayerName` and `Refs` keep the
apostrophe (`אביעזר ז'נו`). Querying a stripped column with the raw page name
returns zero rows and no error. Structure knowledge §16.

**Reproduce the wikitext's arithmetic exactly.** `{{סטטיסטיקה/אחוזים}}` rounds
to two places and `{{#number_format}}` then rounds again — two roundings, which
a single `%.0f` does not match at the boundary. Lua's `string.format` also
rounds half-to-even where MediaWiki rounds half-up.

**`#invoke` output is parsed as wikitext.** Tags outside MediaWiki's allowlist
are escaped — `<a>`, `<input>`, `<label>` among them. Use `[url text]`, not an
anchor tag. Raw HTML needs `<shtml>`, which Lua cannot sign.

**Never rebuild a signed `<shtml>` block.** Its hash is an HMAC of the exact
content under a per-wiki secret: the same tab strip carries a different hash on
production and on the local wiki. Copy it through byte-for-byte, from the wiki
you are deploying to.

## 5. Deploying and verifying

```bash
uv run python infra/perf/wiki/apply_wiki_optimisations.py      # local wiki
uv run python infra/perf/wiki/check_shim_parity.py             # module vs original
uv run python infra/perf/wiki/check_query_limits.py            # room before truncation
uv run python infra/perf/wiki/verify_numbers_against_prod.py   # recompute independently
uv run python infra/perf/wiki/shadow_verify_on_prod.py verify  # real Lua, real data
```

Two of those are different in kind and both matter. `shadow_verify_on_prod`
diffs the module against the live page; `verify_numbers_against_prod`
re-derives the numbers in Python from the original wikitext's meaning. A diff
passes when both sides are wrong the same way. An independent recomputation
does not.

`README.md` in that directory records what each change did and what has been
measured.

## 6. What is deliberately not in Lua

- **Goalkeeper statistics** — `SUM(ResultOpponent)` and opponent-side events are
  not in the modules' queries.
- **`עוזר שופט`** — needs a `HOLDS` join to `Games_Referees`. Referee pages
  render every section twice, once for שופט ראשי and once for עוזר שופט; only
  the first goes through Lua.
- **The tab strips themselves** — signed `<shtml>`, see §4.

## 7. Known duplication, not yet fixed

`יחידה:שיאנים` and `יחידה:סטטיסטיקה משחקים` each carry their own copy of the
join graph, the quote-stripping rules, the row-limit guard and the competition
flags — and they have already drifted apart:

- three different ways to escape a name for SQL (`sanitize`, `opponentList`,
  `sqlList`)
- `קטגוריית מפעל=רשמי` returns `true` in one and tests `row.official` in the
  other; both correct, but the first depends on a `WHERE` clause in another file

The fix is a shared query layer that owns the join graph, the per-column quote
rules and the limit guard, with the display modules on top of it. Not yet
written. Modelled on `תבנית:חיפוש משחק כדורגל`, which already centralises a
parameterised games query — but resolving joins from what was asked for, since
that template joins twelve tables unconditionally.
