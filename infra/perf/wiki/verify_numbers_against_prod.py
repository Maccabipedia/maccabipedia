"""Recompute the general-numbers block from production Cargo, in Python.

This is deliberately NOT a diff of old template against new module -- both could
be wrong the same way. It is a second, independent implementation of what those
nine numbers mean, written from the original wikitext, run against production
data, and compared with what production currently displays.

If Python and the live page agree on every era, the semantics the Lua module was
built on are correct. Read-only: nothing is written to production.

Usage:  verify_numbers_against_prod.py [page …]
"""
import html
import re
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, "infra/perf")
from wiki_api import WikiApi  # noqa: E402

PROD = "https://www.maccabipedia.co.il"

# The four tabs, and the Competitions flags that define each, taken from the
# original כמות נתוני משחק / כמות אירועי שחקן wikitext.
TABS = [
    ("משחקים רשמיים", lambda row: row["official"] == "1"),
    ("ליגה", lambda row: row["league"] == "1"),
    ("גביע", lambda row: row["trophy"] == "1"),
    ("בינלאומי", lambda row: row["intl"] == "1"),
]
ROW_LABELS = ["משחקים", "ניצחונות", "תיקו", "הפסדים", "שערים", "ספיגות",
              "שער נקי", "צהובים", "אדומים"]

# Anchor on the block, not on the class pair: describe/info are used elsewhere
# on the same page (the seasonal table), and matching them loosely silently
# picked up four wrong blocks and reported six mismatches that did not exist.
BLOCK = re.compile(r'<div class="general-stats-list">(.*?)(?=<div class="general-stats-list">|\Z)', re.S)
PAIR = re.compile(r'<span class="describe">(.*?)</span>\s*<span class="info">(.*?)(?:<span class="small">|</span>)', re.S)


def clean(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


# Exactly what תבנית:יריבת כדורגל does to build יריבות לשליפה (its lines 5-9):
# the club's historical names, looked up from Cargo, plus the page's own name.
# Reconstructing this any other way gets it wrong -- the aliases are not a page
# parameter, and the obvious-looking המרות template answers a different question
# and returns "ללא תוצאות" for a name carrying a gershayim.
ALIASES = (
    "{{#arraydefine: שמות בהיסטוריה |}}"
    "{{יריבת כדורגל/שמירת שמות הקבוצה |שם קבוצה={{PAGENAME}}"
    " |שם יריבה מרכזת={{PAGENAME}} }}"
    "{{#arraydefine: יריבות לשליפה |{{#arrayprint: שמות בהיסטוריה}}, {{PAGENAME}} }}"
    "{{#arrayunique: יריבות לשליפה}}"
    "{{#arrayprint: יריבות לשליפה}}"
)


def opponent_aliases(api: WikiApi, page: str) -> list[str]:
    """The names this opponent page actually queries under, per the wiki."""
    raw = api.get(action="expandtemplates", text=ALIASES, prop="wikitext",
                  title=page, formatversion=2)["expandtemplates"]["wikitext"]
    names = []
    for item in raw.strip().strip("()").split(","):
        name = item.strip().strip("'\"")
        # Cargo stores Opponent with quotes stripped -- see structure §16.
        name = re.sub(r"['\"]|&#3[49];|&quot;|&apos;", "", name)
        if name:
            names.append(name)
    return names


def sql_in(values: list[str]) -> str:
    return "(" + ",".join("'" + v.replace("'", "''") + "'" for v in values) + ")"


def expected(api: WikiApi, where: str) -> dict[str, list[int]]:
    """The nine numbers per tab, computed here rather than read off the page."""
    games = api.get(
        action="cargoquery", tables="Football_Games,Competitions",
        join_on="Football_Games.Competition=Competitions.OriginalName",
        where=where,
        fields="Competitions.League=league,Competitions.Trophy=trophy,"
               "Competitions.International=intl,Competitions.Official=official,"
               "Football_Games.ResultOpt=resultOpt,"
               "Football_Games.ResultMaccabi=scored,"
               "Football_Games.ResultOpponent=conceded,COUNT(*)=n",
        group_by="Competitions.League,Competitions.Trophy,"
                 "Competitions.International,Competitions.Official,"
                 "Football_Games.ResultOpt,Football_Games.ResultMaccabi,"
                 "Football_Games.ResultOpponent",
        limit=5000, formatversion=2)["cargoquery"]

    cards = api.get(
        action="cargoquery", tables="Football_Games,Games_Events,Competitions",
        join_on="Football_Games._pageID=Games_Events._pageID,"
                "Football_Games.Competition=Competitions.OriginalName",
        where=where + " AND Games_Events.Team=1 "
                      "AND Games_Events.SubType IN (71,72,73)",
        fields="Competitions.League=league,Competitions.Trophy=trophy,"
               "Competitions.International=intl,Competitions.Official=official,"
               "Games_Events.SubType=subType,COUNT(*)=n",
        group_by="Competitions.League,Competitions.Trophy,"
                 "Competitions.International,Competitions.Official,"
                 "Games_Events.SubType",
        limit=5000, formatversion=2)["cargoquery"]

    out = {}
    for label, keep in TABS:
        total = defaultdict(int)
        for entry in games:
            row = entry["title"]
            if not keep(row):
                continue
            count = int(row["n"])
            total[{"1": "wins", "2": "draws", "3": "losses"}.get(
                row["resultOpt"], "other")] += count
            total["scored"] += int(row["scored"] or 0) * count
            total["conceded"] += int(row["conceded"] or 0) * count
            if row["conceded"] == "0":
                total["clean"] += count
        for entry in cards:
            row = entry["title"]
            if not keep(row):
                continue
            total["yellow" if row["subType"] == "71" else "red"] += int(row["n"])
        played = total["wins"] + total["draws"] + total["losses"]
        out[label] = [played, total["wins"], total["draws"], total["losses"],
                      total["scored"], total["conceded"], total["clean"],
                      total["yellow"], total["red"]]
    return out


def displayed(api: WikiApi, page: str) -> dict[str, list[str]]:
    """The nine numbers per tab as production renders them today."""
    text = api.get(action="parse", page=page, prop="text",
                   formatversion=2)["parse"]["text"]
    blocks = [[clean(value) for _, value in PAIR.findall(chunk)]
              for chunk in BLOCK.findall(text)]
    blocks = [block for block in blocks if len(block) == len(ROW_LABELS)]
    if len(blocks) != len(TABS):
        raise SystemExit(f"{page}: expected {len(TABS)} stats blocks, "
                         f"found {len(blocks)} -- page layout changed")
    # The fourth block carries id="tab3-content" on production (a duplicate-id
    # bug in the template), so pair by document order, not by id.
    return {tab[0]: block for tab, block in zip(TABS, blocks)}


def main() -> None:
    api = WikiApi(PROD, pace_seconds=0.4)
    pages = sys.argv[1:] or ["מכבי חיפה", "הפועל תל אביב"]
    if len(pages) == 1 and Path(pages[0]).is_file():
        pages = [line.strip() for line in
                 Path(pages[0]).read_text(encoding="utf-8").splitlines()
                 if line.strip()]

    failures = 0
    for page in pages:
        # Season pages filter on Season; opponent pages on the club's aliases.
        if page.startswith("עונת "):
            season = page.removeprefix("עונת ").strip()
            where = f'Football_Games.Season="{season}"'
            shown = season
        else:
            aliases = opponent_aliases(api, page)
            where = f"Football_Games.Opponent IN {sql_in(aliases)}"
            shown = aliases
        want = expected(api, where)
        have = displayed(api, page)
        print(f"\n{page}   queried as {shown}")
        for label, _ in TABS:
            mine = [str(v) for v in want[label]]
            theirs = have.get(label)
            if theirs is None:
                print(f"  {label:16s} no block rendered on the page")
                continue
            ok = mine == theirs
            failures += not ok
            print(f"  {label:16s} {'ok' if ok else 'MISMATCH'}")
            if not ok:
                for row_label, a, b in zip(ROW_LABELS, mine, theirs):
                    if a != b:
                        print(f"      {row_label:10s} computed {a:>8s}   "
                              f"page shows {b:>8s}")

    print(f"\n{failures} mismatches" if failures else "\nevery tab agrees")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
