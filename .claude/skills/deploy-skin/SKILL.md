---
name: deploy-skin
description: Use when deploying a new version of the Maccabipedia MediaWiki skin (skins/Maccabipedia/) to production. Runs the full pre-flight — sync gate, prod version check, and ALL three test categories (static guards, HTTP integration, browser/Playwright) — then builds the upload snapshot and hands off the MANUAL FileZilla upload + post-deploy verification. Never writes to prod itself.
---

# Deploy the Maccabipedia skin to production

Deploys `skins/Maccabipedia/` to prod. **Master is the source of truth** — you
ship what is committed and merged, never a dirty working tree. Claude runs every
local/read step and the build, then **STOPS**: the FileZilla upload is manual.

Run these in order. Stop and report on any failure.

## 1. Sync gate — ship master, not a dirty tree

```bash
git fetch origin
git status --porcelain                       # must be EMPTY (clean tree)
git rev-list --count HEAD..origin/master     # must be 0 (not behind master)
```

If the tree is dirty → commit/merge to master via the normal PR flow first.
If behind master → rebase/merge `origin/master` before deploying.

## 2. Version check (fail-fast)

Compare the live prod skin version against the repo's:

```bash
jq -r '.version' skins/Maccabipedia/skin.json
curl -fsS -A "$MACCABIPEDIA_UA_SCRIPT" \
  "https://www.maccabipedia.co.il/index.php/Special:Version" \
  | grep -iA2 'MaccabipediaSkin'
```

The repo version should be **greater** than the live version. If they are
**equal**, warn: either nothing changed or you forgot to bump (the
`skin_version_bump` CI check enforces a bump on PRs). Do not hard-fail here.

## 3. Static guard tests

```bash
uv run pytest infra/local-wiki/tests -m "not integration"
```

These need no wiki: LESS comment balance, CSSJanus image refs, slick module
dep, vendored-slick sha256, VE DOM hooks.

## 4. Local integration — ALL THREE categories must run

Ensure the local wiki is up, then run HTTP + browser integration:

```bash
docker compose -f infra/local-wiki/docker-compose.yml up -d
uv run --with playwright pytest infra/local-wiki/tests -m integration -v
```

- `--with playwright` is **required** — `test_maccabipedia_interactive.py`
  (browser test: hover dropdowns, mobile menu) does `importorskip("playwright")`
  and silently skips without it.
- **A skipped browser test counts as FAILURE.** Confirm the interactive tests
  report PASSED, not SKIPPED. If they skipped, install the browser
  (`uv run --with playwright playwright install chromium`) and re-run.
- If the wiki cannot serve (fresh machine, never set up), that is one-time
  bootstrap — see `infra/local-wiki/README.md` — **stop**, it is not part of
  this deploy.

## 5. Build the upload snapshot (no prod contact)

```bash
bash infra/local-wiki/scripts/deploy-skin.sh
```

Report the snapshot path it prints (`~/maccabipedia_skins/<ts>/Maccabipedia/`).
On WSL, pass a `/mnt/c/...` base so FileZilla on Windows can see it.

## 6. STOP — hand off the manual FileZilla upload

Claude does **not** write to prod. Give the user the atomic-rename steps:

1. Upload `<snapshot>/Maccabipedia/` to `/public_html/skins/Maccabipedia_new/`.
2. On the server: rename `Maccabipedia` → `Maccabipedia_old`.
3. On the server: rename `Maccabipedia_new` → `Maccabipedia`.
4. Smoke-test (step 7), then delete `Maccabipedia_old` later.

`wfLoadSkin('Maccabipedia')` and `$wgDefaultSkin = 'Maccabipedia'` are config —
they live in LocalSettings, not the skin upload (see the `deploy-localsettings`
skill if the skin-default flip is still pending on prod).

## 7. Post-upload verification (only after the user confirms the upload)

```bash
MACCABIPEDIA_LOCAL_URL=https://www.maccabipedia.co.il \
  uv run pytest -m integration infra/local-wiki/tests/test_maccabipedia_scaffold.py
curl -fsS -A "$MACCABIPEDIA_UA_SCRIPT" \
  "https://www.maccabipedia.co.il/index.php/Special:Version" | grep -iA2 'MaccabipediaSkin'
```

- Confirm `Special:Version` now shows the **new** skin version.
- **CSS may look stale for up to 24h.** `load.php` style responses are sent
  `cache-control: max-age=86400` with no version param, so browser + CDN keep
  the old stylesheet. To verify immediately, hard-refresh (Ctrl/Cmd+Shift+R) or
  cache-bust: `curl ".../load.php?...&skin=maccabipedia&cb=$(date +%s)"`. For
  all visitors at once, purge the CDN/nginx cache for `load.php` styles.
- The interactive browser test is `localhost`-pinned, so only the scaffold
  (HTTP) test applies against prod.
