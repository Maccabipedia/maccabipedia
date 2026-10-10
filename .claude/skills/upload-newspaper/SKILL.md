---
name: upload-newspaper
description: Use whenever a newspaper scan goes up on MaccabiPedia, in any sport. That covers a new clip for a game, a new version of an uploaded file (a better crop), or several pieces for one game. You crop the Maccabi article by eye, never a whole page. The upload_newspaper tool builds the name and page text from strict params and refuses a cut edge, a broken cap or a bad date. Nothing goes up before the maintainer has seen the before/after.
---

# Upload a newspaper clip

The rules and their reasons are in `rules.md` next to this file. Read a section there
when a step points to it. The tool enforces them, so never upload by hand, through MCP
`upload_file` or with pywikibot.

## 1. Find all of the game's coverage

Find every piece first, then decide which ones to upload (`rules.md`, "Find all of the
game's coverage"):
- The scan: `.claude/newspaper_archives.md`, which covers the search script and which
  archive has what.
- On the page: continuation notes (`(המשך בעמוד N)`, `(סוף בעמוד אחרון)`), the facing
  page of a spread, a second headline in the same block, a story from the opponent's
  side, a box just below the article, a column that ends mid-word.
- The rest of the issue: `search_newspaper_archive --date … --terms <opponent>`.

Write the list down, including the pieces you won't upload and the ones the archive
doesn't have.

## 2. Pick what goes up

- **Count** what the game already has, before you crop anything. Run the tool with the
  game params and no image. It prints the game page, the file name it would build, and
  every newspaper already linked against the cap. A game at its cap needs a swap
  decision from the maintainer, not a new crop.
- **Cap:** 2 for a regular game, 5 for a title, a cup final or a milestone game
  (`--special`). More candidates than room? Show them to the maintainer as pictures and
  let them choose.
- **One image per article.** Anything with its own headline is its own file. A box
  score, a table or a photo caption stays with its report. Keep the group table, but
  blank the items about other games in the group.

## 3. Crop by eye, into a spec

For each piece, write a crop spec (format at the top of `newspaper_crop.py`), in
original-scan pixels:
- Work from the archive's highest-resolution render (`pdftoppm -r 200`), not a
  downsized copy.
- Get the coordinates from a page map. It draws the detected rules in blue over a grid
  in scan pixels, and `--region` zooms in on one area:
  `uv run python -m maccabipediabot.maintenance.papers.newspaper_pagemap scan.jpg map.jpg --step 50 --region x0 y0 x1 y1`
- Cut along the page's own rules and gutters. Stack an article's columns when they wrap
  around another story. Blank the neighbouring stories along the rules that bound them.
  Use `wipe` polygons for slanted rules.
- Only when the whole page is the Maccabi story, keep the whole page, minus ads.

## 4. Dry run, until the tool passes

```
uv run python -m maccabipediabot.maintenance.papers.upload_newspaper \
    --sport כדורסל --paper "ידיעות אחרונות" --publish-date 30-10-1998 \
    --classification "סיקור משחק" --opponent "הכוכב האדום בלגרד" --game-date 29-10-1998 \
    --orig scan.jpg --spec crop.json [--description "תגובות קטש"] [--special]
```

- The main report has no `--description`. Every other piece from the same paper and day
  gets a short Hebrew description of what it is, never a number.
- **REFUSED** means fix the spec or a param, then run again. Don't silence a check:
  - `--accept-edge` is only for an edge that really is a rule, a frame line or a seam.
  - `--blanks-read <edge>`, one per edge, is only after you've zoomed into what that blank covers.
  - `--whole-page-because` is only for a page that is all Maccabi.
- Open the `.preview.jpg` and read it zoomed in: all four sides, and every blank.

## 5. Show the maintainer, then upload

1. Show the maintainer the `.before_after.jpg` from each dry run: the scan with the
   kept area outlined, with the crop next to it. For several clips, put them in one
   report. They answer by picture, not by reading text.
2. After their OK: `--apply` on **one** file. Open it on the wiki.
3. Then the rest, one run per file. To fix a file the bot already uploaded, use
   `--replace "<existing name>"`, which uploads a new version under the same name.
4. Tell Oren what changed (CLAUDE.md, "Telling Oren What Changed").
