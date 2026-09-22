# Wiki Lua modules — Design

**Date:** 2026-09-13
**Status:** awaiting review
**Scope of this spec:** the query layer, plus one display block carried
end-to-end to prove its interface.

The living reference for the delivered code is `.claude/lua_modules.md`.
This document is the design and the decisions behind it; where the two
disagree, the reference describes what exists and this describes what was
agreed.

(Kept in `.claude/` rather than `docs/superpowers/specs/` because that path is
gitignored in this repo, and a design nobody can read is not a design.)

## 1. Problem

MaccabiPedia's football statistics are rendered by 46 display templates under
`קטגוריה:סטטיסטיקה/תצוגה/` calling 20 query templates under
`…/שליפות/`. All 20 `#cargo_query` calls live in the query templates; the
display templates issue none. The layering is already right. Two things are
wrong with it:

**One query per number.** `סיכום אירועים לפי מפעל` calls
`כמות אירועי שחקן` 8 times, and the block above it renders 4 tabs, so 32 Cargo
queries produce one player's events column. The leaderboards are worse: 16
templates × 8 calls = 128 call sites on `שיאני כמות אירועי שחקן`. A player page
issues ~4,200 SQL statements, of which only ~12% are data queries — the cost is
query *count*, and Scribunto keeps no module state between `#invoke` calls, so
the only way to reduce it is for one invoke to render a whole block.

**Every query template re-implements the boundary.** Each carries its own join
graph, quote rules, competition flags and row handling, and they have drifted:

- `קטגוריית מפעל=יתר-רשמיים` filters in `כמות אירועי שחקן` and is **silently
  ignored** by `כמות נתוני משחק`, which returns the unfiltered total.
- Three different SQL escaping strategies across the templates.
- `בית/חוץ` is documented as a missing parameter in the two biggest templates
  while `Football_Games.HomeAway` exists and three siblings implement it.
- The templates carry `[[קטגוריה:אין טיפול בשגיאות]]` on their own pages —
  there is no error handling by design.

A dropped filter does not look like a failure. It looks like a number.

## 2. Decisions

| # | Decision | Consequence |
|---|---|---|
| 0 | **Several low-level primitives, not one signature.** A one-row multi-cell aggregate and a grouped leaderboard are different use cases, as they were in the wikitext templates; each gets its own function on the query module rather than one function growing options | Settles C2: the leaderboard shape does not have to fit through `aggregate`, so freezing that signature now costs nothing |
| 1 | Spec covers the query layer **plus one display vertical** (`סיכום אירועים לפי מפעל`, 32 queries → 1) | The interface meets a real consumer before eight more families are built on it. Each remaining display family gets its own short spec. |
| 2 | **Bug-for-bug parity first**; known bugs fixed later as separate, visible changes | Any diff the harness reports is a regression, needing no human judgement. Costs a deliberate quirk-reproduction register (§7). |
| 3 | **All sports eventually, football now.** The tables differ per sport anyway | Sport facts live in data from day one; the engine carries **no** football literals — base table and table roles come from the schema. |
| 4 | **New modules; migrate call sites; retire the old templates** | Requires a call-site inventory that cannot miss one (§10), and a tripwire before deletion rather than after. |
| 5 | **Byte-identical HTML** for the display block | The harness can diff whole rendered pages, so any difference at all is a defect. The Lua reproduces existing markup including its oddities. |
| 6 | **Local wiki until the vertical is proven**, then one low-traffic page | Nothing reaches production until the query layer and the block are complete and byte-identical locally. Prod-scale parity still needs a read-only shadow check, because the local wiki seeds only football 2021/22–2024/25 (222 games, 15,540 events). |

## 2b. Live callers — measured 2026-09-13, and it re-ranks the work

§1 ranked targets by how often the display templates call the query templates:
fan-out **inside** the template tree. That says nothing about whether anything
calls the display templates at all, and it turns out that **41 of the 72
statistics templates have no callers, including 30 of the 46 display
templates**.

| callers | template | namespaces |
|---|---|---|
| 3,000+ | `סטטיסטיקה/אחוזים` | ns0 1,395 · ns3001 387 · ns3003 620 · ns3010 598 |
| 2,542 | `שליפות/מתקדמות/כמות נתוני משחק` | ns0 1,844 · ns3010 698 |
| 2,127 | `שליפות/מתקדמות/כמות אירועי שחקן` | ns0 1,429 · ns3010 698 |
| 2,057 | `שליפות/כמות רשומות` | ns0 1,344 · ns14 15 · ns3010 698 |
| ~805 each | four player-page query templates | ns0 805 |
| **366 each** | **`תצוגה/ימים/סיכום תוצאות`** and `…/לפי מפעל` | ns0 366 |
| **0** | **`תצוגה/שחקנים/סיכום אירועים`** and `…/לפי מפעל` | — |

**The block this spec carried end-to-end has no callers.** The 32 → 1 merge,
the byte-identical comparison and the 650 → 149 ms are all real, and they are
real on a block nothing renders. `תבנית:פרופיל כדורגל` — 805 player pages —
reaches the query templates through its own subpages and never through that
block.

What this changes:

- the **query layer** is where the live value is: the two biggest query
  templates have 2,542 and 2,127 callers, which is exactly what the
  `gameDataCount` drop-in and the per-entry-point filter set already address;
- the first **display** family to merge is **`ימים`**, at 366 calendar pages —
  not the player one, which is a proof of the primitive rather than a win;
- any migration inventory must start from live callers. Building one for the
  player block would have inventoried a block with none.

The lesson is recorded rather than buried: importance was inferred from
internal fan-out and never checked against `embeddedin`, which takes one call
per template.

## 3. Architecture

**Four** module pages, dependencies pointing one way only.

An earlier draft of this section proposed five, splitting a sport-agnostic
engine from a football binding. Arbitration killed that split: the ~500 pages
depend on `{{#invoke:FootballQueries|<name>}}`, not on the internals, so
extracting an engine later costs exactly what extracting it now costs — while
every extra **code** page is re-executed per `#invoke`, which is this design's
own §6 fact working against the only goal it has. The sport boundary is funded
by putting the sport's constants in the schema (decision 3), not by a second
code page. `Module` is the
canonical name of namespace 828; the wiki displays it localised as `יחידה` and
the API normalises `Module:X` → `יחידה:X`, so either spelling reaches the page.

```
Module:FootballPlayerEvents           renderer: cells → byte-identical HTML
    │  reads
    ├── Module:FootballStatsBlocks         data: cell definitions + format NAMES
    │  calls
    └── Module:FootballQueries             SQL building, execution, guards,
            │  reads                       alias expansion, #invoke entries
            └── Module:FootballQueries/Fields   data: tables, columns, filters,
                                                sport constants
```

`format` in the block data is a **name**; the formatter itself lives in the
renderer. A `loadData` page rejects functions, so describing that page as
holding "formatting" would invite one.

- **Nothing depends upward.** The renderer reads block data and calls
  `Module:FootballQueries`; the query module knows nothing about blocks.
- **The two data pages are read with `mw.loadData`.** That is one of only two
  caches that survive the `#invoke` boundary, so the schema and the cell
  definitions are parsed once per page however many blocks render. They must
  contain no functions and no metatables.
- **The query module holds no sport constants.** Table names, columns, filters
  and the side values (`מכבי` = 1 for Maccabi and 0 for the opponent in
  football; volleyball uses **2**) all live in the schema, so a second sport is
  a new data page rather than an edit to shared code. This is the whole of what
  funds decision 3 — the earlier five-module draft claimed a separate engine
  page did it, and it did not, because the sport semantics were sitting in the
  handlers.

### Why four and not two

The data/logic splits are free: `loadData` pages cost nothing extra to parse
and let the harness check 32 cell definitions without rendering anything.
Separating cell *definitions* from *rendering* is what makes the block testable
at all. Collapsing further would put the block definitions in executable code,
re-parsed per `#invoke`, and make the definitions undiffable.

### Repository layout

Source of truth is the repo; the wiki copy is deployed from it and never edited
on the wiki and copied back.

```
infra/football_queries/
  Module_CargoQuery.lua              → Module:CargoQuery
  Module_FootballSchema.lua          → Module:FootballSchema
  Module_FootballQueries.lua         → Module:FootballQueries
  Module_FootballStatsBlocks.lua     → Module:FootballStatsBlocks
  Module_FootballPlayerEvents.lua    → Module:FootballPlayerEvents
  deploy_modules.py                  publish repo → wiki (idempotent, --dry-run, --revert)
  capture_golden_numbers.py          baseline capture + selftest
  compare_rendered_pages.py          byte-identical page diff, local and prod-shadow
  tests/
    stub_mw.lua                      the mw environment, stubbed
    test_cargo_query.lua
    test_football_queries.lua
    test_football_stats_blocks.lua
    test_football_player_events.lua
  fixtures/
    golden_numbers.json
    rendered_blocks/                 before/after HTML for the diff harness
```

`deploy_modules.py` is part of the deliverable, not an afterthought: five module
pages that must move together need one idempotent publisher with a dry-run and
a revert, or the wiki and the repo drift the first time someone is in a hurry.

## 4. Interfaces

### `Module:CargoQuery`

```lua
local engine = require('Module:CargoQuery')

engine.build(schema, filters)   --> { tables, join, where }
engine.run(schema, query, options)  --> rows
```

`schema` is the loaded data table (§4.2). `filters` is a map of filter name to
value. `options` is English — `fields`, `groupBy`, `orderBy`, `having`,
`limit` — because it is this code's own interface, not the wiki's.

Rules the engine enforces, and they are errors rather than fallbacks:

- A filter name absent from `schema.filters` raises, naming the offender.
- A column with no declared quote rule raises rather than guessing.
- A value that cannot be quoted safely (a double quote inside a
  quote-keeping column) raises rather than being mangled.
- A result whose row count reached the limit raises.
- Filters and joined tables are emitted in **sorted** order, so the same filter
  set always builds byte-identical SQL.

### `Module:FootballSchema` (data)

```lua
return {
  baseTable = 'Football_Games',
  roles = { events = 'Games_Events' },     -- named roles, so the engine has no literals
  tables = { <name> = { base = true } | { join = '<condition>' } },
  columns = { ['<Table.Column>'] = 'strip' | 'keep' | 'number' },
  filters = { ['<Hebrew name>'] = { column = '<Table.Column>', kind = '<handler>' } },
  competitionCategories = { ['<value>'] = '<SQL condition>' },
  resultWords = { ['ניצחון'] = 1, ['תיקו'] = 2, ['הפסד'] = 3 },
  aliases = { stadium = {...}, opponent = {...} },
  optionParams = { ['נתון משחק'] = 'aggregate', ['הגבלה'] = 'limit' },
  aggregates = { ['כיבושים'] = 'SUM(...)', ['ספיגות'] = 'SUM(...)' },
  defaults = { events = { ['Games_Events.Team'] = 1 } },   -- see §6
  defaultLimit = 500, maxLimit = 5000,
}
```

Filter names stay Hebrew: they are the templates' published contract and the
values they match are Hebrew Cargo data. Everything else is English.

### `Module:FootballQueries` (binding)

```lua
FootballQueries.count(filters, aggregate)        --> number
FootballQueries.rows(filters, options)           --> rows
FootballQueries.aggregate(filters, cellSpecs)    --> { [cellName] = value }
```

It loads the schema, performs alias expansion (one extra query each for
`אצטדיון` / `יריבה`, only when present), and is the only module a display
module may call.

`aggregate` is the merge primitive: given shared filters and a list of
`{ name, filters }` cell deltas, it builds one query whose fields are one
conditional aggregate per cell and returns every value. It takes the cell list
as an **argument** and never reads `Module:FootballStatsBlocks` — "which cells
make up a block" is a display concern, so the dependency stays pointing one
way. That is also what lets the engine be tested with cell lists that belong to
no block.

### `Module:FootballStatsBlocks` (data)

Each block names its cells, each cell carries its own filter delta and its
format. This is the part a merge gets wrong silently, so it is data that can be
diffed, not code:

```lua
['player-events'] = {
  cells = {
    { name = 'appearances', filters = { ['מספר אירוע'] = '1,5' }, format = 'integer' },
    { name = 'goals',       filters = { ['מספר אירוע'] = '3'   }, format = 'integer' },
    { name = 'goalsRatio',  derived = 'goals / appearances',      format = 'ratio2' },
    ...
  },
  tabs = { 'ליגה', 'גביע', 'בינלאומי', 'רשמי' },   -- קטגוריית מפעל values
}
```

### `Module:FootballPlayerEvents` (renderer)

```
{{#invoke:FootballPlayerEvents|prime|שחקן={{PAGENAME}}}}   once, before the tab strip
{{#invoke:FootballPlayerEvents|tab|קטגוריית מפעל=ליגה}}     inside each tab
```

`prime` runs one query, computes all 32 cells, renders each tab's HTML and
stashes it with `frame:callParserFunction('#vardefine', …)` — the other cache
that survives `#invoke`. Each `tab` call reads its variable. The four-way call
structure and the signed `<shtml>` strip are untouched, which is what keeps the
HTML byte-identical.

## 5. Data flow, one player page

1. The wrapper template calls `prime` with the page's player name.
2. The renderer reads the block's cell list from `Module:FootballStatsBlocks`
   and hands it to `FootballQueries.aggregate({שחקן = …}, cellSpecs)`, which
   builds one query whose fields are 32 conditional aggregates — 8 cells × 4
   competition categories. The categories **overlap** (`רשמי` ⊇ `ליגה`/`גביע`/`בינלאומי`),
   so `GROUP BY` cannot produce them and conditional sums are the correct tool.
3. The engine builds `tables`/`join`/`where` from the filters, resolving only
   the tables the filters reached, and runs it through `mw.ext.cargo.query`.
4. The renderer formats each cell and `#vardefine`s four blocks of HTML.
5. Each tab body reads its variable. **One query for the page**, where today's
   path runs 32.

## 6. Facts this design rests on

All measured against production on 2026-09-13, not assumed. If any of these is
wrong, the design changes.

- **Pruning unused joins is safe here — but not for the reason first written
  down.** Cargo's `join on` emits a LEFT JOIN, so unmatched rows survive with
  NULL columns (82 such games: `ידידות` 81, `גביע מלצ'ט` 1). That rules out row
  **loss** and says nothing about row **multiplication**, which a LEFT JOIN
  does whenever the right side has several matching rows. Measured
  right-side cardinality:

  | join | rows | distinct keys | multiplies |
  |---|---|---|---|
  | `Games_Referees` on `_pageID` | 1,460 | 1,460 | no |
  | `Football_Games_Uniforms` on `_pageID` | 1,790 | 1,790 | no |
  | `Competitions` on `Competition=OriginalName` | 23 | 23 | no |
  | `Games_Events` on `_pageID` | 149,574 | 3,453 pages | **yes, up to 43×** |

  End to end, the exact four-table shape of `כמות נתוני משחק` returns
  `COUNT(*)=3504, SUM(ResultMaccabi)=6602`, and the pruned single-table query
  returns the same (59/102 both ways for `עונה=2021/22`). So for those three
  joins there is no quirk to reproduce. **`Games_Events` is the exception**, and
  it is exactly why an entry point that accepts `שחקן` where its template never
  did returns an event count instead of a game count.
- **Conditional aggregates work.** `CASE WHEN`, `IF()`, bare boolean `SUM` and
  `GROUP BY` on a flag all return correct values through the Cargo API. The
  pattern is already in use on the wiki — `מספרים עונתיים` builds its numbers
  with `SUM(CASE WHEN … THEN 1 ELSE 0 END)`. The merge is therefore not novel.
- **Cargo decodes HTML entities in the WHERE clause *after* the module has
  quoted and escaped it.** `CargoSQLQuery::newFromValues` runs
  `htmlspecialchars_decode($whereStr, ENT_QUOTES)`, and that path is shared by
  `CargoLuaLibrary`, so it is not an API-only artifact. Any entity spelling the
  module fails to decode therefore becomes a raw quote *inside* the SQL:
  proven read-only on production, `Opponents.OriginalName = "x&#x22; OR 1=1 OR ""`
  returned all 289 rows, identical to `where=1=1`. The module decodes the named,
  decimal and hex spellings and **raises on any surviving `&`** — safe rather
  than restrictive, since no value in either quote-bearing column contains one.
- **Values arrive in Lua decoded.** `CargoSQLQuery::run()` applies
  `htmlspecialchars()` on output, which is why the JSON API shows
  `בית&quot;ר ירושלים`, while `CargoLuaLibrary::cargoQuery` returns
  `htmlspecialchars_decode(...)`. The database holds the literal `"`
  (`LIKE '%quot%'` → 0 rows), so the per-column rule needs two states, not
  three. Still owed: one Scribunto smoke run on the local wiki, since this is
  read from Cargo's source rather than observed from inside Lua.
- **Quote-keeping is per column**, and the table in `maccabipedia_structure_knowledge.md`
  §16 (on the unmerged `wiki-perf-optimisations` branch) is wrong about the most
  important one. Keeps quotes: `Football_Games.Competition` (`גביע מלצ'ט`),
  `CoachMaccabi` (`ג'ורדי קרויף`), `Refs`, `Games_Events.PlayerName`,
  `Opponents.OriginalName`. Stripped: `Football_Games.Opponent`, `Stadium`,
  `Competitions.OriginalName`/`CurrentName`, `Stadiums.CanonicalName`.
  Querying a stripped column with a raw name returns zero rows and no error.
- **An events query must constrain `Games_Events.Team`.** Every query template
  touching that table does — `שיאני כמות אירועי שחקן`, `שלושער` and
  `עונות שבהן שיחק שחקן` hardcode `AND Team = 1`; `כמות אירועי שחקן` and
  siblings default `מכבי` to it. Without it one player's league goals come back
  as **152 instead of 150**, because two rows on that page belong to the
  opposing side. Hence `schema.defaults`.
- **`mw.ext.cargo.query` bypasses `CargoQuery.php`**, so it performs neither the
  second LIMIT-less SELECT nor the `cargo_backlinks` DELETE and INSERTs that a
  `#cargo_query` page view performs. This is a real saving per query, separate
  from the saving from fewer queries.
- **`mw.loadData` and `#vardefine` are the only two caches that cross
  `#invoke`.** Module state does not survive it: 1/5/20/65 calls measured at
  0.035/0.100/0.341/0.968s CPU, exactly linear.
- **`HomeAway` has four values**, not two: `בית` 1656, `חוץ` 1721, `נייטרלי`
  102, `רדיוס` 12, and 13 NULL.
- **`Games_Results`** maps ניצחון=1, תיקו=2, הפסד=3. Constant, so the layer does
  not spend a query on it the way `תבנית:המרות/תוצאת משחק למספר` does.

## 7. Quirk register — what bug-for-bug means

Decision 2 says the layer reproduces today's numbers exactly. These are the
known divergences, each of which must be **deliberately reproduced** and carry
a test asserting the quirk, so nobody "fixes" it by accident and no diff is
explained away by hand. Each also gets a follow-up issue.

| # | Today's behaviour | Correct behaviour | Reproduce? |
|---|---|---|---|
| Q1 | `קטגוריית מפעל=יתר-רשמיים` is silently ignored by `כמות נתוני משחק`, returning the unfiltered total | should filter | **yes**, per-template |
| Q2 | `תאריך` must arrive pre-quoted; an unquoted value silently yields 0 | the layer quotes it itself and accepts both forms | **not a quirk** — no number depends on it, see below |
| Q3 | `מפעלים` strips apostrophes before matching `Football_Games.Competition`, which keeps them, so `גביע מלצ'ט` never matches | should not strip | **yes** |
| Q4 | `{{סטטיסטיקה/אחוזים}}` rounds to two places and `#number_format` rounds again — two roundings, half-up | one rounding | **yes**, the double rounding is observable at boundaries |
| Q5 | `#arraydefine: מפעלים \|{{{מפעלים}}}` has no default, so the array is built from the literal string when the parameter is absent | harmless today, every use is `#if`-guarded | not applicable — no observable output |

### Q2 is a pre-quoting convention, and nothing is broken

`תאריך` must arrive **already quoted** — the same convention as
`פורמט תאריך="%d-%m"`, whose default in the template is also written with its
quotes. Measured by expanding the template both ways:

| `תאריך` value | result | database |
|---|---|---|
| `2021-03-15` (unquoted) | **0** | 9 |
| `"2021-03-15"` (quoted) | **9** | 9 |

The 366 calendar pages pass `תאריך={{#var:תאריך עבור מאזן יומי}}`, and that
variable carries the quotes, so they render correctly — verified on `15 במרץ`:
ליגה 9 = 9, אירופה 0 = 0, כל המסגרות 11 = 11.

**An earlier version of this section claimed those 366 pages were broken. They
are not.** That claim came from expanding the template with a date value I
invented, unquoted, rather than the value the caller actually passes. The same
mistake had just been made about `בית"ר ירושלים`. Expand with the caller's real
value or render the page; a hand-written parameter is not evidence about
production.

What remains is a trap, not a defect: an unquoted date yields 0 silently. The
module removes it by quoting the value itself, and because `Football_Games.Date`
is a strip-rule column it accepts the pre-quoted form too — the caller's quotes
are stripped and its own are added. No re-baseline, and Q2 needs no
reproduction because no published number depends on the broken form.

### Two more divergences, found by review and not yet decided

| | template | this layer |
|---|---|---|
| `יריבה` + `יריבות` together | `יריבות` wins; `יריבה` is the *else* branch of a nested `#if` | both conditions are ANDed, so the result is the intersection |
| a shared `מכבי` beside a game-grain cell | not expressible — the templates have no merged query | the side condition lands in the WHERE, so games with no events drop out: 3,439 of 3,504 |

The first is a real parity difference and belongs in the register: with both
parameters supplied, the template answers one question and the layer answers
another. Nothing passes both today.

The second is a semantic question rather than a bug. With a shared `מכבי` the
caller has asked about one side's events, and a game-grain cell in the same
query then counts games that *have* such events — excluding eventless games is
arguably right. It is recorded because it makes the same cell answer
differently depending on whether the caller passed the default explicitly, and
that must not be discovered later as a surprise.

Q1 is per-template, not global: the same parameter *is* honoured by
`כמות אירועי שחקן`. The layer therefore needs the quirk scoped to the call
site being replaced, which is an argument for retiring the old templates
quickly rather than living with a per-caller quirk flag for long.

## 8. Error handling

Three audiences, three behaviours:

- **A page author's mistake** (unknown filter, unknown `קטגוריית מפעל`, unsafe
  date format, a name that matches no stadium) → a visible error in the
  rendered page, naming the parameter. Silence here is what shipped the
  wiki-wide-total bug.
- **A data problem** (a result that reached the row limit) → a visible error.
  A truncated leaderboard is a normal-looking table of wrong numbers.
- **A layer bug** (no quote rule for a column, a column belonging to no known
  table) → `error()` with the module name, surfacing as a Scribunto error.

No fallbacks, no defaults-on-failure, no `pcall` swallowing. `#invoke` output is
parsed as wikitext, so error text must not contain tags outside MediaWiki's
allowlist — `<a>`, `<input>` and `<label>` are escaped.

## 9. Testing

Four layers, cheapest first. The first three need no production.

1. **Stub unit tests** (`lua5.1` + a stubbed `mw`): assert generated SQL, cell
   definitions and formatting. Milliseconds, no wiki. `mw.ext.cargo.query`
   returns queued rows and records what it was asked.
2. **Golden numbers** (`capture_golden_numbers.py`): what the current templates
   render on production, captured **before** any migration, covering all 32
   cells of the block plus one entity of each of the nine types. Extraction
   must be label-anchored, not positional — positional comparison reports every
   position after a reordering as a false diff.
3. **Byte-identical page diff** (`compare_rendered_pages.py`): render the
   wrapper template before and after on the local wiki and diff the HTML. The
   signed `<shtml>` passes through untouched, so the local wiki's different
   HMAC secret does not matter.
4. **Read-only prod shadow**: render the new module's output against production
   data without editing any page, because the local wiki holds only
   2021/22–2024/25 and the quirks live in the old seasons.

**Every check must be proven to fail before it is trusted.** Of the defects
found in the earlier attempt at this work, all nine were in the checking and
five reported success while comparing nothing. Concretely, each harness ships
with a mutation: flip a column's quote rule, weaken the row-limit guard from
`>=` to `>`, corrupt one stored number — and the suite must go red. A green
first run is not evidence.

## 10. Migration and retirement

Decision 4 retires the old query templates, so every call site must be found.
`list=embeddedin` **cannot** do this: almost every template wraps its body in
`<includeonly>`, so the template page's own render never expands its calls and
no templatelink is recorded. It returns the articles correctly and zero
templates, which reads like a real answer.

The inventory is therefore:

1. `list=allpages&apnamespace=10`, then `prop=revisions` in batches of ~12
   (Hebrew titles percent-encode to ~10×; 50 per GET returns HTTP 414), and
   match the template name in the source. This is the only reliable list of
   template callers.
2. `embeddedin` for articles, categories and the sport namespaces, which it
   does report correctly — 991 pages had the deleted canary template in their
   last parse, so this list is large and matters.

Then, per template:

3. Migrate its callers to the module.
4. Replace the old template's body with a **tripwire**: it still returns the
   right number, and additionally adds a hidden tracking category. Anything
   missed by the inventory surfaces as a page in that category instead of
   silently.
5. Watch the category. Delete only when it stays empty.

Deleting before the tripwire is what put a red link on a live season page
earlier today: the canary template was deleted outright while ~991 pages still
referenced it.

## 11. Rollout

1. All five modules and the block built and green on the local wiki, with the
   byte-identical diff passing.
2. Read-only prod shadow comparison across the nine entity types.
3. Modules published to production — they are inert until something calls them.
4. **One** low-traffic page migrated, watched. The old template body is
   restorable in one edit, and `deploy_modules.py --revert` restores the module
   pages.
5. The rest of the block's call sites, then the tripwire and retirement.

No production write happens without explicit approval at each of steps 3, 4
and 5.

## 12. Risks

| Risk | Mitigation |
|---|---|
| A merged block gets one cell's filter subtly wrong — the `Team` class of bug | Cell definitions are data with per-cell tests; golden fixture covers all 32 cells before migration |
| 32 conditional aggregates in one query is slower than 32 small queries | Measure on the local wiki with the measurement overlay (`MW_DISABLE_FOREIGN_IMAGES` is required, or the timings measure network latency to prod) before migrating anything |
| `mw.ext.cargo.query` behaves differently from `#cargo_query` in some way the stub cannot reveal | Step 1 of rollout is a real Scribunto run on the local wiki; the stub is explicitly not evidence about Cargo |
| The engine/binding split turns out to be premature | It is two small pages; collapsing them later is mechanical, unlike extracting them later |
| Row limits hit at prod scale but not at local scale | The limit guard raises rather than truncating, and `check_query_limits` measures real sizes against production |
| A missed call site breaks a page after retirement | The tripwire in §10 turns a silent break into a tracking category |

## 13. Out of scope

Each gets its own spec once this interface is stable: the other eight display
families; the 128 leaderboard call sites (they need `GROUP BY`, ordering, row
limits and two parameters the layer does not have — `שופטים`, `תצוגת יחיד`);
the three `איש צוות` templates (they need `שם לבדיקה`, which reads staff tables,
not games); `כמות רשומות` (it counts rows of an already-rendered query and is
obsolete once a block is one query); goalkeeper statistics and `עוזר שופט`,
which the earlier attempt deliberately left out; and the ten
`סטטיסטיקה/כדורעף/` templates, which follow the same pattern for volleyball.

## 14. Open questions

1. **PR #190** — merge it as the foundation and build on top, or close it and
   resubmit the five-module shape as one reviewed change? Its current content is
   three of the five modules' worth of logic in two pages, and its three
   departures from template behaviour now contradict decision 2.
2. **Where the `prime` invoke goes.** It must run before the tab strip, which
   means editing the wrapper template (`סיכום אירועים`), not only the block.
   Byte-identical output constrains how that edit can look.
3. **Whether `Module:CargoQuery` should be named that at all** before a second
   sport exists, given it will look like a general-purpose utility to the next
   editor who finds it.
