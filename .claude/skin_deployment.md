# MaccabiPedia Skin Deployment

No automated push. One command prepares a ready-to-upload snapshot; the upload
itself is manual via FileZilla.

```bash
# Build the upload snapshot for both skins (read-only; FTP creds auto-load
# from infra/local-wiki/.env). Run with no args — the defaults cover the
# common case (both skins, ~/maccabipedia_skins base).
bash infra/local-wiki/scripts/deploy-skin.sh

# → snapshot at ~/maccabipedia_skins/<ts>/{Maccabipedia,Metrolook}/
# FileZilla: upload <snapshot>/<skin>/ → /public_html/skins/<skin>/
# using the atomic-rename pattern the script prints.
```

## Notes (not surfaced by the scripts)

- FTP creds live in `infra/local-wiki/.env`, **not the shell env** — an empty
  `$MACCABIPEDIA_FTP_*` does not mean creds are missing.
- Banner assets come from prod's `skins/Metrolook/assets` and are **shared by
  both skins**; the Maccabipedia skin ships none of its own. (The sync op name
  `maccabipedia-skin-assets` is misleading — it pulls Metrolook's dir.)
- Scripts aren't executable → run with `bash`, not `./`.
- `wfLoadSkin('Maccabipedia')` is already in prod LocalSettings — skip on
  re-uploads.
- Prod smoke test:
  `MACCABIPEDIA_LOCAL_URL=https://www.maccabipedia.co.il uv run pytest -m integration infra/local-wiki/tests/test_maccabipedia_scaffold.py`
