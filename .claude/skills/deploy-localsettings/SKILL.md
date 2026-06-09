---
name: deploy-localsettings
description: Use when deploying any change to infra/local-wiki/config/LocalSettings.shared.php (site-wide MediaWiki config) to the Maccabipedia production wiki. Lints + verifies the change locally, then hands off the MANUAL FileZilla upload of shared.php ONLY (never env.prod.php or the stub). Never writes to prod itself.
---

# Deploy LocalSettings (shared.php) to production

On prod, `LocalSettings.php` is a stub that does `require_once env.prod.php`
(secrets, **server-only, not in repo**) then `require_once
LocalSettings.shared.php` (site-wide config, **tracked in repo**). This skill
deploys `shared.php` ONLY. **Master is the source of truth.** A syntax error in
`shared.php` fatals the whole wiki, so verify locally before uploading.

Run these in order. Stop and report on any failure.

## 1. Sync gate — ship master, not a dirty tree

```bash
bash infra/local-wiki/scripts/check-on-latest-master.sh
```

Non-zero ⇒ stop: commit/merge to master (dirty) or rebase (behind) first.

## 2. Lint (in the prod-matching PHP 7.4 runtime)

The wiki image is `php:7.4.33` — the **same PHP as prod** — so lint with it, not
the host `php` (8.x, which misses 7.4 incompatibilities). Use a disposable
container that mounts this worktree's config, so it does not depend on the
running container's mount state:

```bash
docker run --rm --entrypoint php \
  -v "$(pwd)/infra/local-wiki/config:/cfg:ro" \
  local-wiki-mediawiki -l /cfg/LocalSettings.shared.php
```

(If the `local-wiki-mediawiki` image is missing, build it first:
`docker compose -f infra/local-wiki/docker-compose.yml build`.)

## 3. Local verify (required)

Restart the wiki so it reloads the config, then confirm the site renders.
`validate-site-ok.sh` catches a fatal **whichever way it surfaces** — HTTP 500
(prod-style, `display_errors` off) or HTTP 200 with an error in the body (local
dev, `display_errors` on); a status-only check would miss the latter. Hit the
root (same path style as prod — no `index.php`):

```bash
docker compose -f infra/local-wiki/docker-compose.yml up -d
docker compose -f infra/local-wiki/docker-compose.yml restart mediawiki
bash infra/local-wiki/scripts/validate-site-ok.sh "http://localhost:8080/"
```

Non-zero ⇒ the change broke the site; fix before upload. `shared.php` is
site-level config, so "the site loads without a fatal" is the smoke we need —
no skin/rendering test suite here. If your change is something you can eyeball
(e.g. a `$wgDefaultSkin` flip or an extension's `Special:` page), confirm it
took effect too.

## 4. STOP — hand off the manual FileZilla upload

Claude does **not** write to prod. Upload `LocalSettings.shared.php` **only**:

1. On the server, back up the current file: rename
   `LocalSettings.shared.php` → `LocalSettings.shared.php.bak-<UTC-ts>`.
2. Upload the repo's `infra/local-wiki/config/LocalSettings.shared.php` to the
   server's LocalSettings directory.
3. **NEVER** upload or overwrite `LocalSettings.env.prod.php` (secrets) or the
   stub `LocalSettings.php` unless that specific file changed.

## 5. Smoke test prod

```bash
bash infra/local-wiki/scripts/validate-site-ok.sh "https://www.maccabipedia.co.il/"
```

Exit codes: **1** = HTTP 500 / error marker ⇒ real prod fatal, **restore the
`.bak-<ts>` immediately**; **2** = unreachable ⇒ edge blocking automation
(expected here), confirm in a browser; **0** = OK. Then confirm the config
change is actually live.
