# Local MaccabiPedia (Docker)

Runs a local MediaWiki 1.39.11 + PHP 7.4 + MariaDB mirror of the production
MaccabiPedia site. MediaWiki itself is built into the image. The default
MaccabiPedia skin is the `SkinMustache`-based skin vendored at
`<repo-root>/skins/Maccabipedia/`; the legacy fallback skin is vendored at
`<repo-root>/skins/Metrolook/` and supplies the shared binary banner
`assets/`. Only those binary banner `assets/` and the prod extensions
are pulled from the FTP server into `synced/`. Site-wide config lives in
`config/LocalSettings.shared.php` which ships byte-equivalent to prod.
Dev-only values (DB host, URL, fake secrets) are in
`config/LocalSettings.env.local.php` — prod has its own `.env.prod.php`.

## Prerequisites

- **Linux / WSL (Ubuntu/Debian):** run `./scripts/setup-host.sh` once. It
  installs `docker.io`, `docker-compose-v2`, and `lftp`, starts the docker
  daemon, and adds you to the `docker` group. Open a new shell (or
  `newgrp docker`) so `docker` works without sudo afterwards.
- **macOS / Windows:** install Docker Desktop manually (with WSL 2
  integration on Windows). `lftp` is needed for the prod-sync script and
  can be installed via Homebrew / Scoop.

## First-time setup

```bash
cd infra/local-wiki
./scripts/setup-host.sh               # docker + lftp + group membership

# FTP credentials (file is gitignored)
cp .env.example .env
chmod 600 .env                        # fill in host/user/pass/remote-root

# Pull what isn't vendored: extensions + skin assets + Common.css/js +
# sample pages. ~few minutes.
./scripts/sync-from-prod.sh bootstrap

# Bring up the stack (first build takes a few minutes)
docker compose up -d --build

# Import every pulled XML dump (starter pages + MediaWiki:Common.{css,js})
./scripts/seed-content.sh
```

Open http://localhost:8080 — you'll see the `מכביפדיה` site with the
MaccabiPedia skin, prod's extension set, and the seeded pages rendering.

Admin user: `maccabi` / `maccabi` (from `docker-compose.yml`; local-only).

## Adjusting the seed set

Pages pulled by `bootstrap` are listed in
`scripts/content-manifests/starter.manifest`. Edit that file (one page
title per line, `#` for comments), then:

```bash
./scripts/sync-from-prod.sh pages scripts/content-manifests/starter.manifest
./scripts/seed-content.sh starter
```

Now browse e.g. `http://localhost:8080/index.php/ערן_זהבי`.

**Limitation**: Cargo data tables aren't populated — `Special:Export`
returns page wikitext only. Full Cargo-table parity needs a real DB dump
(see "Follow-ups").

## Tear down

```bash
docker compose down          # keep data
docker compose down -v       # wipe DB + images + install marker
```

## Files

- `Dockerfile` — `FROM php:7.4.33-apache-bullseye`, installs MW 1.39.11 +
  PHP extensions (intl, gd, mysqli, zip, mbstring, calendar, opcache, apcu
  pinned to 5.1.24). All versions pinned for reproducibility.
- `docker-compose.yml` — `mediawiki` (built locally) + `mariadb:10.11`.
  Named volumes: `mw_db`, `mw_images`, `mw_config` (first-boot marker).
  Mediawiki healthcheck polls `http://localhost/`.
- `entrypoint.sh` — on first boot runs `install.php` with prefix `MPMW_`
  (output discarded to `/tmp`, state tracked via `/generated/.installed`);
  every boot copies the stub to `/var/www/html/LocalSettings.php` as a
  real file and symlinks env+shared as siblings, `php -l` checks the
  result, then runs `update.php --quick`.
- `config/` — the three split `LocalSettings*.php` files. Mounted
  read-only into the container at `/mw-config/`.
  - `LocalSettings.stub.php` — 5-line bootstrap: `require_once` env then
    shared.
  - `LocalSettings.env.local.php` — dev env values (`mariadb` host, dev
    creds from `MW_DB_*` env, verbose errors, `CACHE_NONE`, fake keys).
  - `LocalSettings.shared.php` — site-wide config (extensions, skins,
    namespaces, hooks, Cargo, ContactPage, TabberNeue, …). Byte-equivalent
    to prod's `LocalSettings.shared.php`; prod uploads this file manually
    when it changes.
- `scripts/setup-host.sh` — one-shot host-prereq installer (docker,
  compose, lftp). Idempotent.
- `scripts/sync-from-prod.sh` — named-op wrapper around `lftp` (+ `curl`
  for HTTP). Download-only. See `.env.example` for env vars.
  Ops: `bootstrap`, `maccabipedia-skin-assets`, `extensions`, `favicon`,
  `logo-assets`, `localsettings`, `versions`, `site-scripts`,
  `pages <manifest>`.
  The skin source is vendored at `<repo-root>/skins/Metrolook/` and is
  NOT touched by this script — only the binary banners under
  `skins/Metrolook/assets/` are pulled from prod.
  `site-scripts` pulls `MediaWiki:Common.css` + `MediaWiki:Common.js` (the
  site-wide CSS/JS that back the `site.styles` bundle, CanvasJS hooks, and
  the fanzine form); kept separate from `starter.manifest` because they're
  site-wide assets, not sample content.
- `scripts/seed-content.sh` — imports pulled XML dumps into the running
  container via `importDump.php`, then `rebuildall.php` + `runJobs.php`.
- `scripts/content-manifests/starter.manifest` — editable list of page titles
  to pull.

## Follow-ups (not yet shipped)

- Prod DB dump importer for full Cargo-table parity. Requires a `.sql`
  export from the hosting panel's phpMyAdmin.
- Bot-target integration: a `[maccabipedia-local]` profile in
  `pywikibot_configs/user-password.py` + `MACCABIPEDIA_SITE=local` env
  switch so the Python bots target the local wiki.
