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
wiki, so every PR gets it. The wiki-level harnesses below are local only.

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

## Not done yet

- Nothing is installed on any wiki. The stub proves the SQL shape, not that the
  numbers match; that needs the module running against real data.
- No display module yet, so nothing renders a block.
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
