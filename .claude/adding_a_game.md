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

The newspaper param is `שיוך משחק` in every sport. Purge lists per sport are in
`.claude/maccabipedia_structure_knowledge.md` §3.

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
  13,000"), take the match report and tell Roee about the other figure.

## 4. Resolve every name — never invent

- Maccabi: season squad = the sport's player-events table (see the table) joined
  to its games table, `Team=1`, over the season's date range. Surname → full name
  only when the squad confirms it.
- Guests / loanees: the same events table wiki-wide, `PlayerName LIKE '%<surname>%'`.
- Referee: the games table's referee column (see the table) `LIKE '%<surname>%'`.
  Maccabi coach: a nearby game's `CoachMaccabi` (same column in all three sports).
- Opponent players: surname exactly as printed. Flag unclear ones for Roee instead
  of "correcting" them from memory.
- Anything no source gives stays **blank**: kickoff time, the opponent's coach,
  kit, substitution minutes.

## 5. Write the game page (the canary)

- Title as in the table, home team first, `בית חוץ=בית/חוץ/נייטרלי`.
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
- Show Roee the live page before touching anything else.

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
  milestone games of that weight. Ask Roee when it's unclear whether a game counts
  as special. Count the scans already linked to the game before adding more, and
  pick the most informative ones (full match report and lineups first).
- **Existing scan:** add `סיווג` and `שיוך משחק` inside the template, and keep the
  rest of the page unchanged.
- **New scan:** name it `<paper> DD-MM-YYYY <opponent> (<publish date>).jpg`,
  using the *game* date in the name and the publication date in brackets. Check
  the name is not taken, then upload with MCP `upload_file(filename, file_path, text,
  comment)` (a requests multipart post). Do **not** use
  `football/papers/upload_games_papers_bot.py` for this: it calls
  `FilePage.upload()` (broken, see CLAUDE.md), it finds the game through
  maccabistats (so it can't see a game page created a minute ago), and it writes
  no `סיווג`.
- `שיוך משחק` must be the exact title of the game page. Verify that the file's
  categories include the per-game one (football:
  `עיתונות למשחק מה-<day> ב<month> <year>`) and that its name appears in the game
  page's parsed HTML. A wrong title lands the file in the tracking category
  `עיתוני <sport> עם שיוך לא תקין למשחק`.

## 7. Purge and report

- Purge the pages listed for the sport in the structure-knowledge file §3. For
  football that is the game, the season, the stadium, the competition, the Maccabi
  coach, the referee and every Maccabi player with a profile. Use `site.purgepages(...,
  forcelinkupdate=True)` in batches of 10 and skip pages that don't exist.
- Trello: comment the page link, the sources, the names left unclear and the fields
  left blank. Move the card only once Roee says so.
