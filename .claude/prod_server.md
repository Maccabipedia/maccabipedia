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
- Python's `ftplib` gets `425 Unable to build data connection` on any listing or download;
  `lftp` works.

## Entry processes and the `.htaccess` guard

The account runs at most **60 PHP requests at once** (CloudLinux "Entry Processes"). The
61st gets a 507/508, and the error log fills with `MHL-E2BIG`. DirectAdmin → Resource Usage
has a per-minute table: `EP` A/L/F is active/limit/faults, and `SPEED` is CPU, capped at 400%.

A request that `.htaccess` refuses never starts PHP, so it takes no slot. That makes
`public_html/.htaccess` the cheapest defence against crawler floods. It is versioned as
`infra/local-wiki/config/htaccess.prod`: edit it there, then upload it over FTP. Section 4b
refuses `Drilldown` with any query string (filters, paging, even `?utm_`) to anyone without
a login cookie; `load.php`/`api.php` are exempt, because the page loads its own CSS/JS as
`load.php?modules=ext.cargo.drilldown`. A botnet on residential IPs,
using browser User-Agents, held all 60 slots with random filter combinations until 4b went
up. The file must stay UTF-8: mod_rewrite matches the path decoded, so a Hebrew path pattern in
Windows-1255 never matches (`QUERY_STRING` and `THE_REQUEST` stay percent-encoded). `AH01630 ... 57.141.x` lines in the error log are Meta's
crawler hitting the IP block (section 6). They cost nothing.

`.htaccess` serves every file that exists in `public_html` as-is, so anything left there is public
unless a rule refuses it. Sections 4c and 7 refuse `MyLogs/` and, in any folder, every `*.log`,
its rotated copies (`.log.1`, `.log.gz`, ...) and PHP's `error_log`:
MediaWiki writes its DB error log to `MyLogs/` and the job cron writes `run_jobs.log` in the wiki
root, and both used to download for anyone (DB user and host, server paths, stack traces). Never
write a log, dump or backup into `public_html` without a rule that refuses it.

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
  modes, a missing file, `thumb=`, `Media:`/`:File:` links, the file lists and the file history,
  and requires a 2x wherever core gave one (the hook swallows its errors, so a silent failure
  must still fail a test). It fails against the version that took prod down (67 cases, the
  TypeError), a hook that throws on every image (13), and core's old setting (94). Before a deploy,
  also render real pages with their real images, old setting vs new (no errors, same 1x, same 2x
  file, no new files).
- **2x copy only, no 1.5x** (card #626). Core's `$wgResponsiveImages` wrote a 1.5x and a 2x
  copy of every image shown in an article, gallery or File page, created during the parse
  whatever the HTML used. They were 65% of all thumbnails. `LocalSettings.shared.php` turns
  the setting off and a `ThumbnailBeforeProduceHTML` hook adds the 2x copy itself:
  - only where core used to (caller of `toHtml` is `Linker`, `TraditionalImageGallery` or
    `ImagePage`). File history, Special:ListFiles and search results never had copies, and
    crawlers reach them, so a 2x there would add files;
  - never for files the handler must render (WebP, JPEGs rotated by EXIF, SVG, TIFF), paged
    files (PDF), or files from another repository (prod has none; the local wiki shows prod's
    images through one). Those keep the plain thumb: fewer files, a little softer on phones;
  - when the 2x is the original file itself (images shown near their full size, like template
    icons), it uses core's label `1.5x`, so the HTML stays identical to core's. Core judged that
    from the requested box and the hook from the thumb, so a few height-limited images get a
    different label (83 of 37k simulated cases); the file is the same either way;
  - it tries both shapes core could have asked for (width x2; height x2 when height was the
    limit) and reuses the 2x file that exists, because the two can round 1px apart. Measured on
    the local wiki: against core's existing files it wrote none; a fresh page wrote 31 files where
    core wrote 43.
- **No 404 handler** recreates a missing thumb: a request for one gets a wiki 404 page, so the
  page shows a broken image (`maccabipedia_structure_knowledge.md` §7, the 338px case). This is
  on purpose: a handler would let anyone create thumbnails at any width. So before deleting
  thumbnails in bulk, wait out the parser cache (`$wgParserCacheExpireTime`, 24h by default),
  or pages still pointing at them break. A page that renders afresh writes any thumb it needs
  again, so only cached HTML and thumb URLs typed by hand (into pages or other sites) can break; browsers never keep a copy of the page
  (`cache-control: private, must-revalidate, max-age=0`).
- **Not every size comes from articles.** Pages render thumbs at fixed boxes of their own, and a
  delete list built from widths alone hits them: the File page (800x600 preview, its 2x
  1600x1200, the "other resolution" 2560x2048, whose fit for a tall scan can equal a 1.5x: 1536px for a 2998x3997 original, 1.5x of 1024),
  Special:ListFiles (180x360), file history, search results and Special:FileDuplicateSearch
  (120x120). Fit each box to the original's dimensions (`list=allimages`) and keep those widths.
  A fresh `action=parse` does not render the File page's image section; only a real view of the
  File page (logged out and logged in) shows what it links.
- **Thumb URLs typed by hand into pages:** `list=exturlusage` with
  `euquery=*.maccabipedia.co.il` (the plain `www.` form returns nothing).
- **The next-day check is the nginx access log** (FTP `logs/nginx.<Mon>-<year>.tar.gz`, the
  newest is the previous day, written about 00:14). On normal days 0-1 thumb requests get 404
  and 60-110 get 301 (cause not looked into; compare against these days, not against zero); a 404 with a wiki page as referer is a broken image. Crawlers (bingbot)
  keep requesting deleted thumbs from their old index, with no referer; that is harmless.
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
- 2026-11-20: the owner deleted the old DB error log in `MyLogs/`, `_LocalSettings.shared.php`
  (a September copy), `.htaccess__`, `.htupdate.log`, `cargo_recreate.log`, `inode_report.txt`,
  `MaccabiPedia.games` (read only by the dead Telegram bot) and `spd.php` (the host's timezone
  test). Still undecided: `VB/` (a 2020 volleyball-site mock-up with a mail script), `testing/`
  (`testing.maccabipedia.co.il` resolves, so it may be a subdomain's folder), `export.zip`, the
  two Brothers 1906 campaign pages, and the 1.31-era leftovers `profileinfo.php`, `Gruntfile.js`,
  `StartProfiler.sample`, `serialized/`.
- 2026-11-18 to 11-21: deleted 20,931 thumbs that were only a 1.5x copy, left over from before
  the 2x-only hook: a width W where a smaller width w in the same folder has round(1.5w) = W (+-1px) and w's 2x (2w +-1px, or the original when 2w reaches it)
  2x exists, and W is not itself shown (no 2W or 1.5W file, not anyone's 2x, not one of the
  fixed sizes above). Rounds: 5, 997, 1,999, 5,977, 5,970, 5,983 (a few per round were already gone: MediaWiki clears an image's thumb folder when the file is re-uploaded). Each round had a check before and
  after (20 sampled files on up to 10 of their pages, logged out, logged in and fresh parse, all
  the image's thumbs answering 200; 60 File pages), then a folder listing after the delete, then the
  access-log check. Nothing broke. 37 paths with `"` in them were left, because the delete script quotes each path for lftp and refuses them; at 37 files they are not worth deleting by hand.
- About 23 extensions sit in `extensions/` without being loaded (AbuseFilter, Math, OATHAuth,
  SpamBlacklist, ...). The owner chose to keep them.
