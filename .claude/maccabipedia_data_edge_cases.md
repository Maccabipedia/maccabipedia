# MaccabiPedia data edge cases

The traps in MaccabiPedia's data and in the wikitext/Cargo/Lua path that
reads it: each one has produced, or would produce, a number that looks right
and is wrong. Football first; counts are production, dated. Before you trust
a query, a harness or a rewrite, check it against this list.

The deep reference for names and quoting is
`maccabipedia_structure_knowledge.md` §15; the query layer's own findings are
in `football_queries.md`. This file is the checklist; those are the proofs.

## 1. Quotes: `'`, `"`, and their escapings

**Every column has its own quote rule.** A stripped column queried with the
raw name returns **zero rows and no error** (§15 table):

| keeps `'` `"` | stripped at write time |
|---|---|
| `Football_Games.Competition` (`גביע מלצ'ט`), `.CoachMaccabi`, `.Refs` | `Football_Games.Opponent`, `.Stadium`, `.Season`, `.HomeAway` |
| `Games_Events.PlayerName` | `Competitions.OriginalName` / `CurrentName` |
| `Opponents.OriginalName` (37 names with a quote) | `Stadiums.CanonicalName` |

The stripping is `תבנית:המרות/שם ללא גרש וגרשיים`: it removes `'`, `"`,
`&#34;` and `&#39;` - and **not** the Hebrew geresh ׳ / gershayim ״. So a
normalised spelling (`ביתר ירושלים`) exists only in the games table, never in
a lookup table, and is usually a redirect, not a page title.

**How often (2026-09-22, `Games_Events.PlayerName`):** a double quote in
exactly **one** name (`אמנון חרל"פ`, 14 rows); an apostrophe in **1,580**
distinct names (the transliterated ג' צ' ז' ץ' - `דור תורג'מן`, `חיים חג'ג'`);
a geresh/gershayim in 59; an ampersand in none. Stadiums: 11 page names carry
a quote; one stored stadium name has ׳ (`אצטדיון זדז׳לה`). Test with an
apostrophe name - it is the common case, not the rare one.

**The same value arrives in four encodings:**

| where you read it | what a `"` looks like |
|---|---|
| `{{PAGENAME}}` | `&#34;` (and `'` as `&#39;`) |
| a template argument from `#cargo_query format=template` | `&quot;` - values are HTML-encoded before the template sees them |
| `action=cargoquery` JSON | `&quot;` (Cargo `htmlspecialchars`) - `LIKE '%quot%'` finds nothing: the DB holds `"` |
| `mw.ext.cargo.query` in Lua | the raw `"` |

So a Lua rewrite of a template must re-encode where the template compared an
encoded value: the squad card matched the captain on FullHebName **as
`&quot;`**; the players filter fixed `&#39;` in its output.

A `format=template` value used **as a page name** must be decoded first
(`{{#replace:{{{PageName|}}}|&quot;|"}}`): `PAGESINCATEGORY` and DPL
`titlematch=` take it literally and match nothing. DPL `category=` decodes it,
so the old gallery icons worked while the title-win `titlematch` check hid the
trophy on all 6 בית"ר title wins until 2026-09-22 (card 583). Apostrophes
arrive raw (PHP 7.4 `htmlspecialchars` default), so `'` names were never hit.

**Writing a WHERE by hand:**
- A literal quote works when escaped or single-quoted (`"בית\"ר"`,
  `'בית"ר'`). An **entity** (`"בית&quot;ר"`) raises MWException - Cargo decodes
  entities in the finished WHERE, putting a bare `"` inside the literal.
- That decode makes an unknown entity an **injection**: `x&#x22; OR 1=1 OR ""`
  returned every row. Decode the entities you know, escape, and **refuse any
  `&` that survives** (`Module:FootballQueries` `normalise`).
- Cargo rejects `REPLACE()` in a WHERE: normalise in the caller.
- 11 `Stadiums.CanonicalName` rows are **double-encoded** (`אצטדיון ימק&amp;#34;א`)
  and cannot be matched at all; no game points at them.

## 2. Games with less than you expect

Totals: **3,506** football games (2026-09-22).

| case | count | what it breaks |
|---|---|---|
| no events at all | 51 | a count that joins `Games_Events` loses them - game-level numbers (results, goals for/against) must not join events |
| no Maccabi event | 65 | same, once `Team=1` sits in the WHERE instead of the join |
| technical result | 16 | a result with no play: no lineup, no scorers |
| no `Competitions` row | 82 (`ידידות` 81, `גביע מלצ'ט` 1) | the join is LEFT, so they survive with NULL flags - and vanish from any `Official=1` filter. Official work filters by `Competitions.Official` |
| blank `Stadium` / `Refs` / `CoachMaccabi` | 177 / 258 / 54 | an empty group in any per-stadium/referee/coach grouping |
| `HomeAway` | 4 values (`בית`, `חוץ`, `נייטרלי`, `רדיוס`) + 13 blank | a home/away split that assumes two values |
| seasons with no games | 5 (1921, 1923, 1924, 1937/38, 1943) | a season page or block must render empty, not error (`IN ()`) |

Counts of games and events are dated 2026-09-13 in `football_queries.md`
except the totals and blanks above.

## 3. Players and shirt numbers

**A missing shirt number is the norm in old games.** Of 78,886 Maccabi event
rows, **33,377 (42%) have no `PlayerNumber`**. The wikitext token for it is
`אין-מספר`, which the store maps to blank - `PlayerNumber` is an **Integer**
column, so blank is NULL.

**…except in the duplicated penalty rows, where it becomes 0** (see §4): that
store copies the number raw, and `אין-מספר` in an Integer column is stored as
0. That is 285 of the 305 Maccabi rows with number 0; the real rows beside
them hold NULL. So `PlayerNumber = 0` means "unknown" far more often than
"wore 0" - and the squad card hides a number that equals 0 (its `#שווה`
compared numerically against a `000` default).

**The number a player "wore" in a season needs a rule.** 213 player-seasons
wore more than one. Grouping by name alone and reading `PlayerNumber` picks
whatever row MySQL returns first (storage order): the squad showed the wrong
number for 87 of 1,378 player-seasons. The rule now: most games, ties to the
season's earliest game (`season_pages.md` change 4).

**Profiles:** 807 rows on 805 pages - two pages carry duplicate identical rows,
so take the first row per page. **300 have no `MainNumber`** (sorting by it
leaves their order to MySQL - why the squad got a defined tie-break);
**59 have no `Position`**. `Position` is a list field; today no profile holds
more than one position, but code must not assume it.

**Players without a profile:** 170 of the 929 names with a Maccabi event have
no `Profiles` row. Among them are placeholders, not people: **`לא ידוע`
(42 events) and `(לא ידוע)` (1)**. A leaderboard or a count of distinct players
includes them unless it filters them; a card or a link for them has nothing
to point at.

**One name, both teams, one game:** 9 name/game pairs (`אלון נתן`
1986-05-24: 2 events for Maccabi, 1 against). Every events query must
constrain `Team` - a career total hides the leak, a per-side count shows it.
`Team` is 1/0 in football and basketball but **1/2 in volleyball**.

## 4. Events

- **Penalties write two rows.** `גול-פנדל` stores the goal (3/35) **and** a
  penalty row (8/81); `בישול-סחיטת פנדל` stores the assist (4/44) **and** 8/84.
  Missed/saved penalties are 8/82, 8/83 with no goal row. Counting "all events"
  of a player double-counts every penalty goal; count by EventType.
- **Subtypes are NULL for most events** (118,197 of 149,574): lineup, bench,
  substitutions, captain. `SubType != 33` (no own goals) also drops NULLs, so
  use it only on goals, which always carry a subtype.
- Subtype numbers are namespaced by type (3 → 30-39, 4 → 40-47, 7 → 71-74,
  8 → 81-84, 13 → 131-133, 1/2 → 111/211), so a subtype filter is unambiguous.
  Unknown tokens fall to 30 / 40 and put the page in a tracking category.
- Types in use (2026-09-22): 1 lineup, 2 bench, 3 goal, 4 assist, 5 sub on,
  6 sub off, 7 card, 8 penalty, 9 captain (2,639), 13 disallowed goal (15).
  The store also knows 12 (shoot-out) and 20 (offside), which have **no rows**:
  a shoot-out or offside statistic would read 0 because nothing was entered,
  not because nothing happened.
- Joining `Games_Events` multiplies game rows up to 43x: never join it for a
  game-level number.

## 5. Wikitext, Cargo and Lua mechanics

- **Cargo's silent limit:** a query without `limit` returns at most 100 rows,
  with no warning. Set a limit and treat a result that reaches it as an error.
- `IN ()` with no values is an SQL error, not an empty result.
- `mw.ext.cargo.query`: alias every field (`ge.PlayerName=name`); an unaliased
  dotted field comes back with no key. NULL comes back as `nil`.
- `action=cargoquery` rejects field aliases starting with `_`: `_pageName=page`.
- `#cargo_query` needs `|default=` or an empty result prints "no results" text.
- Parser functions trim their arguments and results. A whitespace delimiter
  in `#arrayprint` is trimmed to nothing and glues the items together - probe
  arrays with a text marker.
- `#arrayunique` drops empty elements; `#arrayprint` trims each item.
- `#ifeq` / `#שווה` compare **numerically** when both sides are numbers:
  `0` equals `000`, `5` equals `05`.
- Lua module output is not re-preprocessed: tags like `nowiki` must go through
  `frame:extensionTag`.
- Scribunto keeps no state between `#invoke`s; one invoke must render a block.
- An `#ifexist` / `#קיים` on a `קובץ:` title checks the local description page
  only - a local wiki with foreign images answers "no" for every file.

## Adding to this file

Add an edge case when it has cost a wrong number, with the count, the date
and what it breaks. Measure it on production (read-only, paced through
`infra/season_pages/season_api.py`) rather than recalling it.
