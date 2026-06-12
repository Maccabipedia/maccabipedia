# MaccabiPedia Structure & Knowledge Base

## 1. Namespaces and Page Prefixes

| Sport | Game Format | Player/Coach Pages | Opponent Pages | Season Pages |
|-------|-------------|-------------------|----------------|--------------|
| **Football** | `משחק: DD-MM-YYYY [Home] נגד [Away] - [Competition]` | `Name` (main namespace) | `Name` (main namespace) | `עונת YYYY/YY` (main namespace) |
| **Basketball** | `כדורסל:DD-MM-YYYY [Home] נגד [Away] - [Competition]` | `כדורסל:Name` | `כדורסל:Name` | `כדורסל:עונת YYYY/YY` |
| **Volleyball** | `כדורעף:DD-MM-YYYY [Home] נגד [Away] - [Competition]` | `כדורעף:Name` | `כדורעף:Name` | `כדורעף:עונת YYYY/YY` |

> **Note:** Football game pages use `משחק: ` with a space after the colon (confirmed via Cargo API). Football player pages, coaches, referees, and stadiums all live in the **main namespace** with no prefix — e.g. `שגיב יחזקאל`, not `שחקן:שגיב יחזקאל`.

> **Warning:** Some team names (e.g. `הפועל ירושלים`, `מכבי רחובות`) exist in **both** main namespace (as football pages) and `כדורעף:`/`כדורסל:` namespace. Always use the sport-specific prefix for volleyball/basketball operations.

Competition pages use the sport prefix (e.g. `כדורסל:ליגת העל`, `כדורעף:ליגת העל`).

## 2. Core Templates

| Sport | Template |
|-------|----------|
| Football | `קטלוג משחקים` |
| Basketball | `משחק כדורסל` (quarter points, optional overtime) |
| Volleyball | `משחק כדורעף` (set-by-set results) |

## 3. Page Purging
After uploading/updating a game, purge all related pages using a **batch purge** (collect a `set[str]`, one `purge(forcelinkupdate=True)` at the end).

**Football** (all pages in main namespace):
1. Opponent page — `Name`
2. Season page — `עונת YYYY/YY`
3. Competition page — `Name`
4. Stadium page — `Name`
5. Maccabi players — `Name` (no `שחקן:` prefix; confirmed `שחקן:Name` does not exist)
6. Maccabi coach + Opponent coach — `Name`
7. Referee — `Name`

**Volleyball** (all pages under `כדורעף:` prefix, confirmed via GH Actions logs + wiki API):
1. Opponent page — `כדורעף:Name`
2. Season page — `כדורעף:עונת YYYY/YY`
3. Competition page — `כדורעף:Name`
4. Stadium page — main namespace (stadium pages do **not** exist on the wiki yet; all purges are skipped)
5. Players, coaches, referees — `כדורעף:Name` (not yet implemented; `VolleyballGame` model does not carry these fields)

Filter maccabistats sentinel values before purging: skip `"Cant found coach"`, `"Cant found referee"`, etc.
Only purge related pages if the game page was actually saved (not skipped).

## 4. Date & Naming Conventions
- Date format: `DD-MM-YYYY` (dashes) in page titles.
- `בית חוץ` parameter: strictly `"בית"`, `"חוץ"`, or `"נייטרלי"`.
- Unknown time (`00:00`) → upload as empty string `''`.
- URLs: `https://www.maccabipedia.co.il/Page_Title_With_Underscores` — no `index.php?title=...`.

## 5. Querying Data (Cargo API)
Prefer Cargo over scraping wiki text.
- **Endpoint**: `https://www.maccabipedia.co.il/index.php?title=Special:CargoExport&format=json`
- **Main tables**: `Football_Games`, `Basketball_Games`, `Volleyball_Games`
- **Explore all tables**: `https://www.maccabipedia.co.il/Special:CargoTables`
- Find game page names by querying Cargo by date and extracting `_pageName`.
- **Two Cargo endpoints exist:**
  - `Special:CargoExport` — allows `_pageName` directly, returns flat JSON arrays
  - `action=cargoquery` (API) — rejects field aliases starting with `_`. Must alias: `_pageName=pageName`. The MCP server handles this automatically.
- **MCP server:** Use `mcp__maccabipedia__query_cargo` — it uses `action=cargoquery` and auto-aliases underscore fields so callers can just write `_pageName`.

### The `Team` integer in player-event tables

The per-player event tables store `Team` as an **Integer** (not a Hebrew string), written by each sport's `#cargo_store` template — the bot never writes the numeric value. Maccabi is `1` in all sports, but the opponent value differs:

| Sport | Table | Maccabi | Opponent |
|---|---|---|---|
| Football | `Games_Events` | `1` | `0` |
| Basketball | `Basketball_Player_Game_Events_Summary` | `1` | `0` |
| Volleyball | `Volleyball_Players_Game_Events` | `1` | **`2`** |

Why volleyball differs: the storing template `תבנית:משחק כדורעף/הזנת אירועי שחקנים` hardcodes `|Team={{#תנאי: {{{האם יריבה|}}} |2 |1}}`, while football's `תבנית:קטלוג משחקים/הזנת אירועי משחק לטבלת אירועי משחק` maps the wikitext tokens `מכבי→1` / `יריבה→0`. The encodings were authored independently and never unified.

All stats consumer templates filter Maccabi rows with `Team=1`, so the mismatch is latent — it only matters for queries that target **opponent** rows explicitly (football/basketball `Team=0`, volleyball `Team=2`). Note a player can have rows on both sides of the same table from stints at other clubs (e.g. ערן זהבי has opponent-row events from his הפועל ת"א years).

### Cargo name fields hold normalized values, not page titles

- `Football_Games.Opponent` (and similar name fields) pass through
  `תבנית:המרות/שם ללא גרש וגרשיים` — quotes/geresh are STRIPPED, so the value
  (`ביתר ירושלים`) is usually a **redirect** to the real page (`בית"ר ירושלים`).
  Resolve via `api.php?action=query&redirects=1` before treating values as titles.
- Title formats for linked entities: football referees `כדורגל:<שם> (שופט)`
  (from `Football_Games.Refs` — football-only field); volleyball halls
  `כדורעף:<אולם> (אולם)`, opponent centers `כדורעף:<שם> (מרכז)`; basketball has
  NO club page (`כדורסל:מכבי תל אביב` is missing on prod, redlinked there too).
- `api.php` accepts POST through the edge proxy (only the `Special:Export`
  form rejects POST) — use POST for batched title queries to avoid 414s.
- Profile templates pick photos with `{{#קיים: קובץ:X}}` — `#ifexist` on a
  `קובץ:` title checks the LOCAL description page only (never foreign repos),
  so a wiki copy needs the description pages imported even when binaries come
  from a ForeignAPIRepo. Each sport's profiles table records the chosen photo
  in `ProfilePicture` (e.g. `Eran Zahavi Profile.png`).

### Where Cargo declarations and stores live (template layout)

- Every `#cargo_declare` lives on a dedicated template under `תבנית:טבלאות מידע/<table name in Hebrew>` (e.g. `תבנית:טבלאות מידע/משחקי כדורגל` declares `Football_Games`). These are **never transcluded by content pages**. Enumerate them via `api.php?action=query&list=pageswithprop&pwppropname=CargoTableName` (64 tables as of June 2026).
- Only **2** templates use `#cargo_attach`, both basketball (`משחק כדורסל/שמירת משחק לקארגו`, `…/שמירת נתוני שחקנים/שמירת שחקן`). Enumerate via `pwppropname=CargoAttachedTable`.
- Everything else stores via `#cargo_store` directly inside the content templates (e.g. `תבנית:קטלוג משחקים` stores `Football_Games`, `Games_Events`, `Games_Referees`, `Games_Videos`, `Football_Games_Uniforms` inline). Consequence: Cargo's "recreate data" tooling (which re-parses only pages transcluding declaring/attached templates) rebuilds almost nothing on this wiki — rows exist because they're written at page-save time. The mapping tables (`Days_In_Week`, `מיפוי…`) are stored by parsing the declaring template page itself.
- Third source: **central data-entry pages** — the whole `Competitions` / `Basketball_Competitions` / `Volleyball_Competitions` catalog is stored from one page per sport (`הזנת מפעלי כדורגל/כדורסל/כדורעף`), not from the competition pages (those store only `Football_Competitions_Map`). The player/season stat queries INNER-join these catalogs (League/Trophy/International/Official flags), so a wiki copy missing the הזנת pages renders every aggregate as 0.

## 6. Redirects
Hebrew redirect syntax: `#הפניה [[Target_Page_Name]]`
- Basketball seasons: canonical = `כדורסל:עונת YYYY/YY`, redirect from `כדורסל:YYYY/YY`.

## 7. Game Media Files

**Tickets** (`File:` pages):
- Basketball: `{{תיוג כרטיס משחק כדורסל|משחק=PAGE_NAME}}`

**Posters** (`File:` pages):
- Basketball: `{{תיוג כרזת כדורסל|משחק=PAGE_NAME}}`
- If no matching game page found in Cargo, upload with `{{תיוג כרזת כדורסל}}` (no `משחק=`) for tracking
- Filename convention: `כרזת משחק כדורסל DD-MM-YYYY.jpg`

**Newspapers** (`File:` pages, template `{{תיוג עיתונים}}`):
- File naming: `{שם_עיתון}_{תאריך_המשחק}_{שם_היריבה}_{מספר}_{(תאריך_פרסום)}`

## 8. Non-Game Entities

**Fan Songs** (`שיר:` namespace, template `{{שיר}}`):
- Parameters: `קטגוריה`, `שם השיר`, `עונת בכורה`, `על השיר`, `ביצוע לשיר`, `מילים`

## 9. Football Player Events (`|אירועי שחקנים=`)

Each event is one pipe-separated entry in the `|אירועי שחקנים=` parameter of `קטלוג משחקים`.

**Format:** `name::jersey::event_type::time::team`  (5 fields, separator is `::` — double colon)

**Fields:**
- `name` — player name as it appears on the wiki
- `jersey` — jersey number, or `אין-מספר` for historical games without jersey numbers
- `event_type` — see valid types below
- `time` — minute (integer), or empty for lineup events
- `team` — `מכבי` or `יריבה`

**Valid event types:**

| Category | Valid values |
|----------|-------------|
| Goals | `גול-רגל`, `גול-פנדל`, `גול-נגיחה` |
| Assists | `בישול-קלאסי`, `בישול-קרן`, `בישול-בעיטה חופשית`, `בישול-סחיטת פנדל`, `בישול-נגיחה` |
| Lineup | `הרכב`, `הרכב-שוער`, `ספסל`, `ספסל-שוער` |
| Substitutions | `מחליף`, `מוחלף` |
| Cards | `כרטיס צהוב`, `כרטיס צהוב-ראשון`, `כרטיס צהוב-שני`, `כרטיס אדום` |
| Other | `קפטן` |

**Common invalid/legacy types and their correct replacements:**

| Invalid (found in old pages) | Replace with |
|-----------------------------|-------------|
| `גול` | `גול-רגל` |
| `גול-קלאסי` | `גול-רגל` |
| `גול-ידוע` | `גול-רגל` |
| `גול-ישראל` | `גול-רגל` |
| `גול-פרץ` | `גול-רגל` |
| `גול-רגך` | `גול-רגל` (typo: ך instead of ל) |
| `גול-לא רגל` | `גול-נגיחה` |
| `גול-חופשית` | verify context; likely `גול-רגל` |
| `גול-עצמי` | investigate — own goal; no standard type exists yet |
| `בישול` | `בישול-קלאסי` |
| `בישול-רגל` | `בישול-קלאסי` |
| `בישול-קלאיסי` | `בישול-קלאסי` (typo) |
| `בישול-סחיטת פנדל מוצלח` | `בישול-סחיטת פנדל` |

**Example:**
```
אבי נמני::10::הרכב::0::מכבי
אבי נמני::10::קפטן::0::מכבי
אלי דריקס::7::הרכב::0::מכבי
ערן זהבי::14::ספסל::0::מכבי
אבי נמני::10::בישול-קלאסי::34::מכבי
אלי דריקס::7::גול-רגל::34::מכבי
אלי דריקס::7::מוחלף::72::מכבי
ערן זהבי::14::מחליף::72::מכבי
```

**The single-colon trap:**  
A single `:` before the minute (e.g. `גול-נגיחה:67`) instead of `::` (e.g. `גול-נגיחה::67`) causes the template to tag the page as having illegal events, even though the type name is valid. Always use `::` between every field.

**Tracking category:** Pages with bad events are added to the `משחקים המכילים אירוע לא תקין` tracking category (populated by the `הזנת אירועי משחק` template's `#ברירת מחדל` branch for unknown main event types).

## 10. Basketball Player Stats (`|שחקנים מכבי=` / `|שחקנים יריבה=`)

Basketball game pages use template `משחק כדורסל`. Player data is **not** a `::` delimited row — each player is a named-parameter sub-template:

```
{{אירועי שחקן סל |שם=טל ברודי |מספר=7 |דקות=38 |חמישייה=כן |נק=22 |זריקות עונשין=6 |קליעות עונשין=5 |זריקות שתי נק=8 |קליעות שתי נק=4 |זריקות שלוש נק=5 |קליעות שלוש נק=3 |ריבאונד הגנה=3 |ריבאונד התקפה=1 |פאולים=2 |חטיפות=3 |איבודים=2 |אסיסטים=7 |בלוקים=0}},
{{אירועי שחקן סל |שם=אולסי פרי |מספר=12 |דקות=35 |חמישייה=כן |נק=18 |זריקות עונשין=8 |קליעות עונשין=6 |זריקות שתי נק=7 |קליעות שתי נק=6 |זריקות שלוש נק=0 |קליעות שלוש נק=0 |ריבאונד הגנה=9 |ריבאונד התקפה=3 |פאולים=3 |חטיפות=1 |איבודים=2 |אסיסטים=2 |בלוקים=2}},
{{אירועי שחקן סל |שם=מיקי ברקוביץ' |מספר=5 |דקות=12 |חמישייה= |נק= |זריקות עונשין=0 |קליעות עונשין=0 |זריקות שתי נק=2 |קליעות שתי נק=0 |זריקות שלוש נק=1 |קליעות שלוש נק=0 |ריבאונד הגנה=1 |ריבאונד התקפה=0 |פאולים=2 |חטיפות=0 |איבודים=1 |אסיסטים=1 |בלוקים=0}}
```

Multiple players are joined with `,\n` (comma + newline). Both `|שחקנים מכבי=` and `|שחקנים יריבה=` use the same format.

**Key fields:**
- `מספר` — jersey number (integer or empty)
- `חמישייה` — `כן` if starting five, empty if bench (real pages use empty string, not `לא`)
- `נק` — total points scored, or empty if the player scored 0 / data unavailable
- `זריקות/קליעות שתי נק` — free throw attempts/made (confusingly named "two-point throws")
- `פאולים טכני` — optional, omit entirely if zero

## 10b. Basketball Competition Codes & Playoff Naming (basket.co.il)

The `games_all.json` feed tags each game with a numeric `game_type`. Only **stable, single-meaning** codes are mapped in `translations._BASKET_GAME_TYPE`:

| `game_type` | Competition (`מפעל`) |
|---|---|
| `5` | `ליגת העל` (regular season) |
| `34` | `הסופרקאפ הישראלי` |

**Playoffs are NOT keyed off the code.** Each playoff round gets its own `game_type` (observed: `16`=רבע גמר, `26`=חצי גמר, the final is yet another), so enumerating them is whack-a-mole. Instead, when a code isn't in the map, `discover_games_latest_season` recovers the competition from the **game page header** via `crawl_basket_co_il._competition_from_game_page`: the top-league h4 reads `ליגת <sponsor logo> סל …`, so once the logo `<img>` is dropped the tokens `ליגת סל` sit adjacent → `ליגת העל`. This positively identifies the top division across every round while excluding cups (`גביע … סל`) and the second tier (`ליגת לאומית בכדורסל`), and handles all current and future ליגת העל playoff rounds with no code maintenance. Only if both the code is unmapped **and** the header is unrecognised (e.g. a brand-new cup) does discovery raise — preserving the fail-loud-don't-silently-lose-a-competition guarantee at the competition level. To support a genuinely new competition (a cup), extend `_competition_from_game_page` (or add a stable code to `_BASKET_GAME_TYPE`).

**Playoff games:** `מפעל=ליגת העל` with the round in `שלב במפעל`, e.g. `רבע גמר - משחק 1`, `חצי גמר - משחק 2`, `גמר - משחק 3`. The page title uses only the competition: `כדורסל:DD-MM-YYYY מכבי תל אביב נגד <יריבה> - ליגת העל`. basket.co.il's raw header label (`- רבע הגמר משחק מספר N`) is normalized to this convention by `crawl_basket_co_il._normalize_fixture`.

## 11. Volleyball Player Stats (`|שחקנים מכבי=` / `|שחקנים יריבה=`)

Volleyball game pages use template `משחק כדורעף`. Player data is a `::` delimited row per player:

**Format:** `name::shirt_number::score[::לא-שיחק]`

- `shirt_number` — jersey number (integer)
- `score` — points scored, or `ללא-נקודות` if the player played but scored 0
- `לא-שיחק` — optional 4th field; present when the player was listed in the squad but **did not play**
- Players are joined with `,\n` where the comma starts each new line (the first player has no leading comma)

**Example (from real game):**
```
סאם בורגי::3::19
,גיא כהן::4::2
,ניקולס גונזלס::5::ללא-נקודות::לא-שיחק
,וסילי דניסוב::10::12
,אומרי רויטמן::13::ללא-נקודות
```

Both `|שחקנים מכבי=` and `|שחקנים יריבה=` use the same format. The volleyball model currently does not carry player data at the game-upload level (`VolleyballGame` dataclass has no players fields).

## 12. External Research Sources

See `.claude/maccabipedia_research_sources.md` for the full reference of where to search for data by sport and type (stats, rosters, video, etc.).

## 13. Navigation Categories

Pill-style navigation strips on player/staff achievement category pages, rendered by two DPL-based templates:

- `תבנית:ניווט קטגוריות זכיה בתארים` — params: `ענף`, `תואר`, `האם אנשי צוות` (optional `כן`).
- `תבנית:ניווט קטגוריות עונות במכבי` — params: `ענף`, `האם אנשי צוות` (optional `כן`).

### Category title patterns

| Pattern | Kind | Role |
|---|---|---|
| `שחקני {sport} שזכו ב-{N} {trophy_type}` | trophy | players |
| `אנשי צוות {sport} שזכו ב-{N} {trophy_type}` | trophy | staff |
| `שחקני {sport} ששיחקו {N} עונות במכבי` | seasons | players |
| `אנשי צוות {sport} שהיו {N} עונות במכבי` | seasons | staff |

### How the nav renders

Each template uses DPL with a regex on category titles (`[1-9]` or `[1-9][0-9]` for the count) plus a `PAGESINCATEGORY > 0` filter, so only categories with at least one member appear in the strip. New milestone categories materialize automatically when a player gets categorized — no need to pre-create them.

### Maintenance script

`packages/maccabipediabot/src/maccabipediabot/maintenance/sync_navigation_categories.py` enumerates every category found by `site.allcategories(...)` matching the four patterns, builds the canonical template invocation, and overwrites any page whose wikitext doesn't already match. Then purges all matched pages with `forcelinkupdate=true` so DPL caches refresh. Daily cron (`.github/workflows/sync_navigation_categories.yaml`).

Two side effects worth knowing:

- **Backfills missing pages.** `allcategories` returns categories that have ≥1 member even when no wiki page physically exists for them (redlink categories left over from before `AutoCreateCategoryPages` was installed, or from category-add paths the extension didn't hook). The script's save step creates the page from scratch, in addition to installing the template.
- **One-time spacing normalization.** Equality is exact (no whitespace tolerance). On first run, any page whose wikitext only differs by spacing gets re-saved to match the canonical exactly. From the second run onward, all matching pages skip cleanly.

### Sports and trophy types today

- `כדורגל` — אליפויות, גביעי מדינה, גביעי הטוטו, etc.
- `כדורסל` — אליפויות, גביעי מדינה, גביעי אירופה, הגביע הבין יבשתי, etc.
- `כדורעף` — אליפויות, גביעי מדינה, etc.

