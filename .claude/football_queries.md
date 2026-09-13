# Football Queries — the Lua query layer

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
- **`HomeAway` has four values**, not two: `בית` 1656, `חוץ` 1721, `נייטרלי`
  102, `רדיוס` 12, plus 13 NULL. A `ביתחוץ` filter passes the value through.
- **Alias expansion is not symmetrical.** Stadiums relate rows by `_pageID` and
  match on `CanonicalName`; opponents relate rows by `CanonicalName` and match
  on `OriginalName`.

## Testing

There is no Lua interpreter in MediaWiki's path here, so tests run against a
stub of the `mw` environment — `mw.text.trim`, `mw.loadData`, and an
`mw.ext.cargo.query` that returns queued rows and records what it was asked:

```bash
lua5.1 infra/football_queries/tests/test_football_queries.lua   # needs: apt install lua5.1
luac5.1 -p infra/football_queries/*.lua                          # syntax only
```

The suite asserts generated SQL, so it is fast and needs no wiki. **Confirm it
fails before trusting a pass** — flipping `Games_Events.PlayerName` from `keep`
to `strip`, or the row-limit guard from `>=` to `>`, must turn it red.

`capture_golden_numbers.py` records what the current templates render on
production into `fixtures/golden_numbers.json`, as the baseline the rewrite has
to reproduce. Its `selftest` corrupts a stored number and asserts the
comparison reports it.

## Not done yet

- Nothing is installed on any wiki. The stub proves the SQL shape, not that the
  numbers match; that needs the module running against real data.
- No display module yet, so nothing renders a block.
- Three deliberate departures from the templates, which will show as real diffs
  against the golden fixture: `יתר-רשמיים` filters instead of being ignored,
  dates are quoted inside `DATE_FORMAT` instead of interpolated bare, and
  `מפעלים` no longer strips apostrophes because `Football_Games.Competition`
  keeps them.
