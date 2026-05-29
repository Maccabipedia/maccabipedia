# MaccabiPedia Skin Deployment

No automated push. One command assembles a ready-to-upload snapshot from the
repo; the upload itself is manual via FileZilla.

The build is **fully local** — the skin vendors its own banner assets under
`skins/Maccabipedia/assets/`, so there is no prod pull and no special
permission is needed to run it.

```bash
# Assemble the upload snapshot (local; default skin is maccabipedia).
bash infra/local-wiki/scripts/deploy-skin.sh                       # maccabipedia
bash infra/local-wiki/scripts/deploy-skin.sh --skin=maccabipedia

# → snapshot at ~/maccabipedia_skins/<ts>/Maccabipedia/
# FileZilla: upload <snapshot>/Maccabipedia/ → /public_html/skins/Maccabipedia/
# using the atomic-rename pattern the script prints.
```

## Notes (not surfaced by the scripts)

- **Assets are vendored** in the repo under `skins/Maccabipedia/assets/` (binary,
  protected by the skin's `.gitattributes` `-text`). The deploy packages those
  directly — it no longer pulls from prod. (Historically they were shared from
  Metrolook's `assets/` dir; that coupling is gone.)
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
