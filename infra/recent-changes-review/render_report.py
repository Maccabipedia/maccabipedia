"""Render a recent-changes review (markdown) into one self-contained HTML page for the reports shelf.

Usage: render_report.py <review_*.md> <output.html>

The report quotes edit comments, titles and page text that any wiki user can write, and the shelf is
served on a public tunnel. So raw HTML in the markdown is never passed through: markdown-it runs with
`html` off, which escapes it, and its link validator drops `javascript:`-style URLs.
"""
import html
import sys
from datetime import datetime, timezone
from pathlib import Path

from markdown_it import MarkdownIt

PAGE = """<!DOCTYPE html>
<html lang="he">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Recent-changes review</title>
<style>
  :root{{--blue:#0a2a66;--yellow:#ffe000;--line:#e3e6eb;--bg:#f6f7f9;--card:#fff;--muted:#5b6470}}
  *{{box-sizing:border-box}}
  body{{margin:0;font-family:"Segoe UI",Arial,sans-serif;background:var(--bg);color:#1a1f29;line-height:1.55}}
  header{{background:var(--blue);color:#fff;padding:18px 16px;border-bottom:6px solid var(--yellow)}}
  header h1{{margin:0;font-size:1.15rem;color:#fff}}
  header p{{margin:6px 0 0;font-size:.8rem;opacity:.88}}
  header a{{color:#fff}}
  main{{max-width:820px;margin:0 auto;padding:12px 16px 40px}}
  h1,h2,h3{{color:var(--blue);line-height:1.3}}
  main h1{{font-size:1.15rem}}
  h2{{font-size:1.05rem;margin:26px 0 8px;padding-bottom:4px;border-bottom:2px solid var(--yellow)}}
  h3{{font-size:.98rem;margin:18px 0 6px}}
  p,li{{font-size:.92rem;unicode-bidi:plaintext}}
  li{{margin:4px 0}}
  code{{background:#eef0f4;border-radius:4px;padding:1px 5px;font-size:.85em;unicode-bidi:plaintext;overflow-wrap:anywhere}}
  pre{{background:#eef0f4;border-radius:8px;padding:10px;overflow-x:auto;font-size:.8rem;direction:ltr}}
  pre code{{background:none;padding:0}}
  table{{border-collapse:collapse;display:block;overflow-x:auto;font-size:.85rem}}
  th,td{{border:1px solid var(--line);padding:4px 8px;text-align:start}}
  blockquote{{margin:8px 0;padding:4px 12px;border-inline-start:4px solid var(--line);color:var(--muted)}}
</style>
</head>
<body>
<header>
  <h1>🔎 MaccabiPedia — Weekly recent-changes review</h1>
  <p>{source} · rendered {rendered} · <a href="./index.html">all reports</a></p>
</header>
<main dir="auto">
{body}
</main>
</body>
</html>
"""


def render(markdown_text: str, source_name: str) -> str:
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    rendered = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return PAGE.format(source=html.escape(source_name), rendered=rendered, body=md.render(markdown_text))


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    page = render(source.read_text(encoding="utf-8"), source.name)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(page, encoding="utf-8")
    tmp.replace(target)
    print(f"rendered {source.name} -> {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
