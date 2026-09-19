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

## Load when switching

Purging in small batches does not pace anything: a template edit invalidates
every page that transcludes it at once, and each page's next view - the
scraper fleet included - is a cold 3-6 s parse. The icons edit hits 97 pages,
each numbers edit 104 (and the container-only moment is the most expensive
variant, 2 + 32 queries). Switch at low traffic, keep the two numbers edits
back to back, and stop on HTTP 508 (production's resource limit).
