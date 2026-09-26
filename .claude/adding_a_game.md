# Adding a Missing Game

End-to-end checklist for adding one historical game by hand, together with its
newspaper coverage. The steps are the same in every sport; what differs is in the
table below. Written after adding the 13-09-1978 Anderlecht football friendly
(Trello #273), so the football column is the one that has been done end to end.
For basketball and volleyball, look at their game bots first (CLAUDE.md: the
football bot is the reference template for the other sports).

A single game is a one-off wiki edit: use scratch scripts, not repo tooling. Other
sessions write to the wiki too, so run one pywikibot process at a time, in the
foreground, with `time.sleep(3)` between saves.

## Per-sport differences

| | Football | Basketball | Volleyball |
|---|---|---|---|
| Title | `משחק:DD-MM-YYYY <home> נגד <away> - <comp>` | `כדורסל:DD-MM-YYYY …` | `כדורעף:DD-MM-YYYY …` |
| Game template | `קטלוג משחקים` | `משחק כדורסל` (quarter points) | `משחק כדורעף` (set scores) |
| Games table | `Football_Games` | `Basketball_Games` | `Volleyball_Games` |
| Player events (Maccabi) | `Games_Events`, `Team=1` | `Basketball_Player_Game_Events_Summary`, `Team=1` | `Volleyball_Players_Game_Events`, `Team=1` (opponent is `2`, not `0`) |
| Referee column | `Refs` | `MainReferee` | `Refs` |
| Player / opponent pages | main namespace | `כדורסל:<name>` | `כדורעף:<name>` |
| Newspaper template | `{{תיוג עיתונים}}` | `{{תיוג עיתוני כדורסל}}` | `{{תיוג עיתוני כדורעף}}` |
| Reference code for the page text | an existing page of the same era | `basketball/gamesbot_basketball.py` | `volleyball/gamesbot_volleyball.py` |

The newspaper param is `שיוך משחק` in every sport. Purge lists for football and
volleyball are in `.claude/maccabipedia_structure_knowledge.md` §3; basketball has
none there (see step 7).

## 1. Prove it is missing

- Cargo by date window: `<Sport>_Games` with
  `Date >= '<d-3>' AND Date <= '<d+3>'`. There is no `Games_Catalog` table; a
  query against it fails with an MWException.
- Cargo by opponent: `Opponent LIKE '%<name>%'` (the column holds the name with
  quote marks stripped).
- `page_exists` on the expected title. Season pages often mention the game in their
  prose (`עונת YYYY/YY`) even when no game page exists.

## 2. Find the sources

- **Already on the wiki:** search ns=6 for the opponent name, not the date. Some
  newspaper files carry the game date (`<paper> DD-MM-YYYY <opponent> (<publish
  date>).jpg`) and others only the publication date, so a date search misses them.
- **Drive archive:** `maintenance/papers/search_newspaper_archive.py`. Look at the days
  after the game, not the day itself. See `.claude/newspaper_archives.md`.
- Other sources: `.claude/maccabipedia_research_sources.md`.

## 3. Read the scans

- Download with pywikibot. Scratch scripts must call
  `maccabipediabot.common.wiki_login.get_site()`, because a bare
  `pywikibot.Site()` raises `UnknownFamilyError`:
  `pywikibot.FilePage(site, title).download(filename=...)`.
- Crop the lineup box and upscale it 4–6x (PIL, LANCZOS), then Read the PNG.
  Lineup-box conventions are in `.claude/newspaper_archives.md`.
- Pull out: score, goals + minutes + how (penalty / header), lineups, substitutions,
  referee, crowd, stadium. When papers disagree (e.g. crowd 14,000 vs "about
  13,000"), take the match report and tell the maintainer about the other figure.

## 4. Resolve every name — never invent

- Maccabi: season squad = the sport's player-events table (see the table) joined
  to its games table, `Team=1`, over the season's date range. Surname → full name
  only when the squad confirms it.
- Guests / loanees: the same events table wiki-wide, `PlayerName LIKE '%<surname>%'`.
- Referee: the games table's referee column (see the table) `LIKE '%<surname>%'`.
  Maccabi coach: a nearby game's `CoachMaccabi` (same column in all three sports).
- Opponent players: surname exactly as printed. Flag unclear ones for the maintainer instead
  of "correcting" them from memory.
- Anything no source gives stays **blank**: kickoff time, the opponent's coach,
  kit, substitution minutes.

## 5. Write the game page (the canary)

- Title as in the table, home team first, `בית חוץ=בית/חוץ/נייטרלי`.
- **No space after the colon:** `משחק:29-08-1954 …`, never `משחק: 29-08-1954 …`.
  On 2026-09-22 the 1954 Lazio friendly was created as `משחק: 29-08-1954 …` and
  had to be moved 40 minutes later, which left a redirect behind. No live game
  page has the space. The two spaced `_pageName`s that Cargo still returns (1939,
  1970) are stale rows of redirects left by a 2023 MaccabiBot move. Old wikilinks
  (e.g. season-page prose) and wiki template docs still show the spaced form, so
  don't copy a title from them. Build it with
  `maccabipediabot.common.page_names.build_football_game_page_name(game_date=...,
  home_team=..., away_team=..., competition=...)`, which is what
  `football/gamesbot.py` uses.
- Copy the layout from an existing page of the same sport and era (basketball and
  volleyball: also check what their game bot writes). Football example:
  `משחק:05-12-1989 מכבי תל אביב נגד דינמו טביליסי - ידידות`, with friendlies as
  `מפעל=ידידות`.
- Football events are `name::jersey::type::minute::team`, with `אין-מספר` when there is no
  number. Valid types are in `.claude/maccabipedia_structure_knowledge.md`. A
  substitute gets `ספסל` plus `מחליף`, and the player he replaced gets `מוחלף`;
  minute `0` when unknown. A goal from a rebound off the crossbar has no assist.
- Save it with one pywikibot script that refuses to overwrite an existing page,
  then check the games-table row and the player-event rows in Cargo.
- Show the maintainer the live page before touching anything else.

## 6. Newspapers: upload new scans, link existing ones

File-page text, football version (matches the existing football files).
Basketball and volleyball use their own template from the table, with the same
`שיוך משחק` param; copy the other params from an existing file of that sport.

```
{{תיוג עיתונים
|שם עיתון=דבר
|תאריך פרסום=14-09-1978
|סיווג=סיקור משחק
|שיוך משחק=משחק:13-09-1978 מכבי תל אביב נגד אנדרלכט - ידידות
}}
```

- **How many:** up to **2** newspapers for a regular game, and up to **5** for a
  special one: the game that clinched a championship, a cup final, and other
  milestone games of that weight. Ask the maintainer when it's unclear whether a
  game counts as special. The cap counts **every** newspaper file linked to the
  game, whatever its `סיווג`, and whether it was already on the wiki or newly
  uploaded. Count them before adding more: football files appear in the per-game
  category `עיתונות למשחק מה-<day> ב<month> <year>`, and in any sport an ns=6
  search for the game title finds the files whose `שיוך משחק` names it. Pick the
  most informative ones (full match report and lineups first).
- **Existing scan:** add `סיווג` and `שיוך משחק` inside the template, and keep the
  rest of the page unchanged.
- **`סיווג`:** the template accepts `טבלת ליגה`, `טבלת גביע`, `לקראת משחק`,
  `סיקור משחק`, `רגע ממשחק`, `סיקור מחזור`, `הגרלת גביע`, `אחר`. A match report is
  `סיקור משחק`; a preview is `לקראת משחק`.
- **New scan:** name it `<paper> DD-MM-YYYY <opponent> (DD.MM.YYYY).jpg`: the
  *game* date in the name and the publication date in brackets. Dots in the
  brackets are the most common form (dashes also appear, e.g. the two Anderlecht
  files). For a second page of the same paper and day, add a suffix after the
  brackets: `… (02.01.1972) עיתון2.jpg` is the usual form, and `(2)` also appears.
  **Basketball's recent uploads reverse the dates:**
  `ידיעות אחרונות <publication DD-MM-YYYY> <סיווג> כדורסל <opponent> (<game DD.MM.YYYY>) עמוד N.jpg`.
  That is the publication date first, the game date in brackets, and the opponent with
  no quote marks (`צסקא מוסקבה`). Examples: the 2004 Final Four and 1981 CSKA files.
  The `תאריך פרסום` param always takes `DD-MM-YYYY`, whatever the file name uses.
  Check the name is not taken, then upload with MCP `upload_file(filename, file_path, text,
  comment)` (a requests multipart post). Do **not** use
  `football/papers/upload_games_papers_bot.py` for this: it calls
  `FilePage.upload()` (broken, see CLAUDE.md), it finds the game through
  maccabistats (so it can't see a game page created a minute ago), and it writes
  no `סיווג`.
- `שיוך משחק` must be the exact title of the game page. Verify that the file's
  categories include the per-game one (football:
  `עיתונות למשחק מה-<day> ב<month> <year>`) and that its name appears in the game
  page's parsed HTML. A wrong title lands the file in a tracking category:
  football `קטעי עיתונות עם שיוך לא תקין למשחק` (and an empty param
  `קטעי עיתונות ללא שיוך למשחק`); basketball/volleyball
  `עיתוני <sport> עם שיוך לא תקין למשחק` (and an empty param
  `עיתוני <sport> ללא שיוך למשחק`). These only catch a title that doesn't exist:
  a link to a redirect (e.g. the old spaced title) passes silently, so check the
  title against the table above yourself.

## 7. Purge and report

- Purge the game page, the newspaper files you touched, and the pages listed in
  the structure-knowledge file §3. For football that is the opponent, the season,
  the competition, the stadium, every Maccabi player with a profile, both coaches
  and the referee. §3 has no basketball list and the basketball bot has no purge
  logic (only the videos bot purges, and only season pages), so for basketball
  purge the same kinds of pages under the `כדורסל:` prefix. Use
  `maccabipediabot.common.wiki_purge.purge_pages(site, titles, chunk_size=10)`,
  which dedups and sets `forcelinkupdate`. Pass `chunk_size=10`, because the
  default of 50 times out on Cargo-heavy player profiles.
- Check the render only after the purge: a brand-new game page's first cached render
  has no lineups or events. Then check that every newspaper thumbnail on it
  loads. Both traps and their fixes are in the structure-knowledge file.
- Trello: comment the page link, the sources, the names left unclear and the fields
  left blank. Move the card only once the maintainer says so.
