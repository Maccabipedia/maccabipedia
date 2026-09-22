# Football season pages — making them cheaper to render

The 104 `עונת …` pages render through `תבנית:עונת כדורגל`. A cold parse on
production took ~4 s for 2024/25 and ~6 s for 1966/68 (September 2026). The
leaderboards were converted first (`Module:FootballStatsBlock`, block `season`
— see `.claude/football_queries.md`, "Leaderboards"). This file covers the rest,
and the tools in `infra/season_pages/`.

## Where the time goes (production, per block, 2024/25 / 2005/06 / 1985/86 ms)

| block | cost | why |
|---|---|---|
| games list | 1308 / 1028 / 2000 | per game: 3 DPL galleries for icons, a DPL title-win check, a ticket check of up to 39 `#ifexist` |
| squad | 712 / 553 / 517 | one query per player (42 on 2024/25) |
| מספרים עונתיים | 545 / 562 / 550 | 8 queries per tab × 4 tabs |
| leaderboards | ~0.2 s | already one query |

Old seasons pay most for the ticket check: a missing `X.jpg` makes
`תבנית:תיקון פורמט תמונה` try 38 case/extension variants (1966/68: 2,548
expensive-function calls per parse). The poster check costs nothing: in
production's row template it sits inside an HTML comment, so it never runs -
which is also why the poster icon never shows. (Rendered on its own, outside
that comment, it measured ~1.6 s; that number describes nothing live.)

## The local seed: one season per era

`generate_season_manifest.py football <season>` also pulls the file pages the
games-list icons depend on (press/photos/programme category members, the ticket
by prefix, the team photo), the day pages the game rows link to, and the
season's collectibles category. Without them the local wiki shows none of those
icons and a before/after comparison of them compares nothing.

Seeded seasons (local only — the CI fixture is unchanged): **1939, 1966/68,
1993/94, 2011/12, 2023/24, 2024/25**. Rebuild with the README's "Seeding a full
season" per manifest, then `scripts/recreate-cargo-tables.sh`, which:

- runs its fast pass with foreign images off, lists the pages that fail there
  (`getSha1() on bool` — pages using a local `קובץ:` page) and re-stores them
  with images on;
- ends by refreshing links **after** Cargo is populated: a press clipping's file
  page picks its `עיתונות למשחק מה-<date>` category from a Cargo lookup of the
  game, so links refreshed on an empty Cargo leave every press icon missing.

Two traps found the hard way (2026-09-19):

- **The local wiki carried ~40 templates edited by an old "local perf
  experiment"** (including the games-list row, `הצגת גלריה לפי קטגוריה` and
  `תיקון פורמט תמונה`). Imports never overwrite a newer local revision, so a
  reseed does not clean them. Compare local templates to production by sha1
  before trusting any local comparison, and restore the drifted ones.
- **Rendering a games list locally hammers production.** The local wiki
  resolves files through production's API, uncached, and the image helper tries
  up to 39 names per ticket: one local capture held ~550 open
  connections to production. Do not render games lists or whole season pages
  locally in bulk; verify those on production, paced (`season_api.py`: 3 s between
  renders, back off on 508 — production's host resource limit).

## Change 1 — games-list icons without galleries

`convert_game_row_icons.py` replaces the three `{{#תנאי: {{הצגת גלריה לפי קטגוריה
…}} |icon}}` tests in `תבנית:כדורגל/רשימת משחקים/הצגת משחק` with
`{{#ifexpr: {{PAGESINCATEGORY:…|all|R}} > 0 |icon}}`. Nothing else changes.

- `compare_game_icons.py` — both tests side by side for every game on production:
  3,505 games, 10,515 checks, 0 disagreements. `--selftest` must fail.
- `compare_games_list.py capture/diff` — the rendered games list before and
  after, byte for byte. Production's rendering is deterministic. Run it on
  production only (see the trap above).

The programme icon has never shown: the template checks `<game>/תוכניית משחק`,
while programmes are categorised under the game's own category and
`קטגוריה:תוכניות משחק`. The change keeps that behaviour; fixing it is a
separate, visible decision.

**Rollout:** re-run `compare_game_icons.py` just before (category counts can
drift from real membership over time; the sweep proves agreement only when it
ran) → `compare_games_list.py capture before` → edit the one template (keep the
old text) → `capture after` → `diff before after` must be empty. The row
template is also on **`עמוד ראשי`** (97 transcluders: 96 seasons + the main
page); the main page is not deterministic enough to byte-diff, so look at it
after the edit.

**The title-win check** (`{{#dpl: |category=משחקי זכייה בתואר (כדורגל)
|titlematch=…}}`) passed the Cargo-encoded `PageName` straight to `titlematch`,
so no בית"ר title win showed its trophy. Fixed on production 2026-09-22
(revision after 206134) by decoding `&quot;` as the icons above do; verified
with TemplateSandbox on the six seasons holding such a game (1946/47, 1976/77,
1979/80, 1995/96, 1998/99, 2024/25): 6 icons restored, none added elsewhere.

## Change 2 — מספרים עונתיים from 2 queries instead of 32

Blocks `season-results` (wins, draws, losses, goals for/against, clean sheets)
and `season-cards` (Maccabi's yellows 71, reds 72/73) in
`Module:FootballStatsBlocks`. Two queries, not one: goals are a SUM of a game
column and the cards join the events table, which would multiply them.

`convert_season_numbers.py` makes the container prime both blocks and each tab
read its eight numbers with `value`; every bit of formatting (percentages,
`#number_format`, per-game ratios, hide-at-zero) and the tab strip stay in the
templates, so the output must be **byte-identical**. `--sandbox` writes the pair
under `/ארגז חול`; `compare_season_numbers.py` renders old beside sandbox.

**Rollout, in order:** publish the modules (Gate A, as in football_queries.md)
→ write the two sandbox pages on production → `compare_season_numbers.py --wiki
prod` over every season → edit the **container first** (priming alone is
harmless), **then** the tab, back to back → check. Revert in the reverse order:
the tab first, or it reads values nothing primes.

**Once the numbers switch is live, the module rollback changes.** The general
rule (republish only `Module:FootballStatsBlock` from the previous commit)
would now break every season page: the old `prime` renders rows, and these
blocks have none (`ipairs(nil)`). Revert the tab, then the container, and only
then the module.

## Change 3 — the ticket icon without the 39-name search

Each row asks `{{תיקון פורמט תמונה}}` whether a ticket image exists; that
helper tries the exact name and then 38 case/extension variants, each an
`#ifexist`. A season whose tickets are missing pays ~39 lookups per game.
Measured on production: the check alone costs 296 ms (2011/12), 735 ms
(1993/94), 1,251 ms (1985/86), 2,057 ms (1966/68 - 2,479 expensive calls).

Of the **2,355** ticket files on production, **2,354 are `.jpg` and one is
`.png`** (`כרטיס משחק 14 באוגוסט 2004.png`); no case variants exist *among
tickets*. MediaWiki does not normalise an extension's case on upload, though,
and the wiki holds 274 `.JPG`, 179 `.jpeg` and 46 `.PNG` files elsewhere - so
the row now tests **four** names (`jpg`, `JPG`, `png`, `jpeg`), as nested
`#קיים` over `קובץ:כרטיס משחק <date>.<ext>`, and stops at the first hit:
**735 ms → 94 ms** per season (median; two names would be 70 ms), with the
same answer for every game sampled. The row only asks whether a ticket EXISTS
(the icon carries no link), so the helper's other job - returning the
corrected name - is not needed here. **The shared helper itself is untouched**: team photos and
posters still use it, as does the commented-out poster line in this row.

Not verifiable locally: with foreign images off, a local `#ifexist` on a file
the local wiki does not hold answers "no" either way, so both sides agree
vacuously. Verified on production instead.

**Rollout (2026-09-20; its scripts were one-offs and are not in the repo):**
old and new test side by side for all 3,506 games (0 disagreements, with a
selftest that had to fail) → the games list of every season captured before
and after the row edit with `compare_games_list.py` → 101/101 byte-identical
→ look at `עמוד ראשי`.

## Change 4 — the squad card's shirt number (correctness, not speed)

`תבנית:עונת כדורגל/הצגת סגל/הצגת שחקן` asked Cargo for the player's number
with `group by=ge.PlayerName` and `order by=COUNT(ge.PlayerNumber) DESC`.
Grouping by the name alone makes `ge.PlayerNumber` a bare column and leaves
the ORDER BY sorting a **single** group, so the number shown was whichever
row MySQL returned first - storage order, which reflects when each game page
was last saved. מיקו בלו 1978/79: the 1978-12-02 game (number 13) has row ID
4,195,261 and the 1979-06-06 game (number 3) has 4,064,234, so the page
showed 3. שגיב יחזקאל 2024/25 showed 29 against a mode of 11.

Now `group by=ge.PlayerName, ge.PlayerNumber` and
`order by=COUNT(*) DESC, MIN(fg.Date) ASC` - Cargo accepts both aggregates in
ORDER BY - i.e. **the number worn in most of that season's games, ties going
to the season's earliest game**. Blank numbers stay excluded, and a player
with no number is still shown without one. **87 of 1,378 player-seasons
changed** (only 213 ever wore more than one number; ties-to-latest would have
changed 94). It is not a speed change: 42 cards cost 374 ms before and 378 ms
after.

**Correction (2026-09-21, found in review):** that query's `COUNT(*)` counts
EVENT ROWS, not games - a game has one row per event, so a number was weighed
by the goals and cards scored in it. The 87 were measured the same way. The
squad module (Change 5) counts `COUNT(DISTINCT fg._pageName)`, i.e. games,
which moves 11 more player-seasons (e.g. אילון אלמוג 2022/23: 8 games in each
of 11 and 29, more events in 29 - by games a tie, so the earlier game's 11).
The card template itself no longer renders on season pages.

**Rollout:** list the expected changes from Cargo (season, player, old, new)
→ capture the squad block of every season with `action=parse&text=` → edit
the card template (keep the old text) → capture again → every difference must
be a number on the list, changing to exactly the listed value, and the
players and their order must be untouched. Run 2026-09-20: 2,451 cards over
101 seasons, 87 numbers moved, all 87 as predicted, nothing else.

## Change 5 — the squad from 3 queries instead of ~90, in a defined order

`Module:FootballSeasonSquad` renders what `תבנית:עונת כדורגל/הצגת סגל` built
from 1 + 5 + 2N queries (the season's players, one per position, then per
card a profile query and a shirt-number query) from **three**: the season's
players with their games, **all** profiles (with Position and MainNumber),
and **all** shirt numbers (most GAMES that season, ties to the earliest game -
see the correction under Change 4). The template keeps its `קפטן בעונה המוצגת` line and
calls the module. The filter template stays: the players portal
(`קטגוריה:שחקנים`) uses it too.

**The card order is the one deliberate change** (decided 2026-09-21). The
templates sorted a position by `MainNumber` and stopped; most old profiles
have none, so their order was whatever MySQL returned - and a different query
returns those ties differently (1926 already did), so no rewrite could keep
it. Now: `MainNumber` ascending, a missing one first (as MySQL placed NULL);
then most games that season; then the name. Wherever MainNumbers differ the
order is today's. It first reproduced today's order with the five position
queries kept (8 queries, 101/101 byte-identical); the defined order saves
those five, only ~5-20 ms, so the reason for it is a meaningful order, not
speed.

Behaviours reproduced on purpose, each with a stub test: the filter's
`&#39;` fix; empty names dropped as `#arrayunique` dropped them (a player
holding two positions would show twice - none does: every profile holds one
position or none); first Profiles row wins (two pages have duplicate
identical rows); only the FIRST player name decides whether the list renders;
a shirt number that equals 0 is hidden (the card's `#שווה` compared it
numerically with its `000` default); the captain matches **FullHebName** with
`"` as `&quot;` (how `format=template` handed it to the card); the `#קיים`
link check; `#arrayprint` trimming each card. No players at all → one query
and an empty shell, where an `IN ()` would raise.

Measured on production, the unsaved module passed as TemplateSandbox text:
the block went **733 → 143 ms (2024/25), 583 → 121 (2005/06), 518 → 102
(1985/86)**. The gate for the reorder: per season, the same positions, the
same cards byte for byte within each, everything outside the cards
byte-identical, and the new order checked against Cargo by separately written
code (fed today's order it must fail - it does).

A production parse can flake: one season once differed in `<p
class="mw-empty-elt">` placement with identical expanded wikitext, and matched
on three reruns. Rerun before chasing a single whitespace difference.

**Rollout:** publish the module (inert: nothing calls it) → render every full
season page with `תבנית:עונת כדורגל/הצגת סגל` overridden through TemplateSandbox:
outside the squad byte-identical to today's (catches a page variable the old
chain leaked and something later read), the squad by the gate above → edit
the template (keep the old text) → look at 2024/25, 1985/86, 1926. Revert:
the old template text; the module can stay.

## Load when switching

Purging in small batches does not pace anything: a template edit invalidates
every page that transcludes it at once, and each page's next view - the
scraper fleet included - is a cold 3-6 s parse. The icons edit hits 97 pages,
each numbers edit 104 (and the container-only moment is the most expensive
variant, 2 + 32 queries). Switch at low traffic, keep the two numbers edits
back to back, and stop on HTTP 508 (production's resource limit).
