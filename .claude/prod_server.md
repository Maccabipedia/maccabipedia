# The production server (hosting account)

Facts about the machine behind www.maccabipedia.co.il, not about the wiki's content
(that is `maccabipedia_structure_knowledge.md`). Versions and the LocalSettings split:
the `deploy-localsettings` skill and `infra/local-wiki/README.md`.

## Access

- **DirectAdmin** panel on port 2222 of the FTP host. Shows the account's limits, runs
  **cron jobs** (the only way to run a command on the server; there is no shell).
- **FTP** with the bot's FTP-only account (`MACCABIPEDIA_FTP_*` in `infra/local-wiki/.env`,
  TLS with a self-signed cert: `lftp` needs `set ssl:verify-certificate no`). Its root holds
  `public_html/` (the wiki), `logs/` (daily access/error logs, `*.tar.gz`, about a week),
  `stats/`, `public_ftp/`. It is not the DirectAdmin login.
- `curl` against the site needs a full browser User-Agent; a short one gets a 302 to
  `abuse.spd.co.il` from the host's firewall, which looks like an outage and is not.
- Reading through FTP is fine. Deleting, moving or uploading anything on the server needs
  the owner's OK for that action.

## The file cap (inodes)

The account allows **250,000 files and folders** (DirectAdmin: Inodes). Disk space and
bandwidth are unlimited, so big single files (`run_jobs.log`, `MyLogs/*.log`) never matter;
the count does. November 2026: ~221k used.

| Where | Files | Notes |
|---|---|---|
| `images/thumb/` | ~162k | thumbnails, one folder per original + one file per size |
| `images/[0-f]/` | ~19k | the originals (~18.5k current files) |
| `images/deleted/` | ~5.5k | deleted files, kept for undelete |
| `images/temp/` | ~4.1k | upload stash, last touched 2020 |
| `images/cache/`, `images/archive/` | ~3k, ~2.7k | image cache; old versions of re-uploaded files |
| MediaWiki core | ~11.5k | `includes`, `resources`, `vendor`, `tests` (2.7k), `docs` |

Counting through FTP (`lftp find`) takes over an hour for the whole account: one directory
per request, and every original has its own thumb folder. A one-off DirectAdmin cron with
`find | wc -l` takes seconds.

## Thumbnails

Thumbnails are written when a page **parses** (`$wgGenerateThumbnailOnParse`, default on)
and kept forever. Every distinct width is another file.

- **The first version took prod down.** Deployed 2026-11-14 (PR #294), it made many pages
  (main page, season pages) answer HTTP 500 with a TypeError from 13:08 to 13:12 UTC, until the
  previous file went back up. The closure declared `array &$linkAttribs`, and core passes `false`
  for an image without a link (`|link=`); the local test had no such image. The current version
  takes untyped parameters and runs its body in `try/catch (Throwable)`: whatever fails, the image
  keeps its plain thumbnail and the page renders.
- **Testing it:** `infra/local-wiki/tests/test_retina_thumbnails.py` (pytest, against a running
  local wiki, `MACCABIPEDIA_LOCAL_URL`) renders 4 images x 10 shapes x 5 link forms, 7 gallery
  modes, a missing file, `thumb=`, `Media:`/`:File:` links, the file lists and the file history.
  Against the version that took prod down it fails 69 cases with that TypeError. Before a deploy,
  also render real pages with their real images, old setting vs new (no errors, same 1x, same 2x
  file, no new files).
- **2x copy only, no 1.5x** (card #626). Core's `$wgResponsiveImages` wrote a 1.5x and a 2x
  copy of every image shown in an article, gallery or File page, created during the parse
  whatever the HTML used. They were 65% of all thumbnails. `LocalSettings.shared.php` turns
  the setting off and a `ThumbnailBeforeProduceHTML` hook adds the 2x copy itself:
  - only where core used to (caller of `toHtml` is `Linker`, `TraditionalImageGallery` or
    `ImagePage`). File history, Special:ListFiles and search results never had copies, and
    crawlers reach them, so a 2x there would add files;
  - never for files that must be rendered (SVG, TIFF), paged files (PDF), or files from another
    repository (prod has none; the local wiki shows prod's images through one);
  - when the 2x is the original file itself (images shown near their full size, like template
    icons), it uses core's label `1.5x`, so the HTML stays identical to core's;
  - it tries both shapes core could have asked for (width x2; height x2 when height was the
    limit) and reuses the 2x file that exists, because the two can round 1px apart. Measured on
    the local wiki: against core's existing files it wrote none; a fresh page wrote 31 files where
    core wrote 43.
- **No 404 handler** recreates a missing thumb: a request for one gets a wiki 404 page, so the
  page shows a broken image (`maccabipedia_structure_knowledge.md` §7, the 338px case). This is
  on purpose: a handler would let anyone create thumbnails at any width. So before deleting
  thumbnails in bulk, wait out the parser cache (`$wgParserCacheExpireTime`, 24h by default),
  or pages still pointing at them break.
- The thumbnails were wiped once, around 2026-04-24, and grew back to more than before.
  Deleting without a setting change only buys time.
- Every File page also writes the largest "other resolutions" size (2560px) from
  `$wgImageLimits`. That's not changed yet.

## Cleanup log

- 2026-11-14: deleted 13 old extension copies (`old_Cargo`, `old-Cargo`, `o_Cargo`, `old-*`,
  `new-EmbedVideo`, which needs PHP 8) and the unused skins `skins/Metrolook` and
  `skins/Maccabipedia_old`, ~2.3k files. Proof that nothing used them: the live
  `siteinfo&siprop=extensions` versions matched the live folders, not the copies; `shared.php`
  loads every extension by folder name; 5 days of access logs had no request into them.
- About 23 extensions sit in `extensions/` without being loaded (AbuseFilter, Math, OATHAuth,
  SpamBlacklist, ...). The owner chose to keep them.
