# MaccabiPedia Skin Deployment

No automated push. One command prepares a ready-to-upload snapshot; the upload
itself is manual via FileZilla.

```bash
# Build the upload snapshot (read-only; FTP creds auto-load from
# infra/local-wiki/.env). No args = both skins; use --skin to limit it.
bash infra/local-wiki/scripts/deploy-skin.sh                  # both skins
bash infra/local-wiki/scripts/deploy-skin.sh --skin=maccabipedia   # just the new skin

# → snapshot at ~/maccabipedia_skins/<ts>/{Maccabipedia,Metrolook}/
# FileZilla: upload <snapshot>/<skin>/ → /public_html/skins/<skin>/
# using the atomic-rename pattern the script prints.
```

## Running it (who runs the script)

The script does NOT write to prod — it makes a **read-only** FTP pull of prod's
banner assets and assembles a **local** snapshot; only the FileZilla upload
mutates prod. But because it connects to prod, Claude Code's auto-mode safety
classifier flags it as a production action and **blocks Claude from running it
directly**. Two ways through:

- **You run it in-session** (simplest) — type the command with a leading `!` so
  its output lands in the conversation:
  `! bash infra/local-wiki/scripts/deploy-skin.sh --skin=maccabipedia`
- **Grant a permission rule** — add a Bash allow rule for
  `infra/local-wiki/scripts/deploy-skin.sh` (and `sync-from-prod.sh`, which it
  calls) in `.claude/settings.json`, then Claude can build the snapshot itself.

Either way the upload step stays manual (FileZilla).

## Notes (not surfaced by the scripts)

- FTP creds live in `infra/local-wiki/.env`, **not the shell env** — an empty
  `$MACCABIPEDIA_FTP_*` does not mean creds are missing.
- Banner assets come from prod's `skins/Metrolook/assets` and are **shared by
  both skins**; the Maccabipedia skin ships none of its own. (The sync op name
  `maccabipedia-skin-assets` is misleading — it pulls Metrolook's dir.)
- Scripts aren't executable → run with `bash`, not `./`.
- **After uploading, the CSS won't change in your browser until you hard-refresh.**
  ResourceLoader recompiles on the source change, but `load.php` style responses
  are sent with `cache-control: max-age=86400, s-maxage=86400` and **no version
  param in the URL** — so both the browser and the `nginx`/CDN layer keep serving
  the old stylesheet for up to 24h. To verify a deploy: hard-refresh
  (`Ctrl/Cmd+Shift+R`) or use a cache-buster, e.g.
  `curl ".../load.php?...&skin=maccabipedia&cb=$(date +%s)" | grep <new-selector>`.
  For *all* visitors to get it immediately, purge the CDN/`nginx` cache for the
  `load.php` style responses (otherwise it clears as each client's cache expires).
- `wfLoadSkin('Maccabipedia')` is already in prod LocalSettings — skip on
  re-uploads.
- Prod smoke test:
  `MACCABIPEDIA_LOCAL_URL=https://www.maccabipedia.co.il uv run pytest -m integration infra/local-wiki/tests/test_maccabipedia_scaffold.py`
