# Football Queries — the Lua query layer

Design and the decisions behind it: `.claude/football_queries_design.md`.

`infra/football_queries/` holds the Lua that turns a filter set into one Cargo
query. **The repo is the source of truth**: the wiki copy is deployed from
here, never edited on the wiki and copied back.

| file | wiki page |
|---|---|
| `Module_FootballQueries.lua` | `Module:FootballQueries` |
| `Module_FootballQueries_Fields.lua` | `Module:FootballQueries/Fields` |

`Module` is the canonical name of namespace 828; the wiki displays it localised
as `יחידה`, and the API normalises `Module:X` to `יחידה:X`. Either spelling
reaches the same page, so code and docs use `Module:`.

## Which templates are actually rendered

Measured 2026-09-13 with `embeddedin`, one call per template: **41 of the 72
statistics templates have no callers**, 30 of them display templates. Ranked by
live callers: `אחוזים` 3,000+, `כמות נתוני משחק` 2,542, `כמות אירועי שחקן`
2,127, `כמות רשומות` 2,057, four player-page query templates ~805 each, the
`ימים` display pair 366 each — and `תצוגה/שחקנים/סיכום אירועים`, the block this
layer was first built against, **0**.

So the delivered renderer is a proof of the merge, not a live win. The live
value is in the query templates, and the first display family worth merging is
`ימים` (366 calendar pages). Full table in
`.claude/football_queries_design.md` §2b.

## Why it exists

The statistics templates issue **one Cargo query per number**: the player
events block calls `כמות אירועי שחקן` eight times, four tabs deep, so 32
queries render one column. A Cargo query costs little in SQL and a lot in
per-query bookkeeping, so fewer queries beats cheaper queries. Scribunto keeps
no module state between `#invoke` calls, so the only way to win is for one
invoke to render a whole block.

Each of the ~20 query templates also re-implements the same join graph, quote
rules and competition flags, and they have drifted: `קטגוריית מפעל=יתר-רשמיים`
filters in `כמות אירועי שחקן` and is **silently ignored** by
`כמות נתוני משחק`, which hands that page the unfiltered total.

## Language rule

Filter names arrive in **Hebrew** — `שחקן`, `קטגוריית מפעל=ליגה`. They are the
templates' published contract and the values are Hebrew data, so translating
them would make the code wrong. Everything else — page names, comments,
locals, query options (`fields`, `groupBy`, `limit`) — is English.

## Two guarantees

- **An unsupported filter is an error, never a dropped condition.** A dropped
  filter does not look like a failure, it looks like a number. A wrapper that
  forwards a fixed parameter list defeats this, so a wrapper must forward
  everything it was given.
- **A result that reached the row limit is an error, never a short answer.**
  Cargo truncates silently, and a block built from a truncated result is a
  normal-looking table of wrong numbers.

## Replacing a query template

`Module:FootballQueries|gameDataCount` is a drop-in body for a query template —
it reads the **parent** frame, so the template enumerates no parameters and
therefore cannot drop one:

```wikitext
<includeonly>{{#invoke:FootballQueries|gameDataCount}}</includeonly>
```

That shape is deliberate. A shim that forwards a fixed parameter list silently
defeats the unsupported-filter guard, which is how an opponent page once asked
for its own yellow cards and was handed the wiki-wide total. Enumerating
nothing is the only way the guard stays honest.

**One shim per template, never one for both.** `כמות אירועי שחקן` has its own
entry point, `playerEventCount`: it counts events, takes `מספר אירוע` and
`שחקן`, and has no `נתון משחק`. Pointing it at `gameDataCount` instead —
which the comparison harness did for a while — refuses every event filter and
renders a red Lua error where the number was. Each entry point declares the
parameters of the template it replaces, and the two lists have to be checked
against the template, not against each other:

```bash
uv run python infra/football_queries/verify_entry_points.py
uv run python infra/football_queries/verify_entry_points.py --selftest
```

It reads each template's wikitext from the local wiki, extracts the `{{{…}}}`
parameters it actually reads, and reports both directions of drift: a
parameter the template takes and the shim refuses (a red error on the page),
and one the shim accepts and the template cannot be asked (a plausible number
answering a different question).

## A block's own constant filters

A block definition may carry `filters`, applied to every one of its cells.
`day-results` fixes `פורמט תאריך = "%d-%m"` there, because the template
hardcodes that format in each of its five calls — it is what makes the block
*this day in any year* rather than *this exact date*. Without it the default
`%d-%m-%Y` matches a single year, which agrees with the template by luck on
dates whose only game is in that year and disagrees everywhere else: 4 of 5
sample dates matched before this was found.

A caller that passes a filter the block fixes is **refused**, not overridden
and not ignored — either of those leaves a page showing the wrong window of
games with nothing in the wikitext to see.

Coverage of the 22 query templates, computed from the Lua spec against each
template's own parameters:

| template | call sites | status |
|---|---|---|
| `כמות נתוני משחק` | 34 | drop-in ready (`gameDataCount`) |
| `כמות אירועי שחקן` | 24 | drop-in ready, `COUNT(*)` only |
| `שיאני כמות אירועי שחקן` | 128 | needs leaderboard rows, `שופטים`, `תצוגת יחיד` |
| `משחק הבכורה`, `משחקים מסודרים…`, `שלושער` | 14–20 each | filters covered, output is a formatted table → display layer |
| the three `איש צוות` templates | — | need `שם לבדיקה` (staff tables, not football games) |
| `כמות רשומות` | — | counts rows of an already-rendered query; obsolete once a block is one query |

## Facts measured against production, 2026-09-13

- **Cargo's `join on` emits a LEFT JOIN.** A game whose competition has no
  `Competitions` row survives the join with NULL columns — 82 such games
  (`ידידות` 81, `גביע מלצ'ט` 1). So joining only the tables a filter actually
  needs **cannot change a row count**; it is a cost decision, not a
  correctness one. `{עונה=2021/22}` joins one table where the templates join
  four.
- **Which columns keep quote characters**, per column, and this contradicts the
  §16 table in `maccabipedia_structure_knowledge.md` on the branch that adds it
  (that table calls `Football_Games.Competition` stripped and omits
  `CoachMaccabi`):

  | keeps `'` | stripped |
  |---|---|
  | `Football_Games.Competition` (`גביע מלצ'ט`) | `Football_Games.Opponent` |
  | `Football_Games.CoachMaccabi` (`ג'ורדי קרויף`) | `Football_Games.Stadium` |
  | `Football_Games.Refs` | `Competitions.OriginalName` / `CurrentName` |
  | `Games_Events.PlayerName` | `Stadiums.CanonicalName` |
  | `Opponents.OriginalName` | |

  Querying a stripped column with the raw name returns **zero rows and no
  error**, so every column a filter touches needs a declared rule and a missing
  one raises rather than guesses.
- **`תוצאה` in words maps to `ResultOpt`** as ניצחון=1, תיקו=2, הפסד=3, read
  from the `Games_Results` table. `תבנית:המרות/תוצאת משחק למספר` spends a Cargo
  query on those three constant rows; this layer does not.
- **An events query must constrain `Games_Events.Team`.** Every query template
  that touches that table does — most hardcode `AND Team = 1`, the rest default
  the `מכבי` parameter to it — so a query without it counts the opposing side's
  events too. One player's league goals come back as **152 without it and 150
  with it**, because two rows on that page belong to the opponent. The layer
  applies `Team = 1` whenever `Games_Events` is joined and `מכבי` did not say
  otherwise.
- **`HomeAway` has four values**, not two: `בית` 1656, `חוץ` 1721, `נייטרלי`
  102, `רדיוס` 12, plus 13 NULL. A `ביתחוץ` filter passes the value through.
- **Alias expansion is not symmetrical.** Stadiums relate rows by `_pageID` and
  match on `CanonicalName`; opponents relate rows by `CanonicalName` and match
  on `OriginalName`. The reason is in
  `maccabipedia_structure_knowledge.md` §15: for `Stadiums` the two name columns
  are identical in all 199 rows, so grouping has to use the page, while
  `Opponents.CanonicalName` is a genuine club **identity** across renames and
  mergers (271 ids over 289 rows; 10 ids carry several names; no name maps to
  two ids) — and **neither column holds the normalised spelling**. Normalisation
  is a write-time transform that only the games table carries, which is why a
  lookup that strips its input finds nothing for the 37 quote-bearing clubs.
  That is a **latent trap, not a live defect**: the club pages do not reach the
  lookup with the raw name, and `בית"ר ירושלים` renders its 173 games
  correctly. Do not introduce a caller that passes the raw page name to it.

## Edge cases in the data, and what they cost

Measured on production 2026-09-13. `verify_edge_cases.py` runs the module's own
SQL for each of these against production, read-only, and compares it with an
independently written query — 25/25 agree, and it carries a selftest that
proves it can fail.

- **A club whose name carries a quote.** `בית"ר ירושלים` (173 games) and
  `צ'לסי` (3) resolve correctly through both the list parameter and the alias
  expansion, because the games table stores the normalised spelling and the
  lookup keeps the raw one.
- **One player name on both teams in the same game.** Nine name/game pairs
  exist. Pinned to the single game, because a career total would not show the
  confusion: `אלון נתן` on 1986-05-24 is 2 events for Maccabi and 1 against,
  and `אברהם לוי` on 1975-03-01 is 2 and 2 — where a leak is invisible in the
  total and only the per-side comparison catches it.
- **The event/subtype matrix.** Subtype numbers are namespaced by their event:
  3 → 30–39, 4 → 40–46, 7 → 71–74, 8 → 81–84, 13 → 131–133, and 1/2 carry both
  NULL and 111/211. **No subtype number is used under two event types**, so a
  subtype filter is unambiguous.
- **`ללא תת אירוע` drops NULL subtypes too.** `SubType != 33` cannot match a
  row whose subtype is NULL, and 118,197 of 149,574 events have none. It is
  harmless in the one place it is used — goals always carry a subtype (0 NULLs
  of 9,862), so excluding own goals gives 6,287 − 62 = 6,225, correctly — but
  the same filter on event type 1, 2 or 5 would silently drop 90–100% of the
  rows. The templates emit the same SQL, so the layer reproduces it.
- **Games with no events at all: 51**, plus 65 with no Maccabi event, and 16
  technical results. Metadata numbers must include them: for 1941/42 — 31
  games, 6 of them eventless, 1 technical — the layer reports wins 24, draws 3,
  losses 4 and all games 31, which sums, and the query does not join the events
  table at all. Putting the Team constraint in the WHERE broke exactly this,
  taking 3,504 games down to 3,439.

## Documenting and categorising a module

A module page holds Lua, not wikitext, so it cannot carry a category itself.
The documentation subpage does, and Scribunto shows it at the top of the module
page. Three things to know, each of which cost an attempt:

- **The doc page name is localised.** `scribunto-doc-page-name` here is
  `Module:$1/תיעוד`, so `/doc` is **not** a documentation page — it stays
  Scribunto content and saving wikitext on it fails with "Lua error: unexpected
  symbol". `/תיעוד` reports `contentmodel: wikitext`, as it should.
- **The category must sit inside `<includeonly>`** so it lands on the *module*
  page rather than on the doc page.
- **The module page must then be purged.** Editing a doc does not re-parse the
  module, so the category stays empty and looks broken.
  `deploy_modules.py` purges after writing.

## Testing

There is no Lua interpreter in MediaWiki's path here, so tests run against a
stub of the `mw` environment — `mw.text.trim`, `mw.loadData`, and an
`mw.ext.cargo.query` that returns queued rows and records what it was asked:

```bash
lua5.1 infra/football_queries/tests/test_football_queries.lua   # needs: apt install lua5.1
luac5.1 -p infra/football_queries/*.lua                          # syntax only
```

The suite asserts generated SQL, so it is fast and needs no wiki. **Confirm it
fails before trusting a pass** — and not by picking two mutations, which is how
10 of 18 escaped once:

```bash
uv run python infra/football_queries/tests/mutate.py   # 83 mutations, 0 may survive
```

This gate runs in CI (`.github/workflows/tests.yaml`, job `lua`): it needs no
wiki, so every PR gets it.

**The wiki-level harnesses also gate a PR now.**
`.github/workflows/football_lua_wiki.yaml` boots `infra/local-wiki/` on the
runner, restores `infra/local-wiki/fixtures/wiki-snapshot.sql.gz`, deploys the
modules and renders both paths — 3m27s including a cold image build, and it
fails on one differing byte. So the byte-identical comparison is no longer
something a human has to remember to run.

Two things stay outside it, for stated reasons:

- `verify_edge_cases.py` queries **production**, read-only: its cases (a club
  whose name carries a quote, one player on both teams of one game, the rare
  subtypes, a season with eventless and technical games) live in old data the
  local seed does not hold. Making it blocking means seeding those rows into
  the fixture first.
- Anything needing production credentials. The CI wiki is built from the repo
  and the committed snapshot, and reaches nothing else.

Then run it for real, because the stub cannot tell you anything about Cargo or
Scribunto:

```bash
uv run python infra/football_queries/deploy_modules.py --dry-run   # repo -> local wiki
uv run python infra/football_queries/deploy_modules.py
uv run python infra/football_queries/smoke_test_local.py           # module vs Cargo
```

`deploy_modules.py` writes through `maintenance/edit.php` inside the local wiki
container, so it needs no credentials and cannot reach production.
`smoke_test_local.py` computes every expectation with a direct Cargo query, so
the module is compared against the database rather than against itself.

### What only a real Scribunto run revealed

- **`next()` does not work on `frame.args`.** Scribunto populates it lazily
  behind a metatable, so a guard written as `next(frame.args) ~= nil` never
  fires. Use `pairs`.
- **`gameDataCount` reads the *parent* frame**, so invoking it directly from
  wikitext passes it nothing — and it answered `222`, every game, for every
  filtered query. It now raises and names the entry point to use instead.
- **The frame entry point is `count`; the Lua API is `countFilters`.** When
  Scribunto handed a frame to a function expecting a filter table, the module
  iterated the frame's fields and blamed a filter called `"args"`, which sends
  the reader somewhere else entirely.

## NULL is an empty cell, never a zero

`COUNT` over no rows is `0`; `SUM` over no rows is `NULL`, and the templates
render `NULL` as an **empty cell** — `{{#number_format:}}` of nothing is
nothing. So `countFilters` returns `nil` rather than `0` when the database
answered NULL, and both `count` and `gameDataCount` turn that into `''`.

The same rule inside the merged query is subtler and cost a real bug:

```sql
SUM(CASE WHEN <cell condition> THEN <column> ELSE NULL END)   -- correct
SUM(CASE WHEN <cell condition> THEN <column> ELSE 0 END)      -- wrong
```

`ELSE 0` makes the sum `0` as soon as the query matches **any** row, not only
when a row matches the cell's own condition. Measured on the local wiki over
222 rows: `ELSE 0` → `0`, `ELSE NULL` → `NULL`. The day block reaches this
through `prime`, which moves each tab's category into the cells — so a cup tab
on a date with only league games printed `0` כיבושים where the template prints
nothing. `--day` now includes a date whose category has no games, which is the
only case that exercises it.

`capture_golden_numbers.py` records what the current templates render on
production into `fixtures/golden_numbers.json`, as the baseline the rewrite has
to reproduce. Its `selftest` corrupts a stored number and asserts the
comparison reports it.

## LIVE on production: the day family, 2026-09-15

`תבנית:סטטיסטיקה/תצוגה/ימים/סיכום תוצאות` renders through
`Module:FootballStatsBlock` on all **366** day pages. **28 Cargo queries → 1.**

Measured on production over 366 renders:

| | p50 | p95 | mean |
|---|---|---|---|
| before (28 queries) | 559 ms | 668 ms | 599 ms |
| after (1 query) | **162 ms** | **208 ms** | **176 ms** |

Also live and called by nothing: the four modules plus their `/תיעוד` pages
and `קטגוריה:יחידות לואה`.

How it was made safe, in the order it happened:

1. `capture_day_pages.py capture` recorded the 8,784 published numbers on all
   366 pages, stamped with the template revision (104114).
2. `compare_prod_day_pages.py --publish` put the module version on a sandbox
   page nothing transcludes, and `--compare` rendered **both** paths for every
   day of the year on production data: **366/366 byte-identical**. This is the
   step the local wiki cannot do - it holds 2021/22-2024/25 while production
   holds every season back to 1906.
3. `migrate_day_template.py --apply` wrote the live template, recording the
   previous revision and its full text for `--revert`.
4. `capture_day_pages.py purge` re-parsed all 366 pages. **Without this the
   verification is worthless**: `action=parse` serves the parser cache written
   before the edit, so the comparison would match the old rendering against
   itself and pass whatever the modules did.
5. `capture_day_pages.py verify` found **8 differences, all on one page**
   (`14 בספטמבר`), moving together: +1 league game, +1 official, +1 win,
   +4 goals for, +1 against.

Those 8 were **not** a defect, and the way that was settled is worth reusing:
a baseline comparison cannot tell a migration bug from the data having moved
on, because both look like a changed number. `ab_day_template.py` writes the
pre-migration text to a second sandbox page and renders it beside the live one
**at the same moment** - 5/5 identical, including that date. The cause was a
real game added after the capture: Maccabi 4-1 הפועל תל אביב, 2026-09-14.

## One invoke: `render`

`{{#invoke:FootballStatsBlock|render|בלוק=day-results}}` renders the whole day
widget as a `<tabber>` (no `<shtml>`, no page variables) from the same single
query. Deployed to prod as an entry point; the live template still uses
`prime`/`tab`/`value` until it is switched with `convert_day_to_tabber.py`.
Checked by `compare_day_widget.py` (`--selftest`, `--all`; a sample runs in
CI). Details and the pixel work: `.claude/shtml_free_tabs_design.md` §7.

## Leaderboards: `leaderboards` (referee and season pages)

`{{#invoke:FootballStatsBlock|leaderboards|בלוק=…}}` renders four leaderboard
boxes (הופעות / כיבושים / בישולים / מוצהבים|צהובים), four tabs each, as
`<tabber>`s from **one** query instead of 32. Two blocks use it:
`referee-assistant` (see `.claude/referee_leaderboards_spec.md`) and `season`,
which `תבנית:עונת כדורגל` calls on the 104 season pages
(`convert_season_section.py` swaps its four `הצגת שיאני …` lines for the invoke).

`season` differs from `referee-assistant` only in data: entity `עונה` is a
plain `Football_Games.Season` filter (no alias lookup); tab 4 is `בינלאומי`;
the cards box is `שיאני מוצהבים`; and its wrapper `boxOpen` has **no** id -
on season pages `id="שיאנים"` sits on the parent container. `boxOpen` is a
required block field with no default; the referee one is the exact string the
renderer used to hard-code, so referee markup is byte-identical.

Deliberate departures, allowed by both comparison harnesses: players tied at
the tenth place are ordered by name; a tab with exactly ten players has no
"עוד" link (it led to an empty page); tab 4 shows the globe. Visible but not
a data change: TabberNeue writes the URL hash on a tab click
(`$wgTabberNeueUpdateLocationOnTabChange`), so a reloaded or shared link opens
scrolled to the boxes - and panel ids carry the box's position on the page,
so converting a tabbed strip above them later re-targets those links.

Checks: `compare_season_leaderboards.py` (local; `--selftest` must FAIL) and
`compare_referee_leaderboards.py`, both in CI. Each tab must read as many rows
as its heading promises, or the tab fails. **The fixture must ship
`תבנית:עונת כדורגל` unconverted** - the harness builds its OLD side from it;
`convert_season_section.py --local --apply` is a demo layered on afterwards.
Measured locally, section only: p50 737 → 388 ms. On production the section
costs 714 ms of a 4.2 s cold page parse.

### Stadium pages: block `stadium`

The 199 stadium pages (`תבנית:אצטדיון כדורגל`) call the **same four
`סטטיסטיקה/תצוגה/שחקנים/שיאני …/עיצוב חדש` box templates** as the season pages,
filtered by `אצטדיונים` - the stadium's historical names plus its own
(`אצטדיונים לשליפה`). So block `stadium` is **derived** from `season` when the
data module loads (a deep copy with `entity`/`entityFilter = 'אצטדיונים'`),
not copied: the two cannot drift, and a stub test asserts identical markup for
identical rows. `אצטדיונים` is a `list` filter on the strip-rule column
`Football_Games.Stadium`: `normalise` decodes `&quot;`/`&#34;`/`&#39;` from
PAGENAME, the rule strips `'`/`"` - what `המרות/שם ללא גרש וגרשיים` did. The
Hebrew ׳/״ are kept by both (one stored name has ׳: `אצטדיון זדז׳לה`).

The boxes switch from `record-section-container`/`.content` to the module's
`records-list-tabs-container`/`.list`, which carries the same title decorator
and the converted-tabber row styling; the page's grid
(`details-records-lists-container`, which keeps `id="שיאנים"`) lays out any
four children. Local screenshots at 1400/800/390 px, every tab: same size,
same rows, only the accepted departures.

Measured on production: the boxes (32 queries) were **2.40 s of `אצטדיון
בלומפילד`'s 2.76 s cold parse**. The section alone, old → new, over all 199
pages (`--sandbox`, 2026-09-22): median **0.59 → 0.10 s**; Bloomfield 1.91 →
0.48, רמת גן 1.38 → 0.40. **199/199 match, 8,122 rows**, 20 stadiums with no
games, 11 quote-bearing names with games.

Tools: `convert_stadium_section.py --print` (the candidate, from production's
template; refuses unless the four boxes appear once, in order, inside the
grid) and `compare_stadium_leaderboards.py`:

- `--sandbox` - before anything is published: per page, the section alone,
  OLD through the live templates vs NEW with `Module:FootballStatsBlocks`
  overridden by the repo file (TemplateSandbox, one page per request - which is
  why this mode renders only the section). Both sides first run the template's
  own preamble with the page's parameters, so they read the same list.
- `--full` - after the block data is published: the whole page with the
  stadium template overridden by the candidate; outside the section
  byte-identical.
- Both: per box and tab, the referee rules; plus the official appearances
  heading on BOTH sides must equal a **direct Cargo count** written apart from
  both paths - so a filter both get wrong (a name stripped to nothing) cannot
  pass as agreement. `--selftest` (Bloomfield OLD vs Ramat Gan NEW) must FAIL.
  It checks that production's other three modules equal the repo's first.

**LIVE 2026-09-22** (template revision 206178). Whole page after the purge:
Bloomfield **2.76 → 0.80 s**, other stadiums 0.27-0.58 s; 0 pages in the
script-error category. Two things the rollout taught: `--full` found 71/199
enough once `--sandbox` had covered every page's data (the template edit is
the same text everywhere); and an **anonymous** purge is rate-limited to 30 a
minute - purge through the bot's session (`deploy_modules_prod.purge`), which
has no limit.

**Rollout, in order:** `--sandbox` over every page → publish
`Module:FootballStatsBlocks` (**not inert**: every day, season and referee
page loadData's it and is queued for re-parse; off-peak, read back, then
`deploy_modules_prod.py --probe`) → `--full` over every page → edit
`תבנית:אצטדיון כדורגל` (keep the old text) → purge the stadium pages in
batches of 10 → spot-check a few, and check for script errors. Revert: the old
template text. The block data can stay.

**Production rollout, in order - stop at the first failure:**

1. **Gate A - publish the modules.** Not inert: every day and referee page
   invokes them and re-renders on its next view. First capture an uncached
   render (`action=parse` with `text=`) of 3 referee sections; then
   `deploy_modules_prod.py --publish`, `--check`, `--probe` (referee and
   season `leaderboards` must each render four boxes); then re-render the 3
   referees and byte-diff the `records-list-tabs-container` fragments. Any
   difference → roll back.
2. **Rollback order:** republish ONLY `Module:FootballStatsBlock` from the
   previous commit. Its old code ignores the newer blocks data; publishing the
   old blocks data first leaves the new renderer reading a missing `boxOpen` -
   a Lua error on every referee page until the second write lands.
   **Exception, once מספרים עונתיים runs on `season-results`/`season-cards`:**
   those blocks have no rows and an older renderer's `prime` cannot handle
   that, so revert the season-numbers tab and container templates first, then
   the module (`.claude/season_pages.md`).
3. **Before Gate B:** `compare_season_leaderboards.py --prod` - a read-only
   sweep of all 104 production season pages, OLD template chain vs the
   published module. It errors before Gate A and must pass after it.
4. **Gate B - switch the template.** Edit `תבנית:עונת כדורגל` (keep the
   previous text for revert), purge the season pages in batches of 10, and
   open a few - an empty season, 1966/68, the current one.

## Rewriting a template chain as a module — lessons from the season squad (2026-09-21)

`Module:FootballSeasonSquad` (season pages, `.claude/season_pages.md` Change 5)
does not use the query layer: it renders cards, not statistics, and talks to
`mw.ext.cargo.query` directly. What it took to replace ~90 template queries
with 3 without changing a byte of the cards:

**Gate on production without editing it.** Production accepts TemplateSandbox
parameters on `action=parse` and `action=expandtemplates`:
`templatesandboxtitle`, `templatesandboxtext`, `templatesandboxcontentmodel`
(`Scribunto` for a module, `wikitext` for a template). The UNSAVED text
renders in place, so an old-vs-new comparison over every page needs no
`/ארגז חול` copy and no edit. One page is overridden per request: to test a
template that calls a new module, save the module first (inert - nothing calls
it) or put the `#invoke` straight into the parse text. The same trick measures
what one piece of a template costs: override it with that piece removed and
take the difference in `limitreport-walltime`.

**`mw.ext.cargo.query` is not `#cargo_query`.**
- It returns raw database values. `#cargo_query format=template` hands the
  template HTML-encoded values (a `"` arrives as `&quot;`), and a template that
  compared against it compared encoded text - the captain check needs
  FullHebName re-encoded to match.
- Alias every field: an unaliased `ge.PlayerName` comes back with no key.
- NULL comes back as `nil`, not `''`.
- A query with no limit gets Cargo's default of 100 and truncates silently.
  Set a limit and raise when a result reaches it - unless the point is to
  keep a template's SQL exactly, in which case keep its (absent) limit too.
- `_pageName IN ()` raises. The template's version failed silently and its
  output was hidden by an emptiness check; the module must skip the query.
- Module output is not re-preprocessed: `<nowiki>` and other tags must go
  through `frame:extensionTag`. Links and `[[קובץ:…]]` are fine as plain text.

**Wikitext semantics the module has to copy:** `#שווה` (`#ifeq`) compares
numerically when both sides are numbers, so `0` equals the `000` default and a
shirt number 0 was hidden. `#arrayunique` drops empty elements.
`#arrayprint` trims each item. Parser functions trim their results. A card
template's trailing newline disappears inside `#arrayprint`.

**Any rewrite reorders MySQL's ties.** A template that sorts by a column with
many NULLs (MainNumber on old profiles) shows ties in whatever order MySQL
returns them, and a different query - even the same table with an IN list
instead of `HOLDS` - returns them differently. Byte-identity then means
keeping the old queries. The squad first did (8 queries, 101/101 identical);
the maintainer then chose a defined order, which retired them. Decide that
up front.

**Gates that cannot pass vacuously.**
- Prime both sides the way the real page does (`עונה להצגה`, `קפטנים`), and
  require something the priming produces to appear on both (captain icons),
  or both sides render nothing and agree.
- Prove the new side ran the new code (the module in `prop=templates`, or a
  season that must differ).
- A selftest that must fail: season A's old block against season B's new;
  for a deliberate reorder, today's order graded against the new rule.
- For a deliberate visible change, the gate allows exactly that change: the
  same cards per position byte for byte, only the order different, and the
  new order checked against Cargo by separately written code.
- Whole pages byte-identical outside the changed block, with the new template
  swapped in by TemplateSandbox - that catches page variables the old chain
  leaked and something later read.
- A production parse can flake (a `<p class="mw-empty-elt">` shift with
  identical `expandtemplates` output). Rerun before chasing one whitespace diff.

The verification scripts were one-offs and are not in the repo; the above is
enough to rebuild them.

## Not done yet

- Departures from the templates, which will show as real diffs against the
  golden fixture. The first three were chosen; the last two were discovered
  afterwards, and both are **re-baselines** — they change published numbers from
  wrong to right, so each needs a before *and* an after fixture rather than a
  parity diff:

  1. `יתר-רשמיים` filters instead of being silently ignored.
  2. The layer quotes the date itself, where the template requires the caller
     to pass it **already quoted** (`תאריך="2021-03-15"` → 9;
     `תאריך=2021-03-15` → 0, silently). The 366 calendar pages do pass the
     quoted form and render correctly, so **no published number changes** —
     this removes a trap rather than fixing a bug. Because
     `Football_Games.Date` is a strip-rule column the layer accepts either
     form: the caller's quotes are stripped and its own added.
  3. `מפעלים` no longer strips apostrophes, because
     `Football_Games.Competition` keeps them.
  4. **The opponent alias keeps the quote when looking a club up**, so
     `יריבה=בית"ר ירושלים` resolves where the template returns nothing. **This
     changes no published number** — the club pages do not call the lookup with
     the raw name, and Beitar's page already renders its 173 games correctly.
     It removes a trap rather than fixing a live bug, so it needs no
     re-baseline.
  5. **A player name containing a quote works.** `כמות אירועי שחקן`
     interpolates `PlayerName= "{{{שחקן}}}"` raw, which Cargo's entity decode
     turns into invalid SQL for the 14 quote-bearing `Games_Events.PlayerName`
     rows; the module escapes it.
- An unknown `קטגוריית מפעל` value adds no condition in the templates — a typo
  silently returns the unfiltered total — while this layer raises. Better
  behaviour, but a behaviour change across ~34 call sites.
