"""Run the modules against PRODUCTION data without changing anything readers see.

The modules have only ever executed against the local wiki's 222 games, all from
2021 onward. Production holds 8,367 across a century. This puts the real Lua in
front of the real data.

It needs the module pages to exist on production -- a Cargo query runs against
the wiki it lives on, so there is no way to execute this code against production
data from anywhere else. The modules are inert while they are there: no template
on production invokes them, so no reader sees any change. `cleanup` deletes them.

  deploy   write the three module pages to production (inert)
  verify   render #invoke output against real page titles, diff against the
           live page's own numbers. Read-only.
  cleanup  delete the three module pages

Nothing here edits a template or any page a reader can reach.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, "infra/perf")
from verify_numbers_against_prod import (  # noqa: E402
    BLOCK, PAIR, ROW_LABELS, TABS, clean, opponent_aliases)
from wiki_api import WikiApi  # noqa: E402

PROD = "https://www.maccabipedia.co.il"
WIKI = Path("infra/perf/wiki")

MODULES = {
    "יחידה:שיאנים": WIKI / "Module_שיאנים.lua",
    "יחידה:שיאנים/נתונים": WIKI / "Module_שיאנים_נתונים.lua",
    "יחידה:סטטיסטיקה משחקים": WIKI / "Module_סטטיסטיקה_משחקים.lua",
}
SUMMARY = ("shadow verification for the performance work -- not called by any "
           "template; see infra/perf/wiki/README.md")

RECORD = re.compile(r'<span class="record">([^<]*)</span>')

# Each leaderboard section on the page, and the module arguments that should
# reproduce it -- taken from the display template each section renders.
LEADERBOARDS = [
    ("שיאני הופעות", "מופיעים שונים", "|מספר אירוע=1, 5"),
    ("שיאני כיבושים", "כובשים שונים", "|מספר אירוע=3 |ללא תת אירוע=33"),
    ("שיאני בישולים", "שחקנים שונים", "|מספר אירוע=4"),
    ("שיאני מוצהבים", "שחקנים שונים", "|מספר אירוע=7 |תת אירוע=71"),
]


def live_section(page_html: str, section: str) -> str:
    """The page's own markup for one records section, by its visible title.

    Anchored on the title and cut at the next one: the four sections use
    identical classes, so anything looser silently compares the wrong block.
    """
    start = page_html.find(f'class="title">{section}<')
    if start < 0:
        return ""
    rest = page_html[start:]
    others = [rest.find(f'class="title">{other}<')
              for other, _, _ in LEADERBOARDS
              if other != section and rest.find(f'class="title">{other}<') > 0]
    return rest[:min(others)] if others else rest


def deploy() -> None:
    from maccabipediabot.common.wiki_login import get_site
    import pywikibot as pw

    site = get_site()
    for title, path in MODULES.items():
        page = pw.Page(site, title)
        if page.exists() and SUMMARY not in (page.text or ""):
            raise SystemExit(f"{title} already exists and is not ours -- stopping")
        page.text = path.read_text(encoding="utf-8")
        page.save(summary=SUMMARY, minor=False)
        print(f"  deployed  {title}")
    print("\nThese are inert: no production template invokes them.")


def cleanup() -> None:
    from maccabipediabot.common.wiki_login import get_site
    import pywikibot as pw

    site = get_site()
    for title in MODULES:
        page = pw.Page(site, title)
        if not page.exists():
            print(f"  gone already  {title}")
            continue
        page.delete(reason="shadow verification finished", prompt=False)
        print(f"  deleted  {title}")


def numbers_from(text: str) -> list[list[str]]:
    blocks = [[clean(value) for _, value in PAIR.findall(chunk)]
              for chunk in BLOCK.findall(text)]
    return [block for block in blocks if len(block) == len(ROW_LABELS)]


def render(api: WikiApi, title: str, wikitext: str) -> str:
    """Expand wikitext in the context of a real page, without saving anything."""
    return api.get(action="parse", text=wikitext, title=title,
                   contentmodel="wikitext", prop="text",
                   formatversion=2)["parse"]["text"]


def live(api: WikiApi, title: str) -> str:
    return api.get(action="parse", page=title, prop="text",
                   formatversion=2)["parse"]["text"]


def verify(pages: list[str]) -> int:
    api = WikiApi(PROD, pace_seconds=0.4)
    failures = 0

    for title in pages:
        if title.startswith("עונת "):
            filter_arg = "|עונה=" + title.removeprefix("עונת ").strip()
        else:
            filter_arg = "|יריבות=" + ",".join(opponent_aliases(api, title))

        page_html = live(api, title)
        want = numbers_from(page_html)
        got = numbers_from(render(
            api, title,
            "{{#invoke:סטטיסטיקה משחקים|numbersBlock" + filter_arg + "}}"))

        print(f"\n{title}")
        if not want:
            print("  no numbers block on this page -- skipped")
            continue
        if len(got) != len(want):
            failures += 1
            print(f"  MISMATCH  module rendered {len(got)} blocks, "
                  f"page has {len(want)}")
            continue
        for (label, _), mine, theirs in zip(TABS, got, want):
            ok = mine == theirs
            failures += not ok
            print(f"  numbers/{label:14s} {'ok' if ok else 'MISMATCH'}")
            if not ok:
                for row, a, b in zip(ROW_LABELS, mine, theirs):
                    if a != b:
                        print(f"      {row:10s} module {a:>8s}   page {b:>8s}")

        # Leaderboards: compare the record VALUES in order, against the values
        # the live page shows in the same section. Which tied player fills the
        # last slot is deliberately different -- the module breaks ties by name,
        # the template left it to the database -- so comparing player names
        # would flag the very change this work intends.
        for section, noun, events in LEADERBOARDS:
            mine = RECORD.findall(render(
                api, title,
                "{{#invoke:שיאנים|section|כינוי=" + noun + events +
                filter_arg + "|הגבלה=10}}"))
            theirs = RECORD.findall(live_section(page_html, section))
            ok = mine == theirs
            failures += not ok
            detail = f"{len(mine)} values" if ok else \
                f"module {len(mine)} vs page {len(theirs)}"
            print(f"  records/{section:14s} {'ok' if ok else 'MISMATCH'}  {detail}")
            if not ok:
                print(f"      module: {mine[:12]}")
                print(f"      page:   {theirs[:12]}")

    return failures


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "verify"
    if command == "deploy":
        deploy()
        return
    if command == "cleanup":
        cleanup()
        return

    source = sys.argv[2] if len(sys.argv) > 2 else None
    pages = ([line.strip() for line in
              Path(source).read_text(encoding="utf-8").splitlines() if line.strip()]
             if source else ["מכבי חיפה", "עונת 1928/29"])
    failures = verify(pages)
    print(f"\n{failures} mismatches" if failures else "\nall blocks agree")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
