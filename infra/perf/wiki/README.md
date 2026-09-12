# Wiki-side performance work

Lua modules and template changes that cut page-render cost. **Developed and
verified on the local wiki; none of this is on production.** Wiki content is not
in the repo, so this directory is where the source lives.

`apply_wiki_optimisations.py` puts a local wiki into the optimised state
(idempotent; `--revert` restores, `--status` reports).

## Measuring locally

Two environment variables matter, both set in `infra/local-wiki/docker-compose.yml`
under the `mediawiki` service:

```yaml
MW_DISABLE_FOREIGN_IMAGES: "1"   # required for stable timings
MW_TRACE_SQL: "1"                # optional, to count SQL per render
```

**`MW_DISABLE_FOREIGN_IMAGES` is not optional for measurement.** Without it the
local wiki resolves every image from production over HTTP mid-render, so page
timings measure network latency to prod — and image-heavy pages blow PHP's
30-second limit and return HTTP 500. It is off by default because the foreign
repo is a real local-wiki feature (and `test_foreign_image_repo.py` covers it);
turn it on only while measuring.

Heavy pages also need more than PHP's default 30 s locally; that limit is raised
in `LocalSettings.env.local.php`.

## Measured on the local wiki

Football 2021/22–2024/25 seeded: 222 games, 15,540 events.

| | ערן זהבי (player) | עונת 2021/22 (season) |
|---|---|---|
| render, median of 7 | 2.51 s → **1.19 s** (−52%) | 4.34 s → **3.35 s** (−23%) |
| SQL statements | 2,455 → 1,281 (−48%) | 4,613 → 2,414 (−48%) |
| `SHOW TABLES` | 391 → 60 (−85%) | 481 → 277 (−42%) |
| preprocessor nodes | 19,152 → 5,860 (−69%) | 74,755 → 41,657 (−44%) |
| post-expand size | 601,215 → 166,563 (−72%) | 1,130,777 → 953,546 (−16%) |
| template arg size | 457,280 → 37,657 (−92%) | — |
| expensive functions | 8 → 8 | 2,176 → 661 (−70%) |
| **parser cache TTL** | **3600 → 86400** | **3600 → 86400** |

Every rendered statistic was compared before and after: 85 values across both
pages, all identical.

## The five changes

### 1. One `#invoke` per stats column, not one per statistic

**Scribunto does not keep module state between `#invoke` calls.** Measured: 1
call 0.035 s CPU, 5 calls 0.100 s, 20 calls 0.341 s, 65 calls 0.968 s — exactly
linear. A module that caches a Cargo query in a local therefore re-queries on
every call and saves nothing.

So `פרופיל כדורגל/הצגת עמודת סטטיסטיקה/שחקן/הצגה` became a single call into
`Module:סטטיסטיקה שחקן|column`, which fetches once and computes all statistics
from the rows. **0.235 s → 0.032 s per column.**

This also replaced 89 lines of repeated `#vardefine` + `#ifexpr` markup with a
list of rows in Lua.

### 2. Season summary: 24 aggregate queries → one grouped query

`עונת כדורגל/הצגת מספרים עונתיים/הצגה לפי מפעל` ran six `כמות נתוני משחק`
lookups per competition category. `Module:סטטיסטיקה משחקים|gameStat` groups by
every dimension the template filters on and answers all of them from one query.

`כמות נתוני משחק` itself is untouched — it accepts parameters the module does
not implement (referee, coach, stadium, date), and the module returns a visible
error rather than silently ignoring an unsupported filter.

### 3. Stop rendering galleries to test whether they are empty

The game-row template did this three times per game:

```wikitext
{{#תנאי: {{הצגת גלריה לפי קטגוריה |שם קטגוריה=…|אין תוצאות=}} |<icon>}}
```

It built a complete photo gallery, threw it away, and showed a one-character
icon if the output was non-empty — 171 galleries per season page.

`תבנית:קטגוריה מכילה קבצים` answers the actual question using
`PAGESINCATEGORY`, which reads the count MediaWiki already maintains in the
`category` table. Over 171 checks: **DPL 0.654 s CPU / 433 SQL → 0.024 s / 116
SQL.**

### 4. `תיקון פורמט תמונה`: 38 extension permutations → 8

The template checks the filename as given, then falls back to trying every
permutation (`jPg`, `jpEg`, `JpeG`…). Missing images are the common case on a
season page, so that fallback ran 38 `#ifexist` calls per lookup, 58 lookups per
page. Mixed-case permutations match nothing real; the list also contained `PNG`
twice. **Expensive parser functions 2,176 → 661.**

### 5. Parser cache TTL: 3600 → 86400 on every page

Two separate causes, both fixed:

- **`{{#dpl:}}`** calls `updateCacheExpiry(cacheperiod ?? 3600)`. There is no
  global setting in any DPL3 version (checked against `master`), so
  `|cacheperiod=86400` was added to all 27 call sites.
- **`תבנית:גיל`** used `{{שנה נוכחית}}` / `{{חודש נוכחי}}` / `{{יום נוכחי}}`,
  marking every player page time-dependent — for a number that changes once a
  year. `Module:גיל` computes it with `os.date`, which carries no
  time-dependence, so the page keeps the full day of cache. Verified against the
  old template across birthday boundaries and a leap day.

**This is the highest-leverage item**: it does not make any page faster, it
makes pages re-parse 24× less often.

## Two traps worth remembering

**`|cacheperiod` must be the LAST parameter.** The first parameter of a parser
function has no leading `|`, so inserting `|cacheperiod=…` directly after
`{{#dpl:` swallows the original first parameter into its value — silently
unsetting `category` and making the gallery list the entire wiki. This was
caught only because rendered output was diffed.

**The season page is non-deterministic.** Two renders of unchanged wikitext
differ by ~380 fragments and even in length, because a query orders rows without
an `ORDER BY`. A raw HTML diff can never validate a change there — compare the
rendered *values* instead. This is a pre-existing bug, unrelated to the work
here, and worth fixing on its own.

## Before deploying any of this to production

- Prod has far more data; re-measure there rather than assuming these ratios.
- The modules deliberately reject parameters they do not implement. Check no
  production page passes a filter that is only supported by the old templates.
- Goalkeeper statistics still route through the existing templates
  (`SUM(ResultOpponent)` and opponent events are not in the module's query).
