"""Check that the repo research-sources doc and the wiki page מקורות שימושיים list the same sources.

usage: uv run python .claude/scripts/research_sources_sync.py [--wiki-file PAGE.txt]

Reads the live wiki page (or a saved copy with --wiki-file) and `.claude/maccabipedia_research_sources.md`,
reduces every link to a source key, and prints the keys found on one side only. Exit code 1 when they differ.

A source key is the host for single-purpose sites, and host + channel/item/topic for sites that hold many
unrelated sources (YouTube, forums, archive.org, Wayback snapshots, ...). So two links into the same site
count as one source, while two different YouTube channels count as two.
"""
import argparse
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

DOC = Path(__file__).resolve().parents[1] / "maccabipedia_research_sources.md"
WIKI_TITLE = "מקורות שימושיים"
URL = re.compile(r"https?://[^\s\]\)\|<>\"'`]+")
# Links the doc carries as how-to detail of a source that is listed on both sides, or as a pointer to the wiki page itself.
DOC_ONLY = {"maccabipedia.co.il", "api-live.euroleague.net"}
# Hosts whose path names the source, not just the site.
PATH_HOSTS = {"youtube.com", "dailymotion.com", "vimeo.com", "facebook.com", "twitter.com", "x.com",
              "en.wikipedia.org", "he.wikipedia.org", "safsal.co.il", "volleybox.net", "12p.co.il"}


def source_key(url: str) -> str:
    parts = urlsplit(unquote(url.rstrip(".,;:")))
    host = re.sub(r"^(www|m)\.", "", parts.netloc.lower()).split(":")[0]
    segments = [s for s in parts.path.split("/") if s]
    if host == "web.archive.org":
        inner = re.search(r"https?://.*|\*/(.*)", parts.path + (f"?{parts.query}" if parts.query else ""))
        target = inner.group(0) if inner and inner.group(0).startswith("http") else f"http://{inner.group(1)}" if inner else ""
        return "wayback:" + source_key(target) if target else host
    if host == "forum.12p.co.il":
        query = parse_qs(parts.query)
        topic = (query.get("showtopic") or query.get("id") or [""])[0]
        return f"{host}/topic/{topic}" if topic else host
    if host == "archive.org":
        return f"{host}/details/{segments[1]}" if len(segments) > 1 and segments[0] == "details" else host
    if host == "youtube.com":
        if segments and segments[0] in ("user", "channel", "c") and len(segments) > 1:
            return f"{host}/{segments[0]}/{segments[1].lower()}"
        return f"{host}/{segments[0].lower()}" if segments else host
    if host in PATH_HOSTS:
        return f"{host}/{'/'.join(segments[:2]).lower()}" if segments else host
    return host


def keys(text: str) -> dict:
    found = {}
    for line in text.splitlines():
        for url in URL.findall(line):
            found.setdefault(source_key(url), line.strip()[:140])
    return found


def wiki_text(path: str | None) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8")
    import pywikibot

    from maccabipediabot.common.wiki_login import get_site
    return pywikibot.Page(get_site(), WIKI_TITLE).text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wiki-file", help="a saved copy of the wiki page's wikitext instead of fetching it")
    args = parser.parse_args()
    wiki = keys(wiki_text(args.wiki_file))
    doc = {k: v for k, v in keys(DOC.read_text(encoding="utf-8")).items() if k not in DOC_ONLY}
    only_wiki, only_doc = sorted(set(wiki) - set(doc)), sorted(set(doc) - set(wiki))
    print(f"sources: wiki {len(wiki)}, doc {len(doc)}, shared {len(set(wiki) & set(doc))}")
    for title, missing, where in (("on the wiki page only", only_wiki, wiki), ("in the doc only", only_doc, doc)):
        if missing:
            print(f"\n{title} ({len(missing)}):")
            for key in missing:
                print(f"  {key}    <- {where[key]}")
    if not only_wiki and not only_doc:
        print("in sync")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
