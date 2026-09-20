# Newspaper Archives (Google Drive scans)

Scanned Israeli newspapers on the MaccabiPedia shared Google Drive, used to verify
game dates, scores and venues against primary press coverage. Mounted locally at
`<drive root>/מכביפדיה_ראשי/ארכיונים/ארכיון עיתונים/` (on the WSL dev box the Drive
is under `/mnt/d/maccabipedia_google_drive/`; set `MACCABIPEDIA_NEWSPAPER_ARCHIVE`
to the `ארכיון עיתונים` folder for the search script).

## What's there

| Folder | Coverage | Form | Text layer |
|---|---|---|---|
| `ארכיון ידיעות אחרונות/עמודים בודדים/<year>/` | 1939–2021, near-daily | **Single pre-selected pages** (`YYYY-MM-DD_p<N>.pdf`, usually the sports pages) | Yes (pdftotext works, bidi-mangled) |
| `ארכיון ידיעות אחרונות/עיתונים מלאים/<year>/` | 1940–2019 | **Full issues** (`YYYY-MM-DD.pdf`, ~9 pages) | Yes — search this when the single-page folder lacks the day |
| `ארכיון חדשות הספורט/<year>/` | 1954–1984, near-daily | **Full issues** (`MM-DD-YYYY.pdf`, 4–6 pages, daily sports paper) | **No** — image-only scans |
| `ארכיון ספורט הבקר/<year>/` | 1936–1946 | issues | unverified |
| `ארכיון אספקלריה של הספורט/<year>/` | 1947–1948 | issues | unverified |
| `ארכיון ספורט ישראל/<year>/` | 1949–1950 | issues | unverified |
| `ארכיון מעריב/` | 1994 only | issues | unverified |
| `מגזין גול/` | 3 files, undated | magazine | unverified |

Full issue vs single page matters: in Yedioth only the pages someone chose to scan
exist, so a story may live on a page that is simply not in the archive. Hadashot
HaSport has every page of every issue, but it is a football-first paper —
basketball appears as a front-page box, a page-3 sidebar, or a photo caption.

## How to search

1. **Text-layer search first (both Yedioth folders):**
   `uv run python -m maccabipediabot.maintenance.papers.search_newspaper_archive --date 1963-11-19 --before 2 --after 4 --terms ברנר 79:64 --sources yedioth yedioth-full`
   It prints HIT / no hit per file, flags `NO TEXT LAYER` (image-only) and `EXTRACTION FAILED`
   (pdftotext error, e.g. a Drive file not yet synced) explicitly, and exits 1 when nothing hit.
   Search the opponent name and the exact score (`79:64` and `64:79` — both orders appear,
   and the text layer often inserts a space: `64 :79`; try the opponent name alone when a score misses).
2. **A text miss is not proof of absence.** Digits and Hebrew are often garbled by
   the embedded OCR. For the pages that matter, render and read the image:
   `pdftoppm -r 200 -png <pdf> <out-prefix>` then open the PNG with the Read tool;
   zoom with `convert <png> -crop WxH+X+Y -resize 200% <crop.png>`.
3. **Hadashot HaSport is visual-only.** pdftotext returns nothing (not "no hits" —
   nothing), so every page must be rendered. Check the front page first, then page 3.
   Tesseract OCR on these scans is slow and unreliable; visual reading is faster.

## Reading the papers to date a game

- Look in the issue **after** the game, not on the game day. "אמש" = the day before
  the publication date; "שלשום" = two days before.
- No paper on Shabbat: a **Friday-night game ("ליל שבת") is reported on Sunday**; a
  Saturday-night game ("מוצאי שבת") first appears on **Monday**. If Sunday's issue
  is silent and Monday's has the box score, the game was Saturday night.
- Games were postponed all the time (snow, a European tour, cup clashes). The wiki
  often carries the *originally scheduled* date; the press carries the *played*
  date. Look for "משחקי השלמה" / "משחק השארית" (makeup games) and "נדחה"
  (postponed) — most doc-vs-wiki date gaps of 1–3 weeks are exactly this.
- Round roundups ("משחקי המחזור ה-13") list every game played that weekend. A game
  missing from its round's roundup is strong evidence it was not played that day.
- Scores are printed opponent-first as often as Maccabi-first, and the halftime
  score usually sits in parentheses next to the final: `(30:54) 81:129`.

## Known data problems

- `ארכיון חדשות הספורט/1964/` contains files misdated as 1964 that are duplicates
  of 1961 issues. Always confirm the masthead date on the rendered page.
- Yedioth has gaps (e.g. no 12.4.1962 page); when one archive has a hole, check the
  other — Hadashot HaSport had the 12.4.1962 issue Yedioth lacked.
- The Yedioth text layer merges adjacent columns, so a hit's context lines may
  belong to a different article. Confirm on the image before trusting a snippet.

## Where this was used

The basketball doc-vs-wiki audit (2026-09): 115 score/date discrepancies between a
typed historical results list and the wiki were each settled against these scans.
The wiki was right ~4:1 overall, but the hardest cases were rescheduled games where
the press date beat both sources' assumptions.
