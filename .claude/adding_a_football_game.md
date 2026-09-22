# Adding a Missing Football Game

End-to-end checklist for adding one historical football game by hand, together with
its newspaper coverage. Written after adding the 13-09-1978 Anderlecht friendly
(Trello #273). A single game is a one-off wiki edit: use scratch scripts, not repo
tooling. Other sessions write to the wiki too, so run one pywikibot process at a
time, in the foreground, with `time.sleep(3)` between saves.

## 1. Prove it is missing

- Cargo by date window: `Football_Games` with
  `Date >= '<d-3>' AND Date <= '<d+3>'` (the table is `Football_Games`, not
  `Games_Catalog`, which errors with an MWException).
- Cargo by opponent: `Opponent LIKE '%<name>%'` (the column holds the name with
  quote marks stripped).
- `page_exists` on the expected title. Season pages often mention the game in their
  prose (`עונת YYYY/YY`) even when no game page exists.

## 2. Find the sources

- **Already on the wiki:** search ns=6 for the opponent name. Newspaper file names
  carry the *game* date and the opponent:
  `<paper> DD-MM-YYYY <opponent> (<publish date>).jpg`.
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

- Maccabi: season squad = `Games_Events` joined to `Football_Games`, `Team=1`,
  over the season's date range. Surname → full name only when the squad confirms it.
- Guests / loanees: `Games_Events` wiki-wide, `PlayerName LIKE '%<surname>%'`.
- Referee: `Football_Games.Refs LIKE '%<surname>%'`. Maccabi coach: a nearby game's
  `CoachMaccabi`.
- Opponent players: surname exactly as printed. Flag unclear ones for Roee instead
  of "correcting" them from memory.
- Anything no source gives stays **blank**: kickoff time, the opponent's coach,
  kit, substitution minutes.

## 5. Write the game page (the canary)

- Title: `משחק:DD-MM-YYYY <home> נגד <away> - <competition>`, home team first,
  `בית חוץ=בית/חוץ/נייטרלי`. Friendlies: `מפעל=ידידות`.
- Copy the layout from a similar page, e.g.
  `משחק:05-12-1989 מכבי תל אביב נגד דינמו טביליסי - ידידות`.
- Events are `name::jersey::type::minute::team`, with `אין-מספר` when there is no
  number. Valid types are in `.claude/maccabipedia_structure_knowledge.md`. A
  substitute gets `ספסל` plus `מחליף`, and the player he replaced gets `מוחלף`;
  minute `0` when unknown. A goal from a rebound off the crossbar has no assist.
- Save it with one pywikibot script that refuses to overwrite an existing page,
  then check the `Football_Games` row and the `Games_Events` rows in Cargo.
- Show Roee the live page before touching anything else.

## 6. Newspapers: upload new scans, link existing ones

File-page text (matches the existing football files):

```
{{תיוג עיתונים
|שם עיתון=דבר
|תאריך פרסום=14-09-1978
|סיווג=סיקור משחק
|שיוך משחק=משחק:13-09-1978 מכבי תל אביב נגד אנדרלכט - ידידות
}}
```

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
- `שיוך משחק` must be the exact title of the game page. Verify that the file shows
  up in `קטגוריה:עיתונות למשחק מה-<day> ב<month> <year>` and that its name appears
  in the game page's parsed HTML.

## 7. Purge and report

- Purge the game, the season, the stadium, the competition, the Maccabi coach, the
  referee and every Maccabi player with a profile. Use `site.purgepages(...,
  forcelinkupdate=True)` in batches of 10 and skip pages that don't exist.
- Trello: comment the page link, the sources, the names left unclear and the fields
  left blank. Move the card only once Roee says so.
