#!/usr/bin/env python3
"""Download wiki PAGES (content) from the production MaccabiPedia site over HTTP
(Special:Export) into infra/local-wiki/downloaded-pages/, for optionally seeding
real content into the local wiki. NOT needed to render or verify the skin —
extensions are baked into the Docker image and the skin's assets (incl. favicon)
are vendored in the repo. Import the result with `bash scripts/seed-content.sh`.

Runs on the host (no credentials; read-only — only fetches page XML):
  uv run python scripts/download_pages_from_prod.py <op> [args]

Ops:
  bootstrap            site-scripts + pages (scripts/content-manifests/starter.manifest)
  site-scripts         MediaWiki:Common.css + MediaWiki:Common.js
  pages <manifest>     every title in <manifest> (one per line; blank / '#' ignored)

Optional env: MACCABIPEDIA_WEB_URL  (default: https://www.maccabipedia.co.il)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

import requests

_SCRIPT_DIR = Path(__file__).resolve().parent
_LOCAL_WIKI_DIR = _SCRIPT_DIR.parent
_DOWNLOAD_DIR = _LOCAL_WIKI_DIR / "downloaded-pages"
_STARTER_MANIFEST = _SCRIPT_DIR / "content-manifests" / "starter.manifest"
_BASE_URL = os.environ.get("MACCABIPEDIA_WEB_URL", "https://www.maccabipedia.co.il").rstrip("/")
_SITE_SCRIPT_TITLES = ["MediaWiki:Common.css", "MediaWiki:Common.js"]


# URL-encoded byte budget for the `pages` param of one export GET. Apache's
# default request-line limit is ~8K; leave headroom for the host, path and the
# other query params. Hebrew titles inflate ~3x when percent-encoded, so a
# season manifest (~170 titles) needs several chunks.
_PAGES_PARAM_BUDGET = 6000


def chunk_titles(titles: list[str], budget: int = _PAGES_PARAM_BUDGET) -> list[list[str]]:
    """Split titles into batches whose URL-encoded `pages` value fits `budget`."""
    chunks: list[list[str]] = []
    current: list[str] = []
    current_len = 0
    for title in titles:
        encoded_len = len(quote(title)) + len(quote("\n"))
        if current and current_len + encoded_len > budget:
            chunks.append(current)
            current = []
            current_len = 0
        current.append(title)
        current_len += encoded_len
    if current:
        chunks.append(current)
    return chunks


def merge_export_dumps(dumps: list[str]) -> str:
    """Merge several Special:Export XML dumps into one importable document.

    Keeps the first dump's <mediawiki> envelope (header + siteinfo) and splices
    the <page> elements of the rest in before its closing tag.
    """
    first = dumps[0]
    closing_index = first.rindex("</mediawiki>")
    parts = [first[:closing_index]]
    for dump in dumps[1:]:
        if "<page>" not in dump:
            continue  # every title in this chunk was missing on prod
        pages_start = dump.index("<page>")
        pages_end = dump.rindex("</page>") + len("</page>")
        parts.append(dump[pages_start:pages_end] + "\n")
    parts.append(first[closing_index:])
    return "".join(parts)


def _export_chunk(titles: list[str]) -> str:
    # GET (not POST): prod's edge layer rejects the POST export form; GET with
    # the same params works. curonly=1 = current revision only; templates=1 also
    # pulls templates the pages reference.
    params = {
        "title": "Special:Export",
        "pages": "\n".join(titles),
        "curonly": "1",
        "templates": "1",
        "action": "submit",
    }
    # Generous timeout: templates=1 exports can take a while on a big page set.
    response = requests.get(f"{_BASE_URL}/index.php", params=params, timeout=120)
    response.raise_for_status()

    # Special:Export returns MediaWiki XML on success; an HTML error page won't
    # carry the <mediawiki root element near the top. Anchor the match to
    # "<mediawiki" + whitespace so an HTML page that merely mentions the word
    # can't slip through.
    if not re.search(r"<mediawiki\s", response.text[:512]):
        sys.exit("ERROR: response is not a MediaWiki XML dump — check the site / titles")
    return response.text


def _export(stem: str, titles: list[str]) -> None:
    titles = [title for title in titles if title.strip()]
    if not titles:
        sys.exit("ERROR: no page titles to export")
    _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    out_file = _DOWNLOAD_DIR / f"{stem}.xml"

    chunks = chunk_titles(titles)
    print(
        f"==> GET {_BASE_URL}/index.php?title=Special:Export  "
        f"({len(titles)} titles in {len(chunks)} request(s)) -> {out_file}"
    )
    dumps = [_export_chunk(chunk) for chunk in chunks]

    out_file.write_text(merge_export_dumps(dumps), encoding="utf-8")
    print(f"    OK — {out_file.stat().st_size} bytes")


def _titles_from_manifest(path: Path) -> list[str]:
    if not path.is_file():
        sys.exit(f"ERROR: manifest not found: {path}")
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def main() -> None:
    op = sys.argv[1] if len(sys.argv) > 1 else ""
    if op == "site-scripts":
        _export("site-scripts", _SITE_SCRIPT_TITLES)
    elif op == "pages":
        if len(sys.argv) < 3:
            sys.exit("ERROR: 'pages' op requires a manifest path\n"
                     "  e.g. ... pages scripts/content-manifests/starter.manifest")
        manifest = Path(sys.argv[2])
        _export(manifest.stem, _titles_from_manifest(manifest))
    elif op == "bootstrap":
        _export("site-scripts", _SITE_SCRIPT_TITLES)
        _export(_STARTER_MANIFEST.stem, _titles_from_manifest(_STARTER_MANIFEST))
    elif op in ("-h", "--help", "help"):
        print(__doc__)
    else:
        sys.exit(f"ERROR: unknown op {op!r}\n{__doc__}")


if __name__ == "__main__":
    main()
