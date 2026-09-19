# Season pages: the four leaderboard boxes on one query, as tabbers

Status: SPEC v1 - not reviewed yet. Local only; nothing reaches production
without Roee's ack. Sibling of `.claude/referee_leaderboards_spec.md`, whose
primitive and entry point this reuses; read that first.

## 1. What and why

`תבנית:עונת כדורגל` is transcluded by the 107 football season pages
(`קטגוריה:עונות כדורגל`, `עונת 1921` .. `עונת 2026/27`, measured 2026-09-18).
Its `שיאנים` section is four boxes - שיאני הופעות / כיבושים / בישולים /
מוצהבים - each through a season-only wrapper `עונת כדורגל/הצגת שיאני …`,
which calls the SHARED `סטטיסטיקה/תצוגה/שחקנים/שיאני …/עיצוב חדש` with
`עונה=` only. Each shared box is an `<shtml>` radio strip of four tabs, and
each tab runs 2 queries (the leaderboard, plus the same grouped query with
`הצגה=list |הגבלה=2000` counted by `כמות רשומות`): **32 Cargo queries per
season page** for this section.

Why seasons first (chosen 2026-09-18 over stadiums, main referees, basketball,
volleyball):
- Season-only wrappers: the change is confined to `תבנית:עונת כדורגל`. The
  shared `עיצוב חדש` templates (990 callers: stadiums, opponents, coaches,
  referees) are NOT touched.
- `עונה` is a plain text filter (`Football_Games.Season`), no alias lookup. The
  stadium blocker - 11 `Stadiums` rows with entity-encoded names, refused by
  `expandAliases` - cannot occur.
- The CSS is already there: `records-list.less` styles rows inside
  `.tabber-converted`; `tabber-converted.less` has icons for every label used
  here (`גביע` trophy, `בינלאומי` globe - chosen 2026-09-17).

## 2. Scope

In:
- A `season` block in `Module:FootballStatsBlocks`, rendered by the existing
  `leaderboards` entry point: one query, four boxes, each a `<tabber>`.
- The one code change that needs: the box wrapper markup becomes block data
  (§4.1).
- `תבנית:עונת כדורגל`: the four `עונת כדורגל/הצגת שיאני …` lines become one
  invoke; the parent `players-records-container id="שיאנים"` grid stays.

Out (listed, not done here):
- The shared `עיצוב חדש` templates and their other 883 callers.
- The season page's other blocks: games list by competition, squad, staff,
  captains, the uniforms `#cargo_query`, and `הצגת מספרים עונתיים` (already
  conditional aggregates).
- Basketball/volleyball season pages.
- Deleting the four season wrappers (left in place, unused, for a later
  cleanup - same as the referee wrappers).

## 3. Current behaviour to reproduce (read from production 2026-09-18)

Query per box and tab (`שיאני כמות אירועי שחקן/עיצוב חדש`): tables
`Football_Games, Games_Events, Games_Referees, Competitions`; where `Team=1
AND Competitions.Official = 1` (every tab, so `רשמי` is SHARED as in the
referee block), the tab's category flag, `EventType IN (...)`,
`Football_Games.Season = "<season>"`; group by `Games_Events.PlayerName`;
order `COUNT(*) DESC`; limit 10; row template
`סטטיסטיקות/הצגת שיאנים/הצגת שחקן/כדורגל`; more results text `עוד`.

| box | title | noun | filters |
|---|---|---|---|
| appearances | שיאני הופעות | מופיעים שונים | `מספר אירוע=1, 5` |
| goals | שיאני כיבושים | כובשים שונים | `3`, `ללא תת אירוע=33` |
| assists | שיאני בישולים | שחקנים שונים | `4` |
| cards | **שיאני מוצהבים** | שחקנים שונים | `7`, `תת אירוע=71` |

Nouns and filters equal the `referee-assistant` block. Differences from it:

| | referee-assistant | season |
|---|---|---|
| cards title | שיאני צהובים | שיאני מוצהבים |
| tab 4 label / heading | אירופה / אירופה | בינלאומי / בינלאומי |
| box wrapper | `records-list-tabs-container id="שיאנים"` | `records-list-tabs-container` (id is on the parent) |
| entity -> filter | `שופט` -> `עוזר שופט` (HOLDS) | `עונה` -> `עונה` (text) |

Tabs 1-3 are identical: `משחקים רשמיים`, `ליגה`, `גביע` (heading `גביע
המדינה`). Titles of the goals and assists wrappers are read again from
production during implementation, not assumed from their page names.

## 4. Design

### 4.1 `season` block in `Module:FootballStatsBlocks`

A sibling of `referee-assistant`, same shape, rendered by the same
`leaderboards` entry point - no new Lua entry point. Differs where production
differs (§3): `entity = 'עונה'`, `entityFilter = 'עונה'` (a plain text filter,
`Football_Games.Season = "…"` - not HOLDS, so `leaderboard()`'s WHERE never
runs the alias-expansion path that refuses stadiums' entity-encoded names);
tab 4 `{ category = 'בינלאומי', label = 'בינלאומי', heading = 'בינלאומי' }`;
cards box titled `שיאני מוצהבים`.

### 4.2 `boxOpen`: the box wrapper becomes block data

The renderer (`leaderboaders()` in `Module:FootballStatsBlock`) hard-coded the
box wrapper as `<div class="records-list-tabs-container" id="שיאנים">`. The
season page's own wrapper carries no id - the parent
`players-records-container` div has it instead - so the wrapper moves into
each block's declaration as `boxOpen`. `referee-assistant` declares today's
exact string (byte-identical, verified by a locked-in stub test, §5); `season`
declares the id-less form. No default value: a block that omits `boxOpen`
fails the moment it tries to render, because `table.concat` cannot concatenate
a `nil` - this was deliberately left as a plain Lua error rather than a
friendlier guarded one, because no guard here can be killed by a mutation:
every real declared block must have `boxOpen` to work in production at all,
so there is no way to exercise "a real block without it" without breaking the
wiki. A speculative guard that cannot be tested is dead code (project rule).

### 4.3 Template change

`תבנית:עונת כדורגל`: the `<div class="players-records-container" id="שיאנים">`
block's four `עונת כדורגל/הצגת שיאני …` lines become the single invoke
`{{#invoke:FootballStatsBlock|leaderboards|בלוק=season|עונה={{#var: עונה
להצגה}}}}`. The div itself, its id, and everything outside it are untouched.
The four season wrapper templates stay in place, unused, until a later
cleanup (same as the referee wrappers).

### 4.4 Deliberate departures (re-baselines, recorded as such)

Identical to the referee conversion (§4.5 of its spec), because they are the
same primitive: (1) ties at the limit get a name-ASC tiebreak, where today's
`ORDER BY COUNT(*) DESC` alone leaves the 10th row unstable between renders;
(2) the distinct-player count is counted in Lua from the ranked rows rather
than by re-running a second query and splitting on commas (no season's
players include a comma in their name - not separately re-measured here,
inherited from the referee work's measurement of the same column); (4) "עוד"
on a tab with exactly ten players: today a link to an empty page, new: no
link.

Visual, not a data departure: tab 4 shows the tabber's globe icon
(`tabber-converted.less`, `.tab-icon(~"בינלאומי"; "\f0ac")`, chosen
2026-09-17 site-wide) where the old strip showed a euro sign for the same tab
- both already read בינלאומי, so this is a like-for-like icon swap, not a new
inconsistency. Recorded here so the screenshot review does not flag it as a
regression.

**Also visual, and found only by Roee using the page (2026-09-19)**: the old
boxes were `<shtml>` strips, so clicking a tab did nothing to the URL. The new
ones are TabberNeue and `$wgTabberNeueUpdateLocationOnTabChange = true`
(`LocalSettings.shared.php:380`), so a tab click now rewrites the location
hash - and reloading, bookmarking or sharing that URL opens the page already
scrolled to the leaderboards. Measured on the URL he pasted: `scrollY` 1450 on
load, putting `מספרים עונתיים` 1343 px above the viewport. He read that as the
block having disappeared, which is exactly how a reader would read it.

Not introduced by this conversion - it is the standing site setting meeting a
newly-converted page, and referee pages have behaved this way since #195 - but
it is new **for season pages**, whose above-the-fold content (seasonal numbers,
achievements, squad, league table) is a lot more than a referee page's. Three
options, Roee's call, unresolved at time of writing: leave it (consistent with
referee pages, and deep-linking a tab has its own value); turn the setting off
site-wide (kills referee deep links too); or keep the hash selecting the tab
but suppress the scroll, which is a skin change and therefore a `skin.json`
version bump plus `deploy-skin`.

## 5. Verification (all local or read-only against production)

1. **Stub tests + mutation gate** (`tests/test_leaderboard.lua`, `mutate.py`):
   the season query's WHERE carries `Football_Games.Season = "…"` and never
   `HOLDS`; the box wrapper has no id; tab 4 reads בינלאומי on both label and
   heading; an empty season raises; only `בלוק` and `עונה` are accepted; each
   box counts exactly its template's events (own goals excluded, yellow cards
   only); the referee-assistant wrapper still carries `id="שיאנים"`
   unchanged by making the wrapper block data. Every new/changed line in
   `Module_FootballStatsBlocks.lua` has a mutation with a season-specific
   variant, made unique against its referee-assistant twin by widening the
   matched context (the two blocks share several identical lines) - a broken
   (non-unique) mutation pattern is treated as failing, not skipped. 138
   mutations, 0 survivors (grew from the referee work's 98+ as this block was
   added).
2. **Production parity of the NUMBERS, read-only**
   (`compare_season_leaderboards.py`): unlike the referee comparison, this
   renders ONLY the `שיאנים` section as raw wikitext - not the whole page
   through `{{עונת כדורגל}}` - because a season page carries other `<shtml>`
   strips above (seasonal numbers) and below (the games list) that would
   break the referee harness's box/tab extraction if reused unmodified (found
   by adversarial review before this ran once, not after). The OLD and NEW
   section texts are extracted from the LIVE template by
   `convert_season_section.section_texts`, never hand-copied, so they track
   production rather than drifting from it. Same allowed differences as the
   referee comparison (§4.4 above). Required cases: every season with local
   data, plus `1921` (a real zero-game season) and a season that does not
   exist at all (same zero-row shape, no page needed since the query is
   parameterised directly). A selftest crosses two seasons and must FAIL.
3. **Local wiki end to end, through the real invoke**
   (`convert_season_section.py --local`, then `--apply` only after §5.2 is
   green): writes the candidate whole-template body to
   `תבנית:עונת כדורגל/ארגז חול לידרבורדים` first, so the real season pages
   are rendered through the genuine template chain (navigation, numbers,
   league table, games list) with only the `שיאנים` section swapped, and
   opened for at least one season with data and `1921`.
4. **Pixel + interaction** (done, local, 2026-09-18): `screenshot_pair.py`
   (given a `--width`/`--height` option - it had none) against
   `תבנית:עונת כדורגל` vs the sandbox candidate, `עונה להצגה=2021/22`, at
   1280, 1000 and 400 px. At 1280/1000 the section holds its 4-column grid
   (`@viewport-regular` up, `pages/football/season-details.less` - narrower
   than the referee boxes ever ran, a condition that work never exercised);
   at 400 it stacks to one column, identical page height (12,070 px) both
   sides. `compare_shots.py --region` found a real, non-icon difference
   `pillow` alone couldn't explain away: three tied players (46 appearances
   each) in a different ORDER, not different rows. Not a bug - it is
   departure 1 (§6 below) made visible for the first time: NEW is strict
   Hebrew alphabetical (א < ג < ס), OLD is unspecified MySQL tie order. Every
   screenshot was opened and looked at, not just diffed, per the standing
   lesson that a diff tool answers "how much changed", never "is this fine."
   `compare_tab_states.py` (hover/pressed/focus/fixed-vs-inactive/fade/panel
   geometry): **0 differing (state, property) pairs.**
   `check_anchor_collisions.py`: 16 unique panel ids, 0 collisions.
5. **Performance** (measured, local, 2026-09-18): section render time,
   4 local seasons × 8 renders each (`action=parse`, same host running
   everything - not comparable to a production estimate, only to itself):

   | | p50 | p95 | mean |
   |---|---|---|---|
   | OLD (32 queries) | 737 ms | 788 ms | 741 ms |
   | NEW (1 query) | **388 ms** | **426 ms** | **390 ms** |

   Re-measured 2026-09-19 after the fixture restore (§7): the first run of
   this table was taken while the fixture still carried a Lua prototype of
   `שיאני כמות אירועי שחקן/עיצוב חדש`, which sits in the OLD chain, so the
   OLD side had not been production's wikitext. It was worth re-running on
   the expectation that the numbers would move - they did not (they were
   746/835/751 and 403/449/408), so the prototype happened to cost about the
   same. The parity comparison was contaminated by that template; this
   measurement was not. Both sides interleaved per iteration so host drift
   hits them equally.

   Same shape as the referee conversion's own local measurement (598→293 ms,
   §5b there); the season section costs more before AND after, consistent
   with scanning a whole season's games rather than one referee's. Production
   is still only an estimate until measured after the real switch (§5.2 of
   the referee spec: production and local numbers are never assumed to
   transfer 1:1).

   **The section number in the context of the whole page** (measured
   2026-09-18, asked for directly - checked rather than assumed): rendering
   the REAL `{{עונת כדורגל}}` fresh (not `page=` + purge, which looked
   accepted but still returned a suspiciously-cached 49ms - `text=` never
   touches ParserCache, so this is the trustworthy number) costs **p50 10.3s,
   p95 14.3s** old, **p50 9.3s, p95 11.1s** new - a real ~1s saving, but the
   page itself is dominated by content this conversion does not touch.
   MediaWiki's own limit report for one render: 2.2s CPU time against 11.1s
   real time - most of the gap is I/O wait, not computation - across 657
   expensive-parser-function calls and 536 ExtLoops for the WHOLE page, of
   which this section is 32 (old) or 1 (new). `תבנית:פרק` (wrapping the
   games list) alone accounts for ~700ms. The season page is not fast after
   this change, and was never scoped to become fast - only the leaderboard
   section's own 32→1 is this work's actual result, and the whole-page
   number here is local-Docker per-query round-trip overhead stacked across
   hundreds of unrelated calls, not something to read as a production
   estimate for anything but the section itself.

## 6. Risks

- `boxOpen` moved live, hardcoded, behaviour into data for the
  ALREADY-SHIPPED referee-assistant block. Gate before publishing: render the
  referee section uncached (`action=parse text=…`, not a cached page parse -
  the deploy purges only module pages, so a cached-page diff could compare
  nothing) for 3 referees before and after, byte-diff the
  `records-list-tabs-container` fragment; any difference is a rollback.
- Join fan-out: none for `Games_Referees` on season data either (no game has
  2+ rows, measured on production; Cargo's join is LEFT, so games with none
  are kept either way) - same conclusion as the referee spec, re-verified
  for this data, not assumed to transfer.
- Name encoding: player names with quotes must match the old output - `עונה`
  itself carries no such risk (every season value is digits and `/`,
  measured), unlike stadium names.
- Five production seasons render zero games in this section
  (1921/1923/1924/1937/38/1943): the boxes must show four `(0 …)` panels with
  no rows and no "עוד" link, not an error and not an empty section.

## 7. What actually happened, first local run (2026-09-18)

The first `compare_season_leaderboards.py` run failed all 4 real seasons on
the same symptom: identical rows, identical distinct-player counts, but the
NEW side showed an "עוד" link the OLD side didn't. Not a departure this spec
already allows (departure 4 is the opposite direction - OLD showing a link
NEW doesn't, at exactly 10 players; here OLD showed NONE at 40).

Tracing it (readable end to end, not just the conclusion): the row DATA
matched, so the query itself was right - only the LINK differed. The OLD
side's "עוד" link pointed at `Special:CargoQuery` with space-separated
parameter names (`group by`, `order by`); every other converted block's OLD
side (including this one's own referee-assistant sibling, checked directly)
points at `Special:ViewData` with underscored ones - `viewMoreResultsLink()`
in Cargo's own PHP (read directly, not inferred) hard-codes `ViewData`,
unconditionally. Reconstructing the query by hand, parameter for parameter,
kept producing `ViewData` - the divergence survived removing every filter
difference, adding the real preceding `#vardefine` count queries, and even
pasting the template's exact source as raw top-level text. It only appeared
when transcluding the REAL STORED PAGE. Fetching that page's actual local
wikitext (not production's, which is what every reconstruction above had
been copying) showed why: the local wiki's `שיאני הופעות/עיצוב חדש` and its
three siblings held `{{#invoke:שיאנים|section…}}` - the abandoned
`Module:שיאנים` prototype from the closed `wiki-perf-optimisations` branch
(PRs #188/#189), explicitly documented in
`.claude/referee_leaderboards_spec.md` §2 as "an abandoned prototype …
present only in the local wiki's DB … not reused, not deployed." Its own
Lua-side "more results" link generation is what produced the CargoQuery URL.
`referee-assistant`'s own box calls a DIFFERENT, DEDICATED template
(`.../עוזר שופט/עיצוב חדש`) that prototype never touched - which is why nine
months of referee-comparison runs never surfaced this: the bug was real, but
invisible to every check that didn't route through the shared template
family this conversion is the first to touch.

**Fix**: production's real wikitext for all 4 shared templates was pulled
directly (`action=raw`, not retyped by hand - a retyping mistake is exactly
how the season template's own section boundary was nearly gotten wrong
earlier in this same session) and written to the local wiki, replacing the
prototype body; `resignSecureHtml.php` re-signed the `<shtml>` blocks under
the local dev secret (writing new content strips a page's signature, made
for production's secret anyway); `snapshot-db.sh` re-captured the fixture.
Verified by a **second, fully independent** restore-from-fixture,
redeploy-modules, reconvert, recompare cycle - not just re-running against
the containers already holding the fix - both leaderboard comparisons and
the rest of the CI suite (`compare_rendered_blocks.py`, `smoke_test_local.py`,
`verify_entry_points.py`) green throughout.

One further, genuine (not fixture-related) difference surfaced once the
fixture was correct: the "עוד" link's `tables=` set. The templates' static
`#cargo_query` always lists `Games_Referees` whether a filter uses it or not;
the module only joins tables a filter actually touches, so on season pages
(no `עוזר שופט` filter) it correctly omits it. Confirmed harmless: no game
has 2+ `Games_Referees` rows (§6) and no field of it is ever selected, so
including or omitting it from a LEFT JOIN cannot change which rows the link
returns. `compare_referee_leaderboards.link_query()` now drops
`Games_Referees` from both sides' compared table/join sets specifically when
neither side's WHERE mentions it - which never fires for referee-assistant
(its WHERE always does) and always fires for season, so the existing
33-referee comparison is provably unaffected (re-verified after the change:
still 33/33, still fails its own selftest correctly).

### 7b. The same contamination, eight more templates (2026-09-19)

Fixing the four shared `עיצוב חדש` templates above treated the symptom that
happened to be visible. Roee then reported that a season page's first block
title, `מספרים עונתיים`, was missing - reading it, reasonably, as damage from
this conversion. The template diff showed this branch changed only the four
lines, so the cause was elsewhere: `תבנית:עונת כדורגל/הצגת מספרים עונתיים`
in the fixture called `יחידה:סטטיסטיקה משחקים`, a module that does not exist
locally and that production's copy of that template does not call either.

So the class of bug was audited properly instead of one page at a time: for
every page in the local Template namespace whose wikitext contains `#invoke`,
production's copy was fetched and compared. **Nine** templates invoked a
module locally that production's copy does not - `יחידה:שיאנים`,
`יחידה:סטטיסטיקה משחקים`, `יחידה:סטטיסטיקה שחקן`, `יחידה:המרות`, `יחידה:גיל`.
All nine were restored from production via `maintenance/edit.php` inside the
container, then `resignSecureHtml.php` (2 pages re-signed) and
`purgeParserCache.php --age 0`; the audit then reported a single remaining
divergence, this branch's own `תבנית:עונת כדורגל`.

Why this mattered beyond the missing title: one of the nine,
`תבנית:סטטיסטיקה/שליפות/מתקדמות/שיאני כמות אירועי שחקן/עיצוב חדש`, is in the
OLD chain of **both** `compare_season_leaderboards.py` and
`compare_referee_leaderboards.py`. Every parity run to date - this branch's
and the merged #195's - had therefore been comparing NEW against a prototype
baseline rather than production's wikitext. Re-run after the restore: season
**6 seasons / 581 rows ok**, referee **33 referees / 2313 rows ok** - the
same results, now against the real baseline. Pixel check re-run too: the
section on עונת 2021/22 and עונת 2024/25, same page and viewport, converted
vs production's template, **0 differing pixels of 2,014,848** on both.

Two standing rules come out of this, both now in memory: the fixture must
ship the season template **unconverted** (the harness derives its OLD side
from it, so `--apply` is a demo layered on after `snapshot-db.sh`, never
before), and a comparison harness only ever proves "same as the baseline it
rendered" - nothing in it checks that the baseline is production's.
