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
| Series links (tie/playoff) | `משחק1`/`משחק2`/`משחק3` = `[[<title>\|<score>]]` | `משחק קודם בסדרה`/`משחק הבא בסדרה` = bare title | same as basketball |
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

## 3b. Settle every uncertain field in the issues around the game

Applies to every game whose source is the press, in any sport and any decade (in
practice everything before online box scores, from the 1930s on). One match report
is not enough for a field you are unsure of: round name, date, home/away, venue,
opponent name, a player's identity.

- Read the issues **before** the game too, not only after. Previews and fixture
  lists ("בליל שבת יערכו...", the draw, "המשחקים:") name the round and the venue,
  list the home side first, and give the day. Reports often skip all three.
- Search a window of about a week each side
  (`search_newspaper_archive.py --before 7 --after 3`), in every archive that covers
  the date (Yedioth single pages, Yedioth full issues, Hadashot HaSport up to 1984).
- A secondary source (a results doc, a book, a fan list) gives a good date, opponent
  and score, but its labels are its own shorthand. Take the round name from the press.
  Example: a hand-kept results doc called the 26.6.1964 basketball cup game "גביע מוקדם";
  Yedioth's preview of 22.6.1964 says "הסבוב ה-4", so the page says `סיבוב רביעי`.
- Round numbering changed from season to season (the basketball cup's early rounds
  were "סיבוב שלישי" in 1963, "הסבוב ה-4" in 1964). Never carry a round name over
  from another season.
- Two papers that disagree on a field: write the one the match report or the preview
  states outright, and tell the maintainer about the other.
- A results box ("אמש בגביע הכדורסל") lists the home side first in every line. A
  drawn host whose game moved to the bigger hall (Yad Eliyahu) is still the host:
  the page says `חוץ` with `אולם=יד אליהו`. Check the box's other lines against their
  venues before trusting the order.
- The text and the box score can disagree on a score (97:78 in the text, scorers
  adding up to 77). Take the score the box score and a second source agree on, and
  tell the maintainer. A box score that adds up 2 short of the final stays as printed.
- Yedioth's text layer is unreadable for roughly 1977–1980, so text search finds
  nothing there. Search for the score from a secondary source instead, then read the
  pages by eye.

## 4. Resolve every name — never invent

- Maccabi: season squad = the sport's player-events table (see the table) joined
  to its games table, `Team=1`, over the season's date range. Surname → full name
  only when the squad confirms it.
- Guests / loanees: the same events table wiki-wide, `PlayerName LIKE '%<surname>%'`.
- Referee: the games table's referee column (see the table) `LIKE '%<surname>%'`.
  Maccabi coach: a nearby game's `CoachMaccabi` (same column in all three sports).
- Opponent players: the same events table joined to the games table, `Team=0`,
  same season and same opponent. Surname → full name only when exactly one rostered
  player matches; the press spells foreign names loosely (מדרמן = דן פדרמן,
  גברסון = קרל נברסון), so a near match goes to the maintainer, not into the page.
  No roster (a club the wiki has no games against that season): surname exactly as
  printed. Flag unclear ones for the maintainer instead of "correcting" them from
  memory.
- Opponent club: the press, the federation and a results doc can each name one club
  differently in the same season (יגור/העמק, גבת-יגור, יגור = the wiki's "הפועל גבת"
  in 1978/79). Prove it is one club from its league games that season (same score
  lines, same players, same coach), then use the name the wiki gives it that season.
  A club the wiki has never played gets a new name from the press, after the
  maintainer agrees. A slash in the name becomes "-" in file names.
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
- **Part of a tie or series?** Link it both ways: fill the series parameters (table above) on
  the new page *and* on every sibling game that exists. A link to a missing page puts the
  game in a "bad entry" category, but a missing link back is caught by nothing. Details
  are in `.claude/maccabipedia_structure_knowledge.md` §7c.
- Save it with one pywikibot script that refuses to overwrite an existing page,
  then check the games-table row and the player-event rows in Cargo.
- Show the maintainer the live page before touching anything else.

## 6. Newspapers: upload new scans, link existing ones

Follow the `upload-newspaper` skill (`.claude/skills/upload-newspaper/`). It covers the cap per game, cropping to the
Maccabi article, file names for one or several pieces, the `{{תיוג עיתונים}}` text with
`שיוך משחק` (use the exact game-page title from §5), and the checks before upload.

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
