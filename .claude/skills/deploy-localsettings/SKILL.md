---
name: deploy-localsettings
description: Use when deploying a site-config change to the Maccabipedia production wiki — editing infra/local-wiki/config/LocalSettings.shared.php to enable an extension, change a setting, or flip $wgDefaultSkin. Lints + verifies the change locally, then hands off the MANUAL FileZilla upload of shared.php ONLY (never env.prod.php or the stub). Never writes to prod itself.
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
git fetch origin
git status --porcelain                       # must be EMPTY
git rev-list --count HEAD..origin/master     # must be 0 (not behind)
```

## 2. Lint

```bash
php -l infra/local-wiki/config/LocalSettings.shared.php
```

Local PHP is 8.3 but prod is **PHP 7.4** — lint catches syntax errors, not
7.4-incompatible 8.x syntax. Keep `shared.php` plain config.

## 3. Local verify (required)

The Docker wiki loads `env.local + shared.php`. Restart it and confirm no fatal:

```bash
docker compose -f infra/local-wiki/docker-compose.yml up -d
docker compose -f infra/local-wiki/docker-compose.yml restart mediawiki
curl -fsS "http://localhost:8080/index.php/%D7%A2%D7%9E%D7%95%D7%93_%D7%A8%D7%90%D7%A9%D7%99" \
  | grep -qiE 'fatal|exception|MWException' && echo "FATAL — fix before upload" || echo "renders OK"
```

A white-screen / fatal ⇒ the change is broken; fix before upload. Confirm the
intended config change actually took effect on the local page.

## 4. No reliable prod drift-check — rely on master + backup

There is **no clean way to diff the server's `shared.php`**: the
`sync-from-prod.sh localsettings` op pulls the prod **stub** `LocalSettings.php`
(into `synced/LocalSettings.prod-snapshot.php`), not `shared.php`. So do not try
to diff against prod. Instead trust the source-of-truth model — you are on
latest master (step 1) — and rely on the `.bak` rollback in step 5 if prod
misbehaves. (If a verified prod baseline is ever needed, add a `shared` mode to
`sync-from-prod.sh` first.)

## 5. STOP — hand off the manual FileZilla upload

Claude does **not** write to prod. Upload `LocalSettings.shared.php` **only**:

1. On the server, back up the current file: rename
   `LocalSettings.shared.php` → `LocalSettings.shared.php.bak-<UTC-ts>`.
2. Upload the repo's `infra/local-wiki/config/LocalSettings.shared.php` to the
   server's LocalSettings directory.
3. **NEVER** upload or overwrite `LocalSettings.env.prod.php` (secrets) or the
   stub `LocalSettings.php` unless that specific file changed.

## 6. Smoke test prod

```bash
curl -fsS -A "$MACCABIPEDIA_UA_SCRIPT" "https://www.maccabipedia.co.il/" \
  | grep -qiE 'fatal|exception|MWException' && echo "PROD FATAL — restore .bak" || echo "prod OK"
```

Confirm no fatal and the config change is live. If it fatals, restore the
`.bak-<ts>` file on the server immediately.
