# Newspaper upload rules: the reasons behind the tool

Reference for the `upload-newspaper` skill (`SKILL.md` next to this file). The tool
`maintenance/papers/upload_newspaper.py` enforces most of these; a new rule goes into
the tool and its tests first, then gets a line here.


File-page text, football version, as the tool writes it (it matches the existing files).
Basketball uses `{{תיוג עיתוני כדורסל}}` and volleyball `{{תיוג עיתוני כדורעף}}`, with the
same params.

```
{{תיוג עיתונים
|שם עיתון=דבר
|תאריך פרסום=14-09-1978
|סיווג=סיקור משחק
|שיוך משחק=משחק:13-09-1978 מכבי תל אביב נגד אנדרלכט - ידידות
}}
```

- **How many, by tier** (`--tier`, which the maintainer decides; the default is regular):
  - **regular**: up to **3** newspaper files.
  - **iconic**: up to **6**.
  - **legendary**: up to **9**.
  The cap counts **every** newspaper file linked to the game, whatever its `סיווג`,
  whether it was already on the wiki or is newly uploaded. The tool counts them,
  including files linked through an old redirect title. Pick the most informative
  ones (the full match report and lineups first). Ask the maintainer when a game might
  be a higher tier.
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
  dash of the next story's rule at the bottom. The tool (`newspaper_crop.py`) checks
  every edge and says why. The thresholds live in the code, not here:
  - **cuts_ink:** a letter or photo continues on both sides of the cut. It is tested
    before trusting a nearby rule, since a cut 20 px above a rule still slices the line
    above it. One cut letter on a long edge counts. A rule running along or across the
    cut does not.
  - **off_rule:** a blank edge in plain gutter can hide whole lines of the article
    without cutting a letter. Zoom in, then name that edge in `--blanks-read`.
  - Every waived check (`--accept-edge`, `--blanks-read`, `--whole-page-because`) is
    written into the upload summary and drawn in orange on the before/after. Waive only
    a real rule, frame line or seam. A blank whose edge sits on an ad's black frame
    leaves the frame as a bar, so run the blank past it.
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
- **New scan:**
  `<paper> <publication DD-MM-YYYY> <סיווג> [<sport> ]<opponent> (<game DD.MM.YYYY>).jpg`.
  - **Basketball and volleyball** say the sport (`כדורסל`, `כדורעף`):
    `ידיעות אחרונות 30-04-2004 לקראת משחק כדורסל סקיפר בולוניה (01.05.2004).jpg`.
  - **Football** has no sport word, no competition and no venue mark (ב/ח/נ). This was
    the maintainer's decision on 2026-10-10:
    `חדשות הספורט 05-03-1958 סיקור משחק IFK גטבורג (04.03.1958).jpg`.
    Older football files with `ליגה`/`גביע` and `(ב)` are not renamed for that.
  Don't copy the minority forms: game date first with the publication date in brackets
  (`דבר 13-09-1978 אנדרלכט (14-09-1978).jpg`), or the date before the paper
  (`05-10-2000 ידיעות אחרונות …`). Write the opponent without quote marks
  (`צסקא מוסקבה`). **Several pieces from the same paper and day: no numbers.** The
  main report keeps the plain name. Each other piece gets a short Hebrew description
  after the game-date brackets, saying what it is. This is the most common of Oren's
  forms since 2024 (105 files; 54 used numbers, which we no longer do):
  `מעריב 08-03-1959 רגע ממשחק ליגה ביתר תל אביב (07.03.1959) לוי מנסה להדוף כדור מפלשל.jpg`,
  `... (29.10.1998) תגובות קטש וג'אקוביץ'.jpg`. Don't use `(2)`, `(3)` or
  `עיתון2`. They show up in old or modern multi-part uploads, but they tell the
  reader nothing. The `עמוד N` suffix belongs to the 2026-09 bot
  uploads of whole pages (the 2004 Final Four, 1967–1998 European basketball, the 1958
  IFK Göteborg friendly). Don't copy it: the page number tells the reader of a crop
  nothing.
  The `<סיווג>` in the name is one of the template's values listed above (a reactions
  piece is still `סיקור משחק`; there is no `תגובות`. The word goes in the description
  instead). Spell the opponent exactly as the
  game page title does, including an ASCII apostrophe (`רג'יו`, not the Hebrew
  geresh `׳`).
  The `תאריך פרסום` param always takes `DD-MM-YYYY`, whatever the file name uses.
  The `upload_newspaper` tool checks the name and uploads (a requests multipart post).
  Don't upload by hand or through MCP `upload_file`. Don't use
  `football/papers/upload_games_papers_bot.py` either: it calls
  `FilePage.upload()` (broken, see CLAUDE.md), it finds the game through
  maccabistats (so it can't see a game page created a minute ago), and it writes
  no `סיווג`.
- `שיוך משחק` must be the exact title of the game page. The tool writes it from the
  game page it found (never a redirect) and after `--apply` checks the categories: for
  football, the per-game `עיתונות למשחק מה-<day> ב<month> <year>`. A wrong title lands
  the file in a tracking category:
  football `קטעי עיתונות עם שיוך לא תקין למשחק` (and an empty param
  `קטעי עיתונות ללא שיוך למשחק`); basketball/volleyball
  `עיתוני <sport> עם שיוך לא תקין למשחק` (and an empty param
  `עיתוני <sport> ללא שיוך למשחק`). These only catch a title that doesn't exist, and a
  link to a redirect (the old spaced title) passes them silently. That is why the tool
  refuses a redirect as the game page.

## Limits enforced in code

They are listed here so a reader knows they exist. Change them in the code and its tests.
- Preview published 0–7 days before the game; report or photo 0–14 days after it
  (`newspaper_names.py`).
- Cap by `--tier`: regular 3, iconic 6, legendary 9 newspaper files per game, counting files linked through
  redirects too.
- Whole page: the crop keeps more than 50% of one page (a landscape scan counts as a
  two-page spread), or a finished `--image` is over 4 MP. Either needs
  `--whole-page-because`.
- File name: at most 240 bytes. No quote marks, slashes, `~`, tabs or invisible
  direction marks. A slash in a team name becomes `-`.
