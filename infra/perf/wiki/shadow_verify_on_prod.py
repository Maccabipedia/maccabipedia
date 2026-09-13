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
# The "N כובשים שונים" count in each tab header. Worth comparing separately:
# the module counts distinct players in memory, while the template ran a second
# query capped at 2000 rows to get it -- so the two can legitimately disagree
# once a category holds more than 2000 distinct players, and that is exactly
# the kind of difference that must not be discovered on production.
TAB_HEADER = re.compile(r'<div class="tab-header">\s*(.*?)\s*</div>', re.S)

# Each leaderboard section on the page, and the module arguments that should
# reproduce it -- taken from the display template each section renders.
# Titles vary by page type for the same leaderboard: a referee page calls the
# yellow-cards section שיאני צהובים where an opponent page calls it שיאני
# מוצהבים, though both render the same display template.
LEADERBOARDS = [
    (("שיאני הופעות",), "מופיעים שונים", "|מספר אירוע=1, 5"),
    (("שיאני כיבושים",), "כובשים שונים", "|מספר אירוע=3 |ללא תת אירוע=33"),
    (("שיאני בישולים",), "שחקנים שונים", "|מספר אירוע=4"),
    (("שיאני מוצהבים", "שיאני צהובים"), "שחקנים שונים",
     "|מספר אירוע=7 |תת אירוע=71"),
]
SECTION_TITLE = re.compile(r'class="title">')


def live_section(page_html: str, names: tuple[str, ...]) -> str:
    """The page's own markup for one records section, by its visible title.

    Cuts at the NEXT section of any kind, not merely the next one this checker
    knows about: a referee page carries מאזן and סטטיסטיקה עונתית between the
    leaderboards, and stopping only at known titles swallowed them -- 8 tab
    headers where the section has 4.

    Takes the first occurrence deliberately. Referee pages render every section
    twice, once for שופט ראשי and once for עוזר שופט; the module implements the
    first and leaves עוזר שופט to the original template.
    """
    for name in names:
        start = page_html.find(f'class="title">{name}<')
        if start < 0:
            continue
        rest = page_html[start:]
        following = SECTION_TITLE.search(rest, pos=len(f'class="title">{name}<'))
        return rest[:following.start()] if following else rest
    return ""


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
        # Once a template invokes one of these they stop being inert, and
        # deleting them takes out every page that transcludes that template.
        users = [user.title() for user in page.getReferences(only_template_inclusion=True)]
        if users:
            raise SystemExit(
                f"{title} is now used by {len(users)} pages "
                f"(e.g. {users[0]}) -- deleting it would break them. "
                f"Revert the templates first: canary_on_prod.py revert")
        page.delete(reason="shadow verification finished", prompt=False)
        print(f"  deleted  {title}")


# Each page type hands the display templates a different filter, and each
# wrapper builds it its own way. These reproduce the wrappers' own expressions
# -- reconstructing them any other way gets a plausible but different list.
ALIAS_LIST = (
    "{{{{#arraydefine: שמות בהיסטוריה |}}}}"
    "{{{{{wrapper} |שם קבוצה={{{{PAGENAME}}}} |שם יריבה מרכזת={{{{PAGENAME}}}} }}}}"
    "{{{{#arraydefine: לשליפה |{{{{#arrayprint: שמות בהיסטוריה}}}}, {{{{PAGENAME}}}} }}}}"
    "{{{{#arrayunique: לשליפה}}}}{{{{#arrayprint: לשליפה}}}}"
)
CATEGORY_PLAYERS = ("{{סטטיסטיקה/שמות דפים מקטגוריה מופרדים לשליפה "
                    "|שם קטגוריה={{שם הדף}} }}")


def expand(api: WikiApi, title: str, wikitext: str) -> str:
    return api.post(action="expandtemplates", text=wikitext, prop="wikitext",
                   title=title, formatversion=2)["expandtemplates"]["wikitext"]


def page_wikitext(api: WikiApi, title: str) -> str:
    page = api.get(action="query", prop="revisions", rvslots="main",
                   rvprop="content", titles=title,
                   formatversion=2)["query"]["pages"][0]
    if "revisions" not in page:
        return ""
    return page["revisions"][0]["slots"]["main"].get("content", "")


def wrappers_on(api: WikiApi, title: str) -> set[str]:
    """Which wrapper templates this page uses -- the page TYPE, told by the wiki.

    Guessing from the title does not work: מגרש הדקלים and קריית שלום are
    stadium pages whose names say nothing of the sort.
    """
    payload = api.get(action="query", prop="templates", titles=title,
                      tllimit=500, formatversion=2)["query"]["pages"][0]
    return {entry["title"] for entry in payload.get("templates", [])}


def filter_for(api: WikiApi, title: str) -> str:
    """The module arguments that should reproduce this page's blocks."""
    if title.startswith("עונת "):
        return "|עונה=" + title.removeprefix("עונת ").strip()

    used = wrappers_on(api, title)
    if "תבנית:אצטדיון כדורגל" in used:
        # Unlike opponents, a stadium's historical names are a parameter on the
        # page itself, not a Cargo lookup -- so build the list the way
        # תבנית:אצטדיון כדורגל does: that parameter plus the displayed name.
        source = page_wikitext(api, title)
        history = re.search(r"\|\s*שמות בהיסטוריה\s*=\s*([^|}\n]*)", source)
        display = re.search(r"\|\s*שם להצגה\s*=\s*([^|}\n]*)", source)
        names = [part.strip() for part in
                 (history.group(1).split(",") if history else []) if part.strip()]
        names.append(display.group(1).strip() if display else title)
        return "|אצטדיונים=" + ",".join(dict.fromkeys(names))
    if "תבנית:שופט כדורגל" in used:
        # The page carries the name Cargo stores (Refs holds "אברהם קליין",
        # not the page title "כדורגל:אברהם קליין (שופט)"). The template's own
        # fallback is a #replaceset that cannot strip the suffix -- it replaces
        # "כדורגל:" WITH "(שופט)" -- so the parameter is the real source.
        source = page_wikitext(api, title)
        shown = re.search(r"\|\s*שם להצגה\s*=\s*([^|}\n]*)", source)
        name = shown.group(1).strip() if shown else \
            title.split(":", 1)[-1].removesuffix("(שופט)").strip()
        return "|שופטים=" + name
    if "תבנית:קטגוריית שחקני כדורגל" in used:
        return "|שחקנים=" + expand(api, title, CATEGORY_PLAYERS).strip()
    if title.startswith("קטגוריה:") or title.startswith("פורטל"):
        # These call the display templates bare. No filter is the only path
        # that reaches mw.loadData -- the 32 queries to 1 case.
        return ""
    return "|יריבות=" + ",".join(opponent_aliases(api, title))


def numbers_from(text: str) -> list[list[str]]:
    blocks = [[clean(value) for _, value in PAIR.findall(chunk)]
              for chunk in BLOCK.findall(text)]
    return [block for block in blocks if len(block) == len(ROW_LABELS)]


def render(api: WikiApi, title: str, wikitext: str) -> str:
    """Expand wikitext in the context of a real page, without saving anything."""
    return api.post(action="parse", text=wikitext, title=title,
                   contentmodel="wikitext", prop="text",
                   formatversion=2)["parse"]["text"]


def live(api: WikiApi, title: str) -> str | None:
    """The page as production renders it, or None if there is no such page.

    Cargo holds seasons and opponents that have no article -- עונת 1938 is a
    season in the data with no page -- and aborting the whole sweep on the first
    one loses every result after it.
    """
    try:
        return api.get(action="parse", page=title, prop="text",
                       formatversion=2)["parse"]["text"]
    except Exception as error:
        if "doesn't exist" in str(error) or "missingtitle" in str(error):
            return None
        raise


def verify(pages: list[str]) -> int:
    api = WikiApi(PROD, pace_seconds=0.4)
    failures = 0

    skipped = []
    for title in pages:
        page_html = live(api, title)
        if page_html is None:
            skipped.append(title)
            continue
        filter_arg = filter_for(api, title)
        want = numbers_from(page_html)
        got = numbers_from(render(
            api, title,
            "{{#invoke:סטטיסטיקה משחקים|numbersBlock" + filter_arg + "}}"))

        print(f"\n{title}")
        checked = 0
        # Stadium, referee, portal and category pages carry records but no
        # numbers block. Skipping the page here -- rather than just this
        # comparison -- is what let those four types report "all blocks agree"
        # while nothing at all was compared.
        if not want:
            print("  (no numbers block on this page)")
        elif len(got) != len(want):
            failures += 1
            print(f"  MISMATCH  module rendered {len(got)} blocks, "
                  f"page has {len(want)}")
        else:
            for (label, _), mine, theirs in zip(TABS, got, want):
                ok = mine == theirs
                failures += not ok
                checked += 1
                print(f"  numbers/{label:14s} {'ok' if ok else 'MISMATCH'}")
                if not ok:
                    for row, a, b in zip(ROW_LABELS, mine, theirs):
                        if a != b:
                            print(f"      {row:10s} module {a:>8s}   "
                                  f"page {b:>8s}")

        # Leaderboards: compare the record VALUES in order, against the values
        # the live page shows in the same section. Which tied player fills the
        # last slot is deliberately different -- the module breaks ties by name,
        # the template left it to the database -- so comparing player names
        # would flag the very change this work intends.
        for names, noun, events in LEADERBOARDS:
            section = names[0]
            page_section = live_section(page_html, names)
            if not page_section:
                continue  # this page does not show that leaderboard
            module_html = render(
                api, title,
                "{{#invoke:שיאנים|section|כינוי=" + noun + events +
                filter_arg + "|הגבלה=10}}")

            for what, pattern in (("values", RECORD), ("headers", TAB_HEADER)):
                mine = pattern.findall(module_html)
                theirs = pattern.findall(page_section)
                ok = mine == theirs
                failures += not ok
                checked += 1
                detail = f"{len(mine)} {what}" if ok else \
                    f"module {len(mine)} vs page {len(theirs)}"
                print(f"  {section}/{what:8s} "
                      f"{'ok' if ok else 'MISMATCH'}  {detail}")
                if not ok:
                    print(f"      module: {mine[:6]}")
                    print(f"      page:   {theirs[:6]}")

        # A page where nothing was compared is not a page that passed. Three
        # separate holes in this checker hid behind exactly that.
        if checked == 0:
            failures += 1
            print("  MISMATCH  nothing on this page was compared")

    if skipped:
        print(f"\nskipped {len(skipped)} titles with no page: "
              f"{', '.join(skipped[:8])}{' …' if len(skipped) > 8 else ''}")
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
