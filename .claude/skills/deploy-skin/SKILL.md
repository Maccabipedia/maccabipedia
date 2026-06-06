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
bash infra/local-wiki/scripts/check-on-latest-master.sh
```

Non-zero ⇒ stop: commit/merge to master via the normal PR flow (dirty tree) or
rebase/merge `origin/master` (behind) before deploying.

## 2. Version check — gate when readable, warn when blocked

```bash
bash infra/local-wiki/scripts/check-prod-skin-version.sh
```

Compares the repo `skin.json` version against the live one on `Special:Version`
(listed under display name `Maccabipedia`, from `namemsg`):

- **Exit 1 (gate)** — prod is readable and the repo version is **not** strictly
  newer (equal ⇒ nothing to deploy or you forgot to bump; the
  `skin_version_bump` CI check enforces a bump on PRs). Stop and investigate.
- **Exit 0** — repo is strictly newer (proceed), **or** prod was unreadable
  (edge block) and the script warned. If it warned, confirm the live version in
  a browser before continuing.

## 3. Static guard tests

```bash
uv run pytest infra/local-wiki/tests
```

`pyproject.toml` sets `addopts = "-m 'not integration'"`, so a bare run already
excludes integration tests. These need no wiki: LESS comment balance, CSSJanus
image refs, slick module dep, vendored-slick sha256, VE DOM hooks.

## 4. Local integration — ALL THREE categories must run

Ensure the local wiki is up, then run HTTP + browser integration:

```bash
docker compose -f infra/local-wiki/docker-compose.yml up -d
uv run --with playwright pytest infra/local-wiki/tests -m integration -rs
```

- `--with playwright` is **required** — `test_maccabipedia_interactive.py`
  (browser test: hover dropdowns, mobile menu) does `importorskip("playwright")`
  and silently skips without it.
- **A skipped browser test counts as FAILURE.** Mechanical check: the `-rs`
  summary must report **`0 skipped`** (no `s` markers). Any `SKIPPED` on
  `test_maccabipedia_interactive` means chromium is missing — run the one-time
  setup `bash infra/local-wiki/scripts/install-playwright-browser.sh` and re-run.
  Do **not** proceed to build while that test is skipped.
- If the wiki cannot serve (fresh machine, never set up), that is one-time
  bootstrap — see `infra/local-wiki/README.md` — **stop**, it is not part of
  this deploy.

## 5. Build the upload snapshot (no prod contact)

```bash
bash infra/local-wiki/scripts/deploy-skin.sh
```

**Always surface the full snapshot path prominently as this step's output** —
it is the artifact the user drags into FileZilla, so it must be unmissable.
Never pipe this command to `/dev/null` or summarize it away; print the literal
`Local snapshot: …/Maccabipedia` line. On WSL, pass a `/mnt/c/...` base so
FileZilla on Windows can see it.

## 6. STOP — hand off the manual FileZilla upload

Claude does **not** write to prod. Give the user the atomic-rename steps:

1. Upload `<snapshot>/Maccabipedia/` to `/public_html/skins/Maccabipedia_new/`.
2. **Verify the upload completed** before swapping — the rename is atomic for
   code but not for a half-finished transfer. Confirm a late/large asset landed,
   e.g. `Maccabipedia_new/assets/images/logo.png` exists with the expected size,
   and that `skin.json` is present. Do not swap on a partial upload.
3. On the server: rename `Maccabipedia` → `Maccabipedia_old`.
4. On the server: rename `Maccabipedia_new` → `Maccabipedia`.
5. Smoke-test (step 7). If it regresses, swap back (`Maccabipedia` →
   `Maccabipedia_new`, `Maccabipedia_old` → `Maccabipedia`). Delete
   `Maccabipedia_old` only once the new skin is confirmed good.

`wfLoadSkin('Maccabipedia')` and `$wgDefaultSkin = 'Maccabipedia'` are config —
they live in LocalSettings, not the skin upload (see the `deploy-localsettings`
skill if the skin-default flip is still pending on prod).

## 7. Post-upload verification (only after the user confirms the upload)

```bash
bash infra/local-wiki/scripts/validate-site-ok.sh "https://www.maccabipedia.co.il/"
MACCABIPEDIA_LOCAL_URL=https://www.maccabipedia.co.il \
  uv run pytest -m integration infra/local-wiki/tests/test_maccabipedia_scaffold.py
```

- `validate-site-ok.sh` exit codes: **1** = HTTP 500 / error marker ⇒ real prod
  fatal, treat as a failed deploy; **2** = unreachable ⇒ the edge is blocking
  automation (expected here), confirm in a browser instead; **0** = OK.
- Confirm `Special:Version` (browser) now shows the **new** skin version, listed
  under display name `Maccabipedia`.
- **CSS may look stale for up to 24h.** `load.php` style responses are sent
  `cache-control: max-age=86400` with no version param, so browser + CDN keep
  the old stylesheet. To verify immediately, hard-refresh (Ctrl/Cmd+Shift+R) or
  cache-bust: `curl ".../load.php?...&skin=maccabipedia&cb=$(date +%s)"`. For
  all visitors at once, purge the CDN/nginx cache for `load.php` styles.
- The interactive browser test is `localhost`-pinned, so only the scaffold
  (HTTP) test applies against prod.
