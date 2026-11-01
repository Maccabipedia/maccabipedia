# Before/after screenshots on pull requests

Every PR that touches `skins/Maccabipedia/`, `infra/lua_modules/` or
`infra/local-wiki/config/` gets one comment from `.github/workflows/visual_diff.yaml`:
the same pages shot before and after the change, desktop (1280) and mobile (390),
and a third "Changes" image (the after shot faded, every changed pixel red). The
comment is edited in place on each push, so there is only ever one.

## Which pages

- `infra/visual_diff/pages.txt`: the defaults. A game page, a player, a competition,
  a stadium, the seasons hub, game search, all in the CI snapshot.
- The PR's own pages, in a hidden block anywhere in the description (editing the
  description re-runs the job):

  ```
  <!-- visual-pages
  תארים (כדורגל)
  -->
  ```

  Name the pages your change is for. A skin change for one page type shows
  nothing on the defaults if that type is not among them.
- A listed page missing from the snapshot is downloaded from production with its
  templates (`download_pages_from_prod.py`, read only). Its **Cargo rows are not**,
  so query-driven numbers can be empty or wrong. Layout and styling still show.
- **No images in CI.** The job runs the wiki with `MW_DISABLE_FOREIGN_IMAGES=1`
  (`infra/visual_diff/compose.no-foreign-images.yml`). From GitHub's runners every
  image lookup to production hangs: the first run's game page never returned
  (Apache logged the page request and nothing after it for 90 s). So pictures are
  missing on both sides and file links, like the game page's event icons, show as
  red `קובץ:` text, which makes the page taller than on the site. Both sides render
  the same content, so a skin change still compares fairly. A local run uses
  whatever your wiki was started with.
- At most 20 pages. Never list whole season pages: the local wiki looks up every
  image on production, uncached, and a season's games list is thousands of lookups
  per render.

## How it decides

The base commit is the merge commit's first parent, so "before" is master as it is
now. Only the paths the wiki renders from are switched (`git restore --source`),
then MediaWiki is restarted so no APCu/OPcache/ResourceLoader state survives. Lua
modules are deployed and the pages purged only when `infra/lua_modules/` differs,
because a purge means re-rendering, which means image lookups on production.

The base is shot twice. A shot that differs between those two is **unstable**
(random box, slider), shown collapsed, and never counted as a change. A shot counts
as **changed** when more than 20 pixels differ, a pixel differing when any one
colour channel moves by more than 16. A count rather than a share of the image, so a
swapped icon shows on a tall page, and per channel, so a blue-only recolour shows.
(Two renders of the same code matched pixel for pixel when measured.)

## Where the images live

GitHub has no API for attaching an image to a comment. `publish.py` commits each
run's JPEGs to the orphan branch `visual-diffs` under `pr-<n>/<run>-<attempt>/`
and the comment links their raw URLs. The branch is only appended to, so old
comments keep their images. About 4 MB a run when the skin changes everywhere.
It commits through the Git Data API, never a clone: a clone of a branch that only
grows, even a shallow one, would download every image ever posted on every run.
A fork's PR cannot push or comment: its shots are only in the run's artifact.

## Run it locally

With the local wiki up (and `restore-db.sh` done), from a clean checkout of the branch:

    uv run --with playwright python infra/visual_diff/run.py --base origin/master \
        --out /tmp/visual --page 'תארים (כדורגל)'

It refuses to start when the rendered-from paths have uncommitted edits, and puts
them back to HEAD when it ends. Open `/tmp/visual/images/` for the JPEGs.
