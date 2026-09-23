# Wiki Lua modules — the query layer and the modules built on it

Design and the decisions behind it: `.claude/lua_modules_design.md`.

`infra/lua_modules/` holds the Lua that turns a filter set into one Cargo
query. **The repo is the source of truth**: the wiki copy is deployed from
here, never edited on the wiki and copied back.

The directory holds every wiki Lua module and its harnesses for all three sports
(renamed from `infra/football_queries/` on 2026-09-23, PR #230).

The live list is `MODULES` in `deploy_modules_prod.py`. Each file `Module_X.lua`
is the wiki page `Module:X` (`_` for `/`). As of 2026-09-23 the shape is:

| page | role |
|---|---|
| `Module:SportQueries` | **shared logic**: one Cargo query from one filter set. `new(Fields)` binds it to a sport's schema; it never names a sport, a table or a wiki page. |
| `Module:StatsBlock` | **shared renderer**: a statistics block (cells, tabs, leaderboards) from one query. `new(Queries, blocksData, name)`. |
| `Module:FootballQueries` | football's five-line shim: `SportQueries.new(mw.loadData('Module:FootballQueries/Fields'))`. The 1,687 pages that invoke it never noticed. |
| `Module:FootballQueries/Fields` | football's schema (tables, columns, quote rules, filters, categories, sides, aggregates, entry points, `name`). |
| `Module:FootballStatsBlock` / `…Blocks` | football's renderer shim and its block data. |
| `Module:SeasonTable` | **shared**: the rows of a "season by season" table. `new(Queries, declaration, name)`; the declaration is what differs between sports and is written in the sport's own binding. |
| `Module:FootballSeasonTable` / `Module:BasketballSeasonTable` | those bindings. |
| `FootballSeasonSquad`, `FootballPlayerStats`, `FootballDate` | standalone football modules built on the query module. |
| `Module:SeasonTrophies` | the three-sport season trophy lists; its own small module by design. |

**A new sport is a schema page and two shims.** Error messages carry the schema's
`name`, which is why football's still read `FootballQueries: …`. What a schema
declares beyond football's original shape (added 2026-09-23 for basketball, football
byte-identical throughout):

- **`tables[T].grain`** - `'game'` (at most one row per game: the game, its
  competition, its referees) or `'perPlayer'` (several rows per game: football's
  events, basketball's per-player summaries). A query may join at most one
  `perPlayer` table. A summed column's grain is its table's: a game-column sum
  (goals for) refuses a `perPlayer` join, a per-player sum (basketball points) is
  event grain and its table is joined even when no filter reaches it, with the side
  constraint inside its CASE. An event-grain count with no `perPlayer` table joined
  is refused - it would be a game count wearing the wrong label.
- **`roles.sideFilter` + `sides.maccabiValue`** - the filter a template uses to ask
  for a side (football `מכבי`, basketball `האם עבור יריבה`) and the value that means
  Maccabi's. A leaderboard with no side asked for narrows to Maccabi's through it. The
  logic used to inject the football name and value itself, which on basketball would
  have ranked the OPPONENT's players.
- **`roles.narrowFilter`** - the filter a leaderboard narrows its rows by (football
  `מספר אירוע`); absent means nothing is narrowed.
- **`kind = 'competitionCategory' | 'resultWord'`** are both the `choice` handler:
  `choices` maps a word to a ready SQL condition, `tables` are joined for every
  choice, and `''` means "no condition" (basketball's `רשמי` tab). The last
  hardwired table name in the logic went with this.
- **`filters[…].stripPrefix`** - a list built from category members carries the
  namespace (`כדורסל:Name`); without stripping it, IN matches nothing and every box
  renders empty with no error.
- **Blocks** may declare `sum` on a box (sum a column instead of counting rows; no
  more link then), `keepZero` (basketball shows zero rows) and `emptyText` (printed
  on an empty tab). Football's blocks declare none.

`tests/test_perplayer_schema.lua` hands `new()` a basketball-shaped schema and
proves these without a basketball data page.

### Basketball, live 2026-09-23: `Module:BasketballQueries` + `Module:BasketballStatsBlock`

Every basketball leaderboard (485 pages: 325 referees, 75 seasons, 46 opponents and
competitions, 22 courts, 9 categories, the portal) went through ONE query template,
`כדורסל/סטטיסטיקה/שיאנים לפי אירוע`, once per tab: 16 queries on the portal, 32 on a
season or opponent page. Its `#cargo_query` is now
`{{#invoke:BasketballStatsBlock|leaderboardTab|בלוק=leaderboards|תיבה={{{אירוע}}}|…}}`
(previous revision 202599). The box templates kept their signed `<shtml>` tab strips
through this step and lost them later the same day - see **The whole box
(`leaderboardBox`)** below, which is what the eight of them run now.
The first call on a page primes every box in the four tab categories from
one grouped query and stores each tab's ranking as data in a page variable keyed by
the filters and the limit; a tab's rows are expanded only when read. Any other
category (`ברירת מחדל`, `יתר-רשמיים`) is primed on its own when asked.
`קטגוריה:שחקני כדורסל` 1.3 → 0.8 s, `קטגוריה:כדורסל/סנטרים` 1.9 → 0.75 s,
`פורטל שחקנים` 3.3 → 2.6 s.

What the schema had to say that football's did not, each measured: every text
column KEEPS quote characters (Opponent has 118 apostrophes and 123 quote marks);
the player list arrives quoted, prefixed and with a trailing `""` from the
category-members helper (`quoted = true, stripPrefix = 'כדורסל:'` - without it
every category page rendered empty with no error); a NULL stat on a matched row
is 0 (`sumMissingAsZero` - older seasons record no blocks or steals, and the
template's COALESCE showed those players with 0); `רשמי` means no condition and an
absent category means Official = 1 (the wrapper passes `ברירת מחדל`); a
parenthesised choice inside `CASE WHEN` is refused by Cargo ("WHEN()"), so
`יתר-רשמיים` is a plain AND chain.

**What is NOT byte-identical, and never can be:** tied players. MySQL returns a tie
in arbitrary order - it differed between two renders of the same page - and fills
the last places of a cut tab with arbitrary members of the tie; the module orders
ties by name. `compare_basketball_tabs.py` sorts tied runs by name on both sides and
masks the names of a boundary tie (same record, same count), then compares byte for
byte; the "עוד..." link's query string is normalised too (Cargo built it from the
template's raw SQL text). 16/16 sample pages across every family passed that.

Cost, measured: the grouped query is ~0.2 s plus ~12 ms per conditional sum over
57k rows, so priming 32 sums costs ~0.55 s and 48 would cost 0.8; expanding the row
template (an existence check per player) for tabs the page never shows cost more
than the query, hence data in the variables and rendering on read.

**The numbers (`cell`), live 2026-09-23.** `כדורסל/סטטיסטיקה/סך אירועים` answered
one number per call - 32 queries on a season or opponent page, 475 pages. Its
query is now `{{#invoke:BasketballStatsBlock|cell|בלוק=numbers|תא={{{אירוע}}}|…}}`
(previous revision 202748). The first call computes every cell of the block in the
tab categories and stores the numbers keyed by the filters; later calls read. Two
queries, not one: points are a GAME column (`Basketball_Games.TotalPointsMaccabi`,
or `…Opponent` under `עבור יריבה`) and the layer rightly refuses to sum a game
column in a query that joins the per-player table, so game-level cells and
per-player cells prime separately (`sides` on a cell names the column per side and
keeps the side filter out of the game query). NULL prints `0`, as the template's
COALESCE did. Season page's numbers 0.32 → 0.17 s, opponent page's 0.51 → 0.31.
Gate: the tab gate with `--template … --candidate …`, 12/12 pages identical - and
here identity proves the invoke ran, since a missing number breaks every `#expr`.

**The counts (`games` block), live 2026-09-23.** `כדורסל/סטטיסטיקה/כמות משחקים` - a
COUNT(DISTINCT game) per call, 885 pages including every basketball player page
(`פרופיל כדורסל`'s "was head coach" and "was captain" checks) - is now
`{{#invoke:BasketballStatsBlock|cell|בלוק=games|תא=…}}` (previous revision 202600).
The wrapper turns the template's `תוצאה` into the cell: הפסד → `הפסדים`, any other
word → `ניצחונות` (its `#בחר` did the same), none → `משחקים`. Its own block, not a
part of `numbers`: the captain filters reach the per-player table, which is fine
for a count and refused for a team-points sum. The captain filters are `text`
filters with `extra` constants (`Team = N AND IsCaptain = 1`) and `constrainsSide`,
or the side default would contradict the opponent's captain. Gate: 10 pages of
every family incl. a player page, identical.

**What the review of the two blocks changed** (all four fixed before the merge, each
with a mutation): the opponent side is decided by the layer's own rule
(`Queries.asksForOpponent`), not by comparing the argument to a literal `כן`;
`narrowShared` injects no Maccabi side when a shared filter already carries
`constrainsSide`, so the captain filters are not contradicted; `cell` refuses a grain
whose cells do not agree on having sides ("mixes … cells with and without sides")
instead of trusting the first cell; and `compare_basketball_tabs.py --template` now
requires `--candidate`/`--against`, since a candidate derived from the leaderboard
template would otherwise be rendered under another template's title and compare nothing.

**The whole box (`leaderboardBox`), live 2026-09-23.** The eight box templates
(`כדורסל/סטטיסטיקה/שיאני …`, 132 pages: 75 seasons, the player categories, the
portal, opponents and competitions) carried their tab strip as signed `<shtml>` -
hidden radio inputs whose `name` groups the tabs - and handed only each tab's
inside to `leaderboardTab`. Each is now ONE invoke
(`{{#invoke:BasketballStatsBlock|leaderboardBox|בלוק=leaderboards|תיבה=…|כמות=…}}`,
2.2 kB of markup down to 0.2), and the module emits the title, the strip as a
`<tabber>` and all four panels. Both entry points share `primeRanking`/`readRanking`
and key their variables alike, so a page part-way through the conversion still
primes once - which is what let the boxes be switched one at a time.

Why it was worth doing beyond the markup: `שיאני אסיסטים` had its radios 2-4 in
group `tab-control-bb-appearances` (only tab 1 in `…-assists`), so pressing any of
its tabs left the officials panel on screen as well - two panels, two "עוד..."
links, two tabs lit - and deselected the appearances box's tab. The bot cannot save
inside `<shtml>` ("גיבוב לא חוקי" on a sandbox), so that one attribute could not be
fixed from the repo at all. A `<tabber>` has no groups to get wrong, so the defect
is gone by construction rather than by a careful edit.

Two rules the conversion had to respect: the tab LABEL is plain text (TabberNeue
builds the panel id, and so the address bar, from it) and the icon comes from the
skin keyed on that label, `atoms/tabber-converted.less`; and `איבודים` and `עבירות`
hardcode `כמות=5`, ignoring the page's `כמות שחקנים`, which the generated templates
keep. **One visible change:** the international tab's glyph is now the globe the
skin maps `בינלאומי` to, where the old strip drew a euro sign. Everything else is
pixel-identical (checked with Playwright, tab by tab).

Gate: `compare_basketball_boxes.py`. The markup changes by design, so it compares
what the box SHOWS - the four panels in order, their players, records and link -
across the whole page, one box template swapped at a time (TemplateSandbox takes one
page). Two traps it was built around: "does the page invoke the module" is vacuous
here, because the live templates already did through `leaderboardTab`, so the
candidate is detected by the `tabber-converted` it alone emits; and a page shows 4,
6 or 8 of the boxes, so replacing one it does not transclude must be reported, not
counted as a pass. `--selftest` points every candidate at the appearances box, so the
run must fail. And once the switch has shipped, the live template IS the candidate and
the plain mode compares a thing with itself: `--against` renders the text each box
replaced (from `switch_template_prod.py`'s record) as the sandbox side instead, which is
the only comparison that still means anything. Its self-test has to patch both namings
(`תיבה=` on the candidate, `אירוע=` on the old template) or it changes nothing and
"passes". Result: 0 of 32 differ across five pages, `--selftest` reports all 32. Render time is barely touched (~0.02 s
per box; the query count was already one per page) - this one bought correctness.

**`#vardefine` trims its value** (Variables registers it without SFH_OBJECT_ARGS, so
the parser PHP-trims every argument). A stored value that begins or ends with
whitespace - a newline included - loses it. The first version of `leaderboardTab`
stored `<link or nothing>\n<rows>`, so a tab with no link (fewer players than the
limit) lost its first newline and its TOP PLAYER came back as the link: live on
small pages (a court with two cup players) until review caught it; the 16 gate
pages all had five or more players per tab. Now the line is `more=…`, the stub
trims like the parser, a mutation restores the bare line and is killed, and the
gate sample includes pages with fewer players than the limit
(`.claude/tmp/bb_small_pages.txt`). The other side filter word: basketball's
`האם עבור יריבה` selects the opponent only for `כן`; the template it replaced flipped
on ANY value. No caller passes a value today; another word would silently mean
Maccabi - the layer's one known "guess" - so a caller adding one must add it to
`sides.opponentValue` first. **Deploying a schema and the logic
that reads it:** production publishes one page at a time, so the schema went out
first carrying the keys the OLD logic read as well (a transitional copy, removed
the moment the new logic was live); no page ever saw a mismatched pair.
Publish order: the shared pages, then a sport's schema, then its shims -
`deploy_modules_prod.py --only` exists for that staged rollout, and each shim was
gated on production first with `compare_module_swap.py` (live module vs the repo
file through TemplateSandbox, byte for byte, on a page of every family).

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
`.claude/lua_modules_design.md` §2b.

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
uv run python infra/lua_modules/verify_entry_points.py
uv run python infra/lua_modules/verify_entry_points.py --selftest
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
lua5.1 infra/lua_modules/tests/test_football_queries.lua   # needs: apt install lua5.1
luac5.1 -p infra/lua_modules/*.lua                          # syntax only
```

The suite asserts generated SQL, so it is fast and needs no wiki. **Confirm it
fails before trusting a pass** — and not by picking two mutations, which is how
10 of 18 escaped once:

```bash
uv run python infra/lua_modules/tests/mutate.py   # 83 mutations, 0 may survive
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
uv run python infra/lua_modules/deploy_modules.py --dry-run   # repo -> local wiki
uv run python infra/lua_modules/deploy_modules.py
uv run python infra/lua_modules/smoke_test_local.py           # module vs Cargo
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

### Main-referee pages: block `referee-main`

`תבנית:שופט כדורגל/שופט ראשי` (~440 referee pages) called four wrappers
around the same `עיצוב חדש` boxes with `שופטים=<name>` (`Refs IN ("name")`),
now `{{#invoke:FootballStatsBlock|leaderboards|בלוק=referee-main|שופט=…}}`.
Derived from `season` with the existing `שופט` filter (`Refs = "name"`, the
same rows). Two differences read from production's wrappers: **only the first
box carries `id="שיאנים"`** (the table of contents' anchor) - so the renderer
now lets a box carry its own `boxOpen` - and the cards box is **שיאני
צהובים**.

`compare_referee_main_leaderboards.py` reuses the stadium gate. Before
publishing only the block data can be overridden, so the id is checked by the
stub tests and by `--full`. Outside the section `--full` allows exactly one
difference: a referee who was also an assistant shows both sections in a
tabber, and the four new tabbers **renumber** the assistant section's
tabbers after them (`tabber-1` → `tabber-5`), which only moves a saved link
to one of those tabs.

**LIVE 2026-09-22** (template revision 206183). Sandbox gate over 149 referees
(88 in order + 61 chosen: 46 quoted names, the 10 busiest, both roles, no
official games), `--full` over 14; section ~0.6 → ~0.1 s. One `--full` FAIL
(משה אשכנזי) was a production parse flake: two old renders and the new one
were identical on rerun. The comparison's link normaliser had to learn that
an apostrophe inside a name (`ג'ורג' אשקר`) is not a SQL string delimiter.

## The season-by-season table: `Module:SeasonTable`

**Shared by the sports since 2026-09-23.** Football's 211-line module became a
binding: the logic is `Module:SeasonTable`, and each sport's page carries only a
declaration - the two base columns, the result columns, the catalogue, the link
shapes, the entities, and the optional competition-grouping map. The football
section below describes the behaviour; it is now that module's, and 17 football
tests pass unchanged through the move (byte-identical on production, the only
difference being a leaderboard tie two *unchanged* renders also swap).

**Basketball, live 2026-09-23** (opponent pages). `יריבת כדורסל/הצגת סטטיסטיקה
עונתית`, 24 pages: one `#cargo_query` for the pairs plus `כמות משחקים` twice per
row - 84 queries on `כדורסל:הפועל תל אביב` - became one invoke and ONE query.
That page: walltime 1.93 → 1.42 s, 47,885 → 33,061 nodes, and the table went
from 34.7% of the profile (557 ms, its third-largest entry) to outside the top
ten. Gate: `compare_opponent_season_table.py --sport basketball --full`, 24/24
with the full three-way check, `--selftest` correctly failing.

What basketball's declaration has to say that football's does not:
- **two result columns, not three** - there is no draw. Each column is named by
  its `תוצאה` word and compiled through the schema's own choices
  (`Queries.choiceCondition`), so a column and a filter by the same word cannot
  drift apart.
- **the `כדורסל:` namespace** in both link shapes (`כדורסל: עונת %s`), which the
  row template wrote out per row.
- **an explicit `limit`**, because basketball's schema declares no
  `defaultLimit`. Football's table was being silently cut at Cargo's 100 (three
  clubs lost their oldest seasons); basketball's largest opponent has 86 pairs,
  so nothing is cut today - and the query layer now raises rather than truncate
  when a result reaches the limit, so it cannot start losing rows quietly.

**The referee families, live 2026-09-23**: 191 head-referee and 276
assistant-referee pages, both templates now one invoke.
`כדורסל:ירון זריף (שופט)` 0.65 → 0.47 s measured at the same moment (the saved
previous template put back through TemplateSandbox), same 31 rows; the table
leaves the profile entirely. Gate `compare_referee_season_table.py --sport
basketball`: 191/191 and 276/276.

Those pages need their own gate for the reason football's did: a row is
identified by its whole competition CELL, because when the grouping page is
missing the row shows the GROUPING name instead of the competition, so the cell
text stops matching the database. Two traps found while building it:

- **The grouping name is a competition like any other and must be linked through
  the sport's own shape.** A review caught this before the switch: bare, every
  such row would have linked `גביע המדינה` and `ליגת העל` to FOOTBALL's ns-0
  articles, since basketball's are `כדורסל:…`. The missing-page fallback still
  prints the bare grouping name, as the row template did.
- **MediaWiki normalises `כדורסל: X` to `כדורסל:X`.** The module emits the
  template's spacing; the gate compares against rendered link titles and asks the
  API about them, both normalised. Written with the space, the gate's oracle
  matched nothing and accused a module that was right.

Basketball is simpler than football in one respect: both referee filters sit on
`Basketball_Games` (`MainReferee` text, `AssistantReferees` HOLDS), so there is
no join to make.

The gate takes a sport. `SPORTS` at the top of
`compare_opponent_season_table.py` holds each one's templates, module, games and
catalogue tables, result columns, namespace (football's opponents are articles,
basketball's are ns 3003), known scratch pages, and self-test pair. Basketball's
uncatalogued competitions are read from the data rather than written down, since
that list grows.

## The football section, now `Module:SeasonTable`'s behaviour

`תבנית:יריבת כדורגל/הצגת סטטיסטיקה עונתית` listed (season, competition) pairs
with one `#cargo_query` and ran `כמות נתוני משחק` three times per row: ~300
queries, 4.35 of `הפועל תל אביב`'s 7.2 s. The template keeps its section
wrapper; only the `#cargo_query` became
`{{#invoke:FootballSeasonTable|rows|יריבות={{{יריבות לשליפה|}}}}}`, which runs
two queries (the pairs with `SUM(CASE WHEN ResultOpt = N …)`, through
`FootballQueries.query` for the opponent list's strip/escape rules, and the
Competitions catalogue for the order). An empty list renders no rows - the
layer reads an empty filter as "no filter", which would list every game.

Three changes, decided by Roee 2026-09-22: **every row** (no limit meant
Cargo's 100: הפועל ת"א showed 100 of 126, מכבי פ"ת 100 of 114, מכבי חיפה 100 of
108); **league, cup, the rest, then name** inside a season (seasons keep the
database's `Season DESC`); **real results for ידידות and גביע מלצ'ט**, which
have no Competitions row and so counted 0/0/0 through the catalogue join.

`compare_opponent_season_table.py`: NEW against a direct Cargo query written
apart, the order against a separately written sort, OLD against NEW allowing
only the three changes (truncation decided from the direct count, not the OLD
row count). `--selftest` must FAIL. Errors are looked for in the table only:
the largest clubs' all-games list already shows "יותר מדי קריאות ל#זמן" (too
many `#time` calls) on production - a separate, untouched bug.

**LIVE 2026-09-22**, switched with `switch_template_prod.py` (previous revision
166428): 59-page sandbox sample (38 quoted names, friendlies, several names,
no games, the 3 truncated) and 7 whole pages all passed; 299 callers purged;
הפועל תל אביב 7.2 → 2.6 s, בית"ר ירושלים 6.3 → 2.6 s, 0 script errors.

**Referee tables, LIVE 2026-09-22** (`…/שופט ראשי` rev after 167772, `…/עוזר שופט`
after 167765): `rows|שופט=…` or `rows|עוזר שופט=…` (exactly one filter) with
`קישור מפעל=מרכז`. Their rows linked the competition through
`Football_Competitions_Map` (`Names HOLDS "C"`, limit 1, no order): nine names
sit in two map rows, and which one that returns follows MySQL's HOLDS join -
ליגת העל gets `הליגה הראשונה בכדורגל`, גביע המדינה itself. Grouping-first and
storage order (`_ID`) each broke some links (caught by the OLD-vs-NEW cell
check), so the module runs the same lookup once per DISTINCT competition:
2 + K queries per table instead of 1 + 4N. Cell rule: `{{#קיים: X |[[X|C]] |X}}`
- a missing grouping page shows X, a competition the map lacks (גביע מלצ'ט)
shows nothing, as before. `compare_referee_season_table.py` (61 main + 20 of
347 assistant pages, all ok). אלון יפת 1.97 → 0.73 s, משה אשכנזי 3.3 → 1.2 s.

**Production's firewall refuses Lua containing `or … ==`** in any request body
(urlencoded or multipart) as SQL injection - a TemplateSandbox render or a
module publish carrying it gets a 302 to abuse.spd.co.il. Write such
conditions as separate `if` branches; diagnose with `allow_redirects=False`.

## Player pages: `Module:FootballPlayerStats`

A player page's statistics column (`פרופיל כדורגל/הצגת עמודת סטטיסטיקה/שחקן`,
five tabs × `…/שחקן/הצגה`) was ~2.3 of its ~3.5 s: 15 query templates per tab,
75 queries. Only `…/הצגה` changed: each `#vardefine`'s query call became
`{{#invoke:FootballPlayerStats|value|שחקן={{#var: שם להצגה}}|קטגוריית מפעל=…|תא=…}}`,
every `#vardefine` and all formatting kept. The first value for a player runs ONE
query for all 13 outfield numbers of all five tabs and stores them in page
variables; the first keeper number runs the two keeper queries - 3 a page.

Mirrored per number (checked on production 2026-09-22): appearances /
substitutions / clean sheets count games CONTAINING the events (the templates
listed games grouped by page and counted them); goals … losses count event
ROWS (10 player/game pairs have two appearance events, so wins can exceed
appearances there, as before); conceded = ROUND(SUM(ResultOpponent)) over the
appearance rows of non-technical games (`Technical = -1`), EMPTY when none;
penalties conceded = a self-join (ge1 the keeper's appearance, ge2 the
opponent's SubType 35), 0 when none. Standalone module with raw queries: the
layer refuses a sum over event rows and has no aliases, and keeping the layer
untouched kept every other page untouched. No duplicate pages, titles with
commas or duplicate Games_Referees rows exist, so the joins the templates used
and this one skips cannot change a count.

**Cargo refuses `CASE WHEN (`**: its field parser reads `WHEN (` as a call to
a function WHEN() ("פונקציית ה־SQL בשם WHEN() אינה מותרת"). Conditions are AND
chains without parentheses.

Gate: `compare_player_stats.py`, batched - 4 players' columns per
`action=parse` separated by markers, live `…/הצגה` vs the candidate through
TemplateSandbox (the module published first, inert), each column byte for byte
in the keeper view (it holds every row), each player's official appearances
against a direct Cargo count, NEW must list the module among its templates.
760/760 identical (~48 min); 8 whole pages byte-identical.
`player_pages.py` reads the players' column names 50 pages per request.
**LIVE 2026-09-22** (previous revision 174539): ערן זהבי 3.9 → 1.5 s, אבי כהן
3.5 → 1.6 s, 0 script errors.

### Profile template trims, LIVE 2026-09-23

Four output-identical edits: the photo gallery rendered once into the variable
`גלריית תמונות` (both `/שחקן` and `/איש צוות`; the second template reuses it via
`#varexists`), the four keeper cells defined only under `#תנאי האם שוער`, the
shirt-number query once, the seasons-played query once for the 6 player trophy lists
(`|עונות=` on `/הרכבת רשימת זכיות/שחקן`). `make_profile_candidates.py FIX` derives
each candidate from the live text; `compare_profile_template.py FIX` renders a
stratified sample (all player+coach pages, keepers, staff-only, with/without gallery,
no photo, random) old vs new, byte for byte, `--selftest` must fail. Paired
before/after timings (`OLD/NEW` alternated, median of 3) are the only trustworthy
saving - one run per page on prod is noise at ±0.15 s.

Measured: player+coach pages 0.3–1.0 s faster (the gallery was built 4×), others
~0.1–0.25 s. **The second gallery render was cheap** (file lookups cached from the
first), so timing a gallery alone overstated that fix ~3×.

**Trap - page-wide arrays.** Every trophy-list template writes the global array
`עונות`, and `/הצגת פרטי שחקן` counts it only redefining it when its own seasons
list is non-empty. So for a player whose `קבלת רשימת עונות/שחקן` list is empty, the
shown "seasons" number and the category `שחקני כדורגל ששיחקו N עונות במכבי` come
from whichever template last wrote the array - today the last staff trophy list,
whose `<em>ללא תוצאות</em>` counts as 1 (אורי עזו shows 1; he played 2). Skipping
the staff lists for player-only pages changed that number, which is why they still
run. Open, for Roee to rule.
## Game dates without `#time`: `Module:FootballDate`

ParserFunctions gives a page ~6000 bytes of `#time` format strings. The shared
date template (`המרות/המרות תאריך/תאריך מלא לפורמט הצגה`, linked form
`[[d "ב"F|j "ב"F]] [[Y]]`) spends ~25 of them, so ~240 dates; past that every
date prints "יותר מדי קריאות ל#זמן" (no tracking category - you only see it).
The opponent all-games row (`יריבת כדורגל/הצגת כל המשחקים/הצגת משחק`) called
it once per game: הפועל תל אביב (242 games) lost its 2 oldest dates, מכבי חיפה
(233) was 7 games away. Stadium, coach, player and referee pages were checked
at their largest (בלומפילד, אברהם גרנט, מיקו בלו; max referee 106) - no error.

`{{#invoke:FootballDate|full|{{{Date|}}}}}` builds the same text from the
digits and a month table; anything but `YYYY-MM-DD` (empty included) goes back
through the template. The shared template itself is untouched - it sits on
18.5k pages incl. files and other sports. Per-row `#invoke` costs nothing
measurable (242 rows: 2.82 → 2.74 s, within noise).

Gate `compare_opponent_dates.py`: `dates` renders every distinct
Football_Games.Date both ways (OLD in batches of 150, under the budget; NEW
via TemplateSandbox with the unsaved module) - 3509/3509 identical, selftest
with two months swapped caught 745; `pages` compares rows only (the page's
leaderboards differ from themselves between two unchanged renders).
**LIVE 2026-09-22** (row template previous revision 202192), 301 pages purged,
Hapoel 0 errors.

## Season trophy lists for three sports: `Module:SeasonTrophies`

**The first module serving more than one sport.** `כדורגל:עונות`, `כדורסל:עונות`,
`כדורעף:עונות` and `עמוד ראשי` asked `<ענף>/שליפות/רשימת זכיות לעונה |עונה=X`
once per season - ONE #cargo_query each: 102 + 75 + 55 = 232 queries on `עונות`,
0.8 of its 1.4 s. Now `{{#invoke:SeasonTrophies|list|ענף=כדורגל|עונה={{{עונה|}}}}}`:
the first call for a sport queries all of its winning seasons and stores each
season's list in a page variable, so a page runs one query per sport.

Conventions this sets for the next multi-sport module (design review 2026-09-22):
- **The file stays in `infra/lua_modules/`** - a second directory means a second
  deployer, a second git-clean check and new CI globs that fail silently when missed.
- **One entry point, the sport as a Hebrew argument**, validated against an in-module
  `SPORTS` table: an unknown `ענף` raises from a line a mutation can flip. One function
  per sport would put the sport in two places and leave the guard to Scribunto.
- **Sport keys are `כדורגל` / `כדורסל` / `כדורעף`**, the wiki's own spellings - the
  contract every later multi-sport invoke should use.
- **`SPORTS` lives in the module**, not a `/Sports` loadData page: three rows rebuild in
  microseconds, and a data page costs a second wiki page, deploy ordering and the
  loadData proxy shape. Aliases are fixed `a`/`c` for every sport (they never reach the
  output); `excluded` is a list so quoting stays in one place.
- **Page variables are prefixed with the module name**, as `FootballPlayerStats` does.

Two Cargo facts the parity depended on (measured on production):
`#cargo_query|no html` joins rows with a comma and **two** spaces (`A,  B`); with no
`order by` Cargo orders by the first field, so the old lists were alphabetical by
competition and the module orders by it explicitly - storage order would pass the gate
by luck and flip on a recreateData. Basketball has ~125 winning rows, so Cargo's silent
100-row default would have cut it: the module asks for 500 and raises if it reaches it.

Gate `compare_season_trophies.py`: `seasons` renders every season the sport's page
actually lists (read out of the LIVE page - basketball and volleyball build their lists
from categories, not a query), old vs new, batched, byte for byte; the selftest compares
the lists against the wrong seasons and must disagree; NEW must name the module in
`prop=templates` or an ignored sandbox override would pass silently. `pages` compares
the season rows of the five caller pages. **232/232 seasons identical.**
**LIVE 2026-09-22** (previous revisions 163471 / 175759 / 143324): `עונות` 1.44 → 0.79 s,
`כדורגל:עונות` 0.60 → 0.37, `כדורסל:עונות` 0.53 → 0.32, `כדורעף:עונות` 0.32 → 0.16,
0 script errors.

## `switch_template_prod.py`

The last step of a rollout, runnable without a paste: `apply` refuses unless
the live template's sha1 is the one the comparison ran against, saves the
previous text under `.claude/tmp/template_switches/`, writes multipart and
reads back; `revert` refuses if the template was edited since; `purge`
purges the callers through the bot session (no anonymous 30-a-minute limit).
Roee allowed exactly this command in the session permissions (2026-09-22).

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
