# Wiki-side performance work

Lua modules and template changes that cut page-render cost. **Developed and
verified on the local wiki; none of this is on production.** Wiki content is not
in the repo, so this directory is where the source lives.

`apply_wiki_optimisations.py` puts a local wiki into the optimised state
(idempotent; `--revert` restores, `--status` reports).

## Measuring locally

Bring the wiki up with the measurement overlay, which sets both variables:

```bash
docker compose -f infra/local-wiki/docker-compose.yml \
               -f infra/local-wiki/docker-compose.measure.yml up -d
```

`MW_TRACE_SQL` writes `/tmp/mw-sql.log` inside the container. **The container's
entrypoint creates that file as root, and Apache runs as `www-data`, so web
requests log nothing until it is made writable** — an empty delta looks exactly
like "this page issues no SQL":

```bash
docker exec local-wiki-mediawiki-1 sh -c 'rm -f /tmp/mw-sql.log; \
  touch /tmp/mw-sql.log; chmod 666 /tmp/mw-sql.log'
```

**`MW_DISABLE_FOREIGN_IMAGES` is not optional for measurement.** Without it the
local wiki resolves every image from production over HTTP mid-render, so page
timings measure network latency to prod — the same six pages took 15.1s / 3.5s /
2.3s / 5.4s / 4.2s / 11.8s with it off and 1.7s / 2.4s / 1.8s / 4.4s / 4.2s /
3.3s with it on — and image-heavy pages blow PHP's 30-second limit and return
HTTP 500.

Drop the overlay when you are done: it is not the default because the foreign
repo is a real local-wiki feature, and
`infra/local-wiki/tests/test_foreign_image_repo.py` fails while it is on.

Heavy pages also need more than PHP's default 30 s locally; that limit is raised
in `LocalSettings.env.local.php`.

## Measured on the local wiki

Football 2021/22–2024/25 seeded: 222 games, 15,540 events. **Every page type in
the benchmark**, not just the ones that improved:

| page | SQL | nodes | cache TTL | render |
|---|---|---|---|---|
| **ערן זהבי** (player) | 2,457 → 1,248 −49% | 19,152 → 5,833 −70% | 3600 → 86400 | 2.67s → **1.30s** −51% |
| **עונת 2021/22** (season) | 4,614 → 2,356 −49% | 74,755 → 43,929 −41% | 3600 → 86400 | 4.56s → **3.43s** −25% |
| **פורטל שחקנים** (portal) | 1,261 → 1,034 −18% | 21,527 → 15,106 −30% | 3600 → 86400 | 1.61s → 1.57s −3% |
| פורטל אנשי צוות | 385 → 385 | 609 → 610 | **3600 → 86400** | — |
| משחק (game page) | 938 → 939 | 17,957 → 17,963 | already 86400 | **untouched** |
| עמוד ראשי (home) | 281 → 282 | 3 → 3 | already 86400 | empty locally |
| פורטל מדים / מפעלים / מתקנים | unchanged | unchanged | already 86400 | already cheap |

**Three pages materially improved; four gained the cache TTL fix; two are still
untouched.** The game page is the notable gap — it is the most numerous page
type on the wiki (8,367 pages) and none of this work reaches it, because the
gallery and image-format fixes went into `הצגת משחק`, the row template used in
season *lists*, while the game page itself renders through `קטלוג משחקים`.

That table predates changes 6 and 7, which cut the season and portal pages
further and reach two page types it does not list at all — opponent pages (~500)
and stadium and category pages. See **Where the six records pages ended up**
below for the current numbers.

Verification: 85 statistics on player and season pages identical before/after,
and all 1,080 leaderboard record values on the portal identical.

## The eight changes

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

### 5. Leaderboards: 32 queries → 1, and a non-determinism bug fixed

Leaderboards (`שיאני כיבושים`, `שיאני הופעות`, …) each ran their own grouped
query — 32 per portal render, since the portal transcludes three category pages
each holding four leaderboards across four competition tabs.

`Module:שיאנים` computes all of them from one aggregate shared through
`mw.loadData`. The template is **not** replaced outright: it becomes a
dispatcher, because opponent, stadium and season pages call it with filters the
module does not implement (opponent, stadium, referee, coach, season, result).
Those still route to the original query, preserved as
`…/שיאני כמות אירועי שחקן/שליפה מלאה`.

This also fixed a real bug. The template sorted by `COUNT(*)` with no
tiebreak, so tied players appeared in arbitrary order — **three renders of the
same page gave three different top-10 lists.** The module breaks ties by name.
Record values are identical; only which tied player takes the last slot changed,
and it is now stable.

### 6. A whole records block per query, not per tab

Item 5 replaced one leaderboard query with a shared one. It did not touch what
*asks* for those leaderboards, and that turned out to be where the queries were.

Each of the four display templates (`שיאני הופעות`, `כיבושים`, `בישולים`,
`מוצהבים`) holds four competition tabs, and each tab ran **two** queries: the
top-10 table, and then the identical query again with `|הצגה=list |הגבלה=2000`
purely to print "34 כובשים שונים" in the tab header. Eight per template, and a
records page transcludes all four — **32**.

`Module:שיאנים|section` renders an entire display template, four tabs and their
four counts, from one query. The page's own filter goes straight to that query,
so this works on the pages that item 5's dispatcher had to route past:

| page | queries |
|---|---|
| stadium / opponent / season / referee | 32 → **4** |
| portal / category (no filter) | 32 → **1** (the four share `mw.loadData`) |

Measured on the local wiki, values verified identical on all six:

| page | SQL | nodes | render |
|---|---|---|---|
| קטגוריה:שחקנים | 4,567 → 2,291 −50% | 12,427 → 1,875 −85% | 2.40s → **0.72s** |
| אצטדיון בלומפילד | 7,996 → 5,871 −27% | 14,608 → 3,256 −78% | 1.78s → 1.55s |
| פורטל שחקנים | 11,042 → 8,688 −21% | 19,714 → 9,162 −54% | 1.69s → 1.14s |
| בית"ר ירושלים | 11,770 → 9,973 −15% | 20,786 → 11,396 −45% | 4.15s → 3.82s |
| מכבי חיפה | 13,504 → 12,219 −10% | 22,467 → 13,543 −40% | 4.36s → 4.01s |
| עונת 2021/22 | 18,620 → 16,394 −12% | 40,793 → 30,420 −25% | 3.27s → 3.05s |

The opponent pages barely move because their remaining cost is a different
cluster (`כמות נתוני משחק`), not the records block.

Two things this had to get right:

- **The signed `<shtml>` tab header is copied through byte-for-byte.** Its hash
  covers its exact content. Only the *contents* of the tabs moved into Lua; the
  radio inputs and labels that need raw HTML stayed in wikitext.
- **Quote characters are stored inconsistently in Cargo, and that is load
  bearing.** `Opponent`, `Stadium` and `Competition` are stored stripped
  (`ביתר ירושלים`), while `PlayerName` and `Refs` keep the apostrophe
  (`אביעזר ז'נו`). The original template encoded this by wrapping *some* of its
  lists in `תבנית:המרות/שם ללא גרש וגרשיים` and not others. Missing it emptied
  every records table on `בית"ר ירושלים` — caught because the row count went to
  zero, not because anything errored.

The `עוד` link under each table was generated by the Cargo query itself, so the
module rebuilds it from the same conditions; all 16 survive on a stadium page.

### 7. The general-numbers block: 32 queries → 2

Opponent pages and season pages show the same block — four competition tabs,
nine rows each (games, wins, draws, losses, goals, conceded, clean sheets,
yellows, reds) — and both built it the same way: six `כמות נתוני משחק` calls
and two `כמות אירועי שחקן` calls per tab. **32 per page.**

`Module:סטטיסטיקה משחקים|numbersBlock` renders all four tabs from one games
query and one cards query. All 146 stat rows verified identical across four
pages.

This also fixed a copy-paste bug in **both** templates: the fourth tab's content
div carried `id="tab3-content"`, duplicating the third, so the CSS rule for
`#tab4-content` matched nothing and the international tab rendered blank.

One formatting trap: the wikitext computed percentages as
`{{סטטיסטיקה/אחוזים}}` (`#expr … round 2`) and then passed the result through
`{{#number_format}}`. That is **two** roundings, and a single Lua `%.0f` gives a
different answer at the boundary — so the module rounds to 2 places first and
then to the displayed precision, both half-up (`math.floor(x * f + 0.5) / f`;
Lua's own `%.2f` rounds half-to-even, so `0.125` becomes `0.12` where MediaWiki
shows `0.13`).

### Where the six records pages ended up

Against the original templates, with every change above applied:

| page | render | SQL | nodes |
|---|---|---|---|
| מכבי חיפה (opponent) | 4.36s → **1.03s** −76% | 13,504 → 8,991 | 22,467 → 9,140 |
| בית"ר ירושלים (opponent) | 4.15s → **0.98s** −76% | 11,770 → 6,640 | 20,786 → 6,994 |
| קטגוריה:שחקנים | 2.40s → **0.66s** −73% | 4,567 → 2,291 | 12,427 → 1,875 |
| אצטדיון בלומפילד | 1.78s → **0.94s** −47% | 7,996 → 6,019 | 14,608 → 3,650 |
| פורטל שחקנים | 1.69s → **1.16s** −31% | 11,042 → 8,553 | 19,714 → 9,162 |
| עונת 2021/22 | 3.27s → **2.40s** −27% | 18,620 → 16,289 | 40,793 → 29,284 |

### 8. Parser cache TTL: 3600 → 86400 on every page

Two separate causes, both fixed:

- **`{{#dpl:}}`** calls `updateCacheExpiry(cacheperiod ?? 3600)`. There is no
  global setting in any DPL3 version (checked against `master`), so
  `|cacheperiod=86400` was added to all 28 call sites — including **category
  pages** (namespace 14), which portals transclude. Scanning only templates and
  articles left `פורטל אנשי צוות` capped at 3600 via
  `{{:קטגוריה: אנשי צוות כדורגל}}`.
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
