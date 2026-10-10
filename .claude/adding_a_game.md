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
- **Part of a tie or series?** Link it both ways: fill the series parameters (table above) on
  the new page *and* on every sibling game that exists. A link to a missing page puts the
  game in a "bad entry" category, but a missing link back is caught by nothing. Details
  are in `.claude/maccabipedia_structure_knowledge.md` §7c.
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
- **Upload the Maccabi item, not the page.** Crop the scan to the article about the
  game: its headline, its columns, its photo and caption, and nothing else on the page.
  That is how the uploaders to follow (`אורן המתעפץ`, `Kosh`) built the ~4,600 files
  they uploaded across all three sports. Their median file is 0.5–0.7 megapixels, and
  old papers usually come out 350–850 px wide. Measured 2026-10 on every file that
  carries the three tagging templates. The shapes they use:
  - **A full report:** the headline plus every column of the article. When the columns
    wrap around other stories, cut them out and stack them into one strip. One
    article means one headline. A piece with its own headline (and often its own
    byline or frame) is a separate article and becomes its own image, even when it
    sits inside the report's block: an interview box, a columnist's frame, reactions.
    A box score, a side table or a photo caption has no headline of its own, so it
    stays with the report. The group or league table stays too, but a short item on
    another game in the group (e.g. Real–Bosna next to a Maccabi report) is blanked:
    keep the table, drop the other game.
  - **A round-up or preview column** (all of the round's games in one item): crop just
    the Maccabi paragraph, with the column's headline above it when it fits. Oren
    often marks the Maccabi lines with a yellow highlighter.
  - **A table:** the table and its header only (`טבלת ליגה`, `טבלה לאחר משחק …`).
  - **A photo:** the photo with its caption (`רגע ממשחק`).
  - **The only time a whole page is right:** a page or spread that is entirely the
    game's coverage under one frame or banner (and even then a separately headlined
    piece inside it can still go up on its own when the cap allows), of any era: a
    title win, a derby, a 1969 Asia Cup report, a jubilee spread. Even then, crop off ads and other sections. Never upload a page where
    Maccabi is one item among others. The reader has to hunt for it, and the file is
    10–20 times larger than it needs to be.
  Crop from the archive's highest-resolution render (`pdftoppm -r 200`), and don't
  shrink the crop to match the widths above. Those come from smaller sources, and
  small print has to stay readable. A 200-dpi article crop is around 1,000–1,400 px
  wide and under 1 MB, far below a full spread's 3,850 px. Find the
  article with the text layer (`pdftotext -bbox`, see `.claude/newspaper_archives.md`),
  then open the crop and read it before uploading.
  **Cut along the page's own separators.** A newspaper page is divided into areas by
  solid rules, dotted or dashed rules, photo frames, boxes and the white gutters
  between columns. Find those first, then build the crop from whole areas: the
  article's areas are kept, and every other area is dropped or blanked. Each kept edge
  should run along a separator or through empty gutter. Each blank edge should run
  along the rule that bounds the neighbouring story. A coordinate picked by eye in
  the middle of a text block is how a crop clips a headline's descenders or leaves a
  dash of the next story's rule at the bottom. A thin-rule detector works for this:
  a rule is a band that is dark along its length but light a few px to either side,
  which also catches dotted rules and keeps text and headline strokes out. Check two
  things automatically:
  - **Ink across the cut:** a pixel on the cut line that is dark, with dark pixels
    2 px to each side, is a cut through a letter or a photo (5 px missed the
    bottom strokes of a cut text line).
  - Test for cut ink before you trust a nearby rule. A cut 20 px above a rule
    "sits near the rule" and can still slice the line just above it.
  - **Blank edges off any rule:** such an edge can hide whole lines of the article
    between two rows of text without cutting a single letter, so read what it covers.
  Every "cuts ink" result is either fixed or explained in writing (it is the rule
  itself, a frame line, or the seam between two stacked pieces). Never let one through
  silently, and never mark a crop clean while one is unexplained. A blank whose edge
  sits on an ad's black frame leaves the frame as a bar, so run the blank past it.
  Then confirm by eye. Separators don't bound everything, because an article can wrap
  around another story, so the reading order still decides which areas belong to it.
  **Find all of the game's coverage before you crop.** One game is often spread over
  several areas, and each separate article becomes its own file (counted against the
  per-game cap above):
  - a continuation note at the end of a column: `(המשך בעמוד N)`, `(סוף בעמוד אחרון)`;
  - the facing page of a spread, which often holds a second piece on the same game,
    such as an analysis, player ratings or reactions under a different headline;
  - a second headline inside the same block (quotes, reactions) is a separate area,
    so crop it as its own image and don't hang it under the main report;
  - every other story on the same page or spread: read them all, because a story
    written from the opponent's side (their hotel, their ticket sales) is still about
    this game; check boxes right under your crop and items outside a frame;
  - a column that ends mid-word with no continuation note is unfinished: record it;
  - the rest of the issue: run the text-layer search over the day's pages
    (`search_newspaper_archive --date … --terms <opponent>`).
  Write down every piece you found, including the ones you won't upload and the ones
  the archive doesn't have (a continuation page that was never scanned). That way the
  next person knows the coverage is incomplete, not missing. Then count the files
  against the cap, the existing ones included (the game page's backlinks in ns=6).
  When there are more pieces than the cap allows, pick the most informative ones and
  ask the maintainer.
  **Review the whole edge (היקף) of every crop before it goes up.** A crop looks right
  at thumbnail size and still cuts text, so do it zoomed in, on the original scan:
  walk all four sides of every kept rectangle, and every side of every area you
  blanked out. At each side, ask two questions:
  1. Is any letter of the article cut, or did it end up outside the crop or inside a
     blank? Typical misses are the last line of a column, a box score's final row,
     and the end of a sidebar.
  2. Does the article continue past this edge? Look across it: a column may run on
     below the cut, a section such as `נקמה` may follow under its own subhead, or a
     second piece on the same game (reactions, quotes) may sit right underneath. If
     it does, extend the crop or add a stacked piece.
  Before trusting a blank, read the text it covers. Twice a blanked block turned out
  to be part of the article, not a neighbouring story. The edge review found
  something on 8 of the first 12 crops (2026-10). Check the bottom edge: the crop ends
  at the article's own end, which is the dashed rule or the `(סוף בעמוד …)` continuation
  note, and not at the first line that looks like a stopping point. Check the side
  edges too: old scans are often tilted, so a column rule can drift 15 px or more
  down the page. A straight cut then shows slivers of the next column at one end and
  clips this article's letters at the other. Follow the rule, or cut the block into
  slices. An article that runs onto a second
  page is two files, or one stacked image, never two whole pages.
- **Existing scan:** add `סיווג` and `שיוך משחק` inside the template, and keep the
  rest of the page unchanged.
- **`סיווג`:** the template accepts `טבלת ליגה`, `טבלת גביע`, `לקראת משחק`,
  `סיקור משחק`, `רגע ממשחק`, `סיקור מחזור`, `הגרלת גביע`, `אחר`. A match report is
  `סיקור משחק`; a preview is `לקראת משחק`.
- **New scan:** use one format in every sport:
  `<paper> <publication DD-MM-YYYY> <סיווג> <sport> <opponent> (<game DD.MM.YYYY>).jpg`,
  where `<sport>` is `כדורגל`, `כדורסל` or `כדורעף`. Example:
  `ידיעות אחרונות 30-04-2004 לקראת משחק כדורסל סקיפר בולוניה (01.05.2004).jpg`.
  This is already the majority form in all three sports, except that football names
  rarely carry the sport word. Include it anyway; existing files are not renamed.
  Don't copy the minority forms: game date first with the publication date in brackets
  (`דבר 13-09-1978 אנדרלכט (14-09-1978).jpg`), or the date before the paper
  (`05-10-2000 ידיעות אחרונות …`). Write the opponent without quote marks
  (`צסקא מוסקבה`). For several pages of the same paper and day, add a suffix after
  the brackets: `(2)`, `(3)` (Oren's form). `עיתון1`/`עיתון2` (Kosh, and the most
  common suffix overall) also appears. The `עמוד N` suffix belongs to the 2026-09 bot
  uploads of whole pages (the 2004 Final Four, 1967–1998 European basketball, the 1958
  IFK Göteborg friendly). Don't copy it: the page number tells the reader of a crop
  nothing.
  The `<סיווג>` in the name is one of the template's values listed above (a reactions
  piece is still `סיקור משחק`; there is no `תגובות`). The `(2)`, `(3)` suffix also
  numbers a second or third crop from the same page. Spell the opponent exactly as the
  game page title does, including an ASCII apostrophe (`רג'יו`, not the Hebrew
  geresh `׳`).
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
