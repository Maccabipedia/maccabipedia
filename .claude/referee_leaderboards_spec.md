# Referee pages: assistant-referee leaderboards on one query, as tabbers

Status: SPEC v2 - v1 reviewed adversarially (9 findings, 2 blockers), every
finding addressed below and marked [v2]. Local only; nothing reaches production
without Roee's ack.

## 1. What and why

`תבנית:שופט כדורגל` is transcluded by 700 pages, all of them referee pages
(namespace 3010, measured). It computes a profile from two counts: main-referee
games and assistant games. Profile 1 (main only) never renders the assistant
section; profile 2 (no main-referee games - including referees with ZERO
assistant games) renders only it; profile 3 renders both inside a native
TabberNeue tabber (שופט ראשי / עוזר שופט), passing `הסתר הערת סוג עמוד=כן`
to the assistant section. The assistant boxes are on 350 pages (measured,
embeddedin of the box template). [v2]

The assistant section renders four leaderboard boxes - שיאני הופעות /
כיבושים / בישולים / מוצהבים - each a `<shtml>` radio strip with four tabs
(משחקים רשמיים, ליגה, גביע, אירופה).

Two problems, one change:

1. **A live bug.** Each strip's labels point at `fb-<kind>-tab1..4`, but its
   radio inputs are `fb-<kind>-second-tab1..4`. Clicking an assistant-referee
   tab switches the MAIN-referee strip of the same kind (when both sections are
   on the page) or nothing at all.
2. **Cost.** Each box runs 8 Cargo queries: 4 leaderboards, plus 4 "distinct
   players" counts that re-run the same grouped query with `הצגה=list
   |הגבלה=2000` and count comma-separated items. 32 queries for the section's
   leaderboards.

Measured on production (uncached preview renders, fixed API cost 110 ms):

| what | p50 | p95 |
|---|---|---|
| `{{שופט כדורגל}}`, full page, 20 random referees | 1,092 ms | 3,677 ms |
| assistant section, 4 leaderboard boxes (5 referees, medians, fixed cost removed) | ~680 ms together | |
| same section: balance ~180, season stats ~80, wins+losses ~50 ms | | |

A first measurement of 3.5 s was WRONG: the section reads the referee name from
a page variable (`{{#var: שם להצגה}}`) set only by `תבנית:שופט כדורגל`, so
rendering the section alone ran every query with an empty name. Every
measurement here renders through `תבנית:שופט כדורגל`, or passes the name the
way the page does.

## 2. Scope

In:
- A leaderboard primitive in `Module:FootballQueries` (the one the module left
  unwritten on purpose: "It gets written when the leaderboards are").
- One `#invoke` that renders all four assistant-referee boxes from ONE query,
  each as a `<tabber>` (`.tabber-converted`), replacing the four
  `שופט כדורגל/הצגת שיאני …/עוזר שופט` calls inside
  `תבנית:שופט כדורגל/עוזר שופט`.
- The bug disappears with the radio inputs.

Out (measured, listed, not done here):
- The main-referee boxes. Their templates (`סטטיסטיקה/תצוגה/שחקנים/שיאני …/עיצוב
  חדש`) are shared with 990 pages (stadiums, opponents, coaches…); converting
  them is a separate, larger change that this primitive enables.
- Balance / season stats / biggest wins+losses (~310 ms together).
- `Module:שיאנים` and the `…/שליפה מלאה` dispatcher: an abandoned prototype from
  closed PRs #188/#189, present in the LOCAL wiki DB only. Not reused, not
  deployed. Its lesson is kept: leaderboards need a deterministic tiebreak.

## 3. Current behaviour to reproduce (production text, not local)

The local wiki holds the prototype's version of the leaderboard query template;
production holds the original `#cargo_query`. Parity is against PRODUCTION.

Per box, per tab (category ∈ רשמי, ליגה, גביע, בינלאומי):

- Query: tables `Football_Games, Games_Events, Games_Referees, Competitions`,
  joined on `_pageID` and `Competition=OriginalName`; where `Team=1 AND
  Competitions.Official=1`, the category flag, `EventType IN (<kind types>)`,
  `Games_Referees.AssistantReferees HOLDS "<name>"`; fields `PlayerName,
  COUNT(*)`; `group by PlayerName`; `order by COUNT(*) DESC`; limit 10;
  `format=template`, template `סטטיסטיקות/הצגת שיאנים/הצגת שחקן/כדורגל`
  (positional 1=name, 2=count); `more results text=עוד`.
- Event filters per kind, read from the production templates [v2]:
  הופעות `EventType IN (1, 5)`; כיבושים `EventType IN (3)` AND `SubType != 33`
  (own goals excluded - a COLUMN condition, never the shared WHERE, or it would
  drop appearances with subtype 33 too); בישולים `4`; מוצהבים `7`. `SubType !=
  33` also excludes NULL subtypes in SQL; inside `CASE WHEN` it behaves the same,
  so parity holds. [impl] Correction found by the local comparison: מוצהבים is
  `EventType IN (7)` AND `SubType IN (71)` - yellow cards only. The first
  implementation counted every card and failed on 20 of 33 local referees.
- Heading: `<label> (<N> <noun>)`, label ∈ משחקים רשמיים, ליגה, גביע המדינה,
  אירופה. Noun per kind [v2]: הופעות `מופיעים שונים`, כיבושים `כובשים שונים`,
  בישולים and מוצהבים `שחקנים שונים`. N = number of players in that tab: the
  count query is the SAME grouped query with `הצגה=list |הגבלה=2000`, counted by
  splitting on commas (no player name contains a comma: 0 events, measured; no
  blank PlayerName: 0 events, measured).
- Row: display template `סטטיסטיקות/הצגת שיאנים/הצגת שחקן/כדורגל`, positional
  1=name 2=count: `atom-records-list-player-row`, name linked only when the page
  exists (`#קיים`), count through `#number_format`.
- "עוד" [v2]: an external link (`target=_blank`, `rel="nofollow noreferrer
  noopener"`) to `מיוחד:ViewData` carrying the whole query with `offset=10
  &limit=100`, i.e. rows 11-110. Cargo emits it when the returned row count
  EQUALS the limit (inferred from Cargo; confirmed empirically in §5), so a tab
  with exactly 10 players links to an empty page.
- Tab with 0 players: heading `(0 …)`, no rows, no link (measured: אירופה on a
  busy assistant referee).
- Box markup [v2]: `records-list-tabs-container` `id="שיאנים"` (duplicate on
  every box) > `title` div > `list` div > `slim-tabs` > radios + `ul` +
  `content#res-tabs-content` > `tabN-content` > `tab-header` + rows + link.

## 4. Design

### 4.1 Primitive: `FootballQueries.leaderboard(shared, columns, options)`

One grouped query for any number of leaderboards that share their WHERE:

- `shared`: Hebrew filters for the WHERE (here `עוזר שופט`; HOLDS is allowed
  only in the WHERE - the module already refuses it inside a cell).
- `columns`: `{ name, grain='event', filters={מספר אירוע, ללא תת אירוע,
  קטגוריית מפעל …} }`, compiled by the SAME conditional-aggregate builder
  `aggregate` uses (`SUM(CASE WHEN <cell> THEN 1 ELSE 0 END)` for event grain -
  v1 misnamed it `COUNT(CASE…)`) [v2].
- Grain: row counting over the same joins as today, so any fan-out today is
  reproduced, not "fixed". Measured: `Games_Referees` has 1,471 rows for 1,471
  games and `Competitions.OriginalName` has no duplicates, so there is none.
  [v2]
- SQL: `GROUP BY Games_Events.PlayerName`, no ORDER BY, no LIMIT in the SQL
  except the existing `maxLimit` guard (5,000 groups). The WHERE also carries
  the union of the columns' event types, so rows outside every column are never
  grouped. A result that hits the limit raises (existing truncation guard).
- Lua per column: drop zero counts, sort by count DESC then **PlayerName ASC**,
  keep the top N; `distinct` = number of non-zero players.

Group key column and join set come from `Fields` (a `groupBy` role), not
hard-coded - the next leaderboard (coaches, seasons) changes data, not code.

### 4.2 Rendering: `Module:FootballStatsBlock` gains `leaderboards`

[v2] v1 would not have run: `blockOf` refuses every direct argument but
`בלוק`, and reading the parent's parameters would pass `שם להצגה` (not a
filter) and `הסתר הערת סוג עמוד` (unsupported filter) into the query layer.

`{{#invoke:FootballStatsBlock|leaderboards|בלוק=referee-assistant|שופט={{#var: שם להצגה}}}}`

- A new entry point with its OWN argument contract: `בלוק` plus the block's
  declared entity argument (`שופט` here), and nothing else - any other direct
  argument raises. It does NOT read the parent's parameters.
- The block maps the entity to the filter (`עוזר שופט` ← `שופט`).
- An empty or whitespace entity RAISES. The query layer treats an empty filter
  as absent, so an empty name would silently drop the HOLDS filter and rank
  every player in every game - the exact failure that produced the wrong 3.5 s
  measurement.

Block data in `Module:FootballStatsBlocks` (`referee-assistant`): entity name
and the filter it maps to, four boxes (title, noun, per-kind filters), the tab
strip (labels, headings, categories) reusing `tabStrip`, the row limit (10),
the display template name, and the "עוד" link parameters.

Per box it emits the wrapper and title unchanged, then `<div
class="tabber-converted">` + `frame:extensionTag('tabber', …)`; each panel is
the heading plus rows rendered through `frame:expandTemplate` on the SAME
display template (so `#קיים` and `#number_format` stay byte-identical), plus
the "עוד" link when the column has more than 10 players.

Tab labels stay plain text (anchors, icons). All four use existing icon rules
(`משחקים_רשמיים` circle, `ליגה`, `גביע`, `אירופה` euro) - no CSS change needed
beyond what #194 shipped. Four tabbers on the page get distinct ids from
TabberNeue's index suffix.

### 4.3 The "עוד" link [v2]

Same element and attributes as today (external link, `target=_blank`, same
`rel`, text `עוד`), pointing at `מיוחד:ViewData` with a query that returns the
same rows 11-110: the per-column query (shared WHERE + that column's
conditions, same tables/joins/template, `group_by PlayerName`, `order_by
COUNT(*) DESC, Games_Events.PlayerName`), `offset=10&limit=100`. The URL text
differs from today's (it encodes a different WHERE); the destination's rows are
compared, not the URL.

Shown when the column has MORE than 10 players - departure 4 below: today's
`count == limit` rule links a tab with exactly 10 players to an empty page.

### 4.4 Template change

`תבנית:שופט כדורגל/עוזר שופט`: the four `הצגת שיאני …/עוזר שופט` lines become the
single invoke above. The balance line and the rest stay. The four wrapper
templates stay (unused by this page) until a later cleanup.

Referees with 0 assistant games still render the section today (profile 2);
the invoke runs its one query and renders four `(0 …)` boxes, as today. Skipping
the query using the page's existing `כמות משחקים כעוזר שופט` count is possible but
changes nothing visible and is not done here. [v2]

### 4.5 Deliberate departures (re-baselines, recorded as such)

1. Ties at the limit: today `ORDER BY COUNT(*) DESC` alone, so tied players come
   back in any order and the 10th row can change between renders (the batch
   harness already marks such strips UNSTABLE). New: name ASC tiebreak.
2. Distinct count: today counts comma-separated items, so a name with a comma
   would count twice. New: counts players. Measured: no such name exists, so no
   visible difference today.
3. Tab click bug: fixed by construction.
4. "עוד" on a tab with exactly 10 players: today a link to an empty page; new:
   no link. [v2]

## 5. Verification (all local or read-only against production)

1. **Stub tests + mutation gate** (`tests/test_*.lua`, `mutate.py`): SQL shape
   (one query, HOLDS in WHERE, event-type union, group key, no ORDER/LIMIT),
   sort/tiebreak/top-N/distinct in Lua, zero-player tab, >10 players (עוד),
   truncation guard, block data typos raise. Every new guard has a killing
   mutation; 0 survivors.
2. **Production parity of the NUMBERS, read-only** (new
   `compare_prod_referee_leaderboards.py`): Lua prints the one query; Python runs
   it through `cargoquery`; the SAME Lua ranking code (sort, tiebreak, top-10,
   distinct, link rule) runs on those rows under the stub; the result is
   compared with production's own render of the old boxes (`action=parse`,
   headings N, names, counts, presence of "עוד"). Sample, required cases named
   [v2]: the 3 busiest assistant referees, 20 random, at least one profile-2
   referee with 0 assistant games, at least one profile-3 (both sections), a
   tab with exactly 10 and one with 11+ players, a goals column where subtype
   33 exists. Allowed differences, checked mechanically: departure 1 (same
   counts sequence; same set of players above the boundary count) and departure
   4. Anything else fails. A selftest crosses two referees and must fail.
   What this does NOT prove - the real `#invoke`, its argument handling and
   `mw.ext.cargo.query` - is §5.3's job; this check is not allowed to stand in
   for it. [v2]
3. **Local wiki end to end, through the real invoke** [v2]: seed the production
   versions of the WHOLE chain - `שופט כדורגל`, `/עוזר שופט`, `/שופט ראשי`, the
   balance and other section templates, `תוכן עניינים דינאמי`,
   `סטטיסטיקה/שליפות/מתקדמות/כמות נתוני משחק` (it decides the profile), the four
   boxes, the leaderboard query template, `כמות רשומות`, the display template -
   plus referee pages chosen from the LOCAL data: one profile 2 and one profile
   3. Before any comparison, assert the page actually rendered what it should:
   profile 3 page has >= 5 tabbers (outer + 4 boxes; 4 more if the main-referee
   boxes are also converted later) and both sections; profile 2 has 4 and no
   outer tabber. A zero here fails the run instead of letting "anchors unique"
   pass over nothing. Then: panel text old vs new through the real invoke,
   `compare_tab_states.py` and the tab browser tests including the NESTED case
   (fade, hover, no page jump, unique anchors, the outer tab still switches and
   the inner ones switch only their own box - the bug's regression test).
4. **Pixel + interaction**: screenshots per tab at 1280 and 400 against the old
   boxes (after the tab-bug fix the old boxes cannot be clicked correctly - the
   comparison clicks the old strip's own inputs).
5. **Performance, production-equivalent**: the 32 queries become 1; measured
   locally on the seeded page (before/after), and the production estimate
   stated as an estimate until deployed.

## 6. Risks

- Join fan-out: none today (measured, §4.1); if it appears later it is
  reproduced, as today's COUNT(*) would include it. [v2]
- `Competitions` join and `Official=1` in every tab must survive into the WHERE.
- Nested tabbers: TabberNeue's panel sizing/observer in a nested carousel.
- Name encoding: player names with quotes (the stadium double-encoding lesson)
  must match the old output.
