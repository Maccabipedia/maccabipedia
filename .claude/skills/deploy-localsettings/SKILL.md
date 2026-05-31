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

## 2. Lint (in the prod-matching PHP runtime)

The local Docker container is `php:7.4.33` — the **same PHP as prod** — so lint
inside it, not with the host's `php` (which is 8.x and would miss 7.4
incompatibilities):

```bash
docker compose -f infra/local-wiki/docker-compose.yml up -d
docker compose -f infra/local-wiki/docker-compose.yml exec -T mediawiki \
  php -l /mw-config/LocalSettings.shared.php
```

(`./config` is mounted read-only at `/mw-config` in the container.)

## 3. Local verify (required)

The Docker wiki loads `env.local + shared.php`. Restart it and confirm the main
page still renders (a fatal returns HTTP 500, which the validator catches by
status — a body grep would miss it):

```bash
docker compose -f infra/local-wiki/docker-compose.yml restart mediawiki
bash infra/local-wiki/scripts/validate-site-ok.sh \
  "http://localhost:8080/index.php/%D7%A2%D7%9E%D7%95%D7%93_%D7%A8%D7%90%D7%A9%D7%99"
```

Non-zero ⇒ the change is broken; fix before upload. Also confirm the intended
config change actually took effect on the local page.

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
bash infra/local-wiki/scripts/validate-site-ok.sh \
  "https://www.maccabipedia.co.il/" "$MACCABIPEDIA_UA_SCRIPT"
```

Exit codes: **1** = HTTP 500 / error marker ⇒ real prod fatal, **restore the
`.bak-<ts>` immediately**; **2** = unreachable ⇒ edge blocking automation
(expected here), confirm in a browser; **0** = OK. Then confirm the config
change is actually live.
