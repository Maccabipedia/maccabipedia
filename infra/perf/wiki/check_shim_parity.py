"""Does each optimised template still answer the same question as the original?

This exists because a shim that forwards a fixed parameter list silently drops
every other parameter, and a dropped filter does not look like a failure -- it
looks like a number. An opponent page asking for its own yellow cards was
handed the wiki-wide total, and nothing anywhere errored.

So: render the live template and the preserved original side by side over a
matrix of the arguments real pages pass, and compare. Run against the local
wiki after apply_wiki_optimisations.py.
"""
import os
import sys

import requests

BASE = os.environ.get("MW_LOCAL_URL", "http://localhost:8080")
FULL = "/שליפה מלאה"

# One entry per template: the argument sets real callers use. Each must include
# at least one case per filter the dispatcher is supposed to route.
CASES = {
    "סטטיסטיקה/שליפות/מתקדמות/כמות אירועי שחקן": [
        "|תת אירוע=71 |מכבי=כן",
        "|יריבות=מכבי חיפה |תת אירוע=71 |מכבי=כן",
        "|יריבות=מכבי חיפה |תת אירוע=72, 73 |מכבי=כן",
        "|יריבות=מכבי חיפה |קטגוריית מפעל=ליגה |תת אירוע=71 |מכבי=כן",
        "|עונה=2021/22 |תת אירוע=71 |מכבי=כן",
        "|עונה=2021/22 |קטגוריית מפעל=גביע |תת אירוע=71 |מכבי=כן",
        "|שחקן=ערן זהבי |מספר אירוע=3",
        "|שחקן=ערן זהבי |מספר אירוע=3 |קטגוריית מפעל=ליגה",
        "|שחקן=ערן זהבי |מספר אירוע=3 |עונה=2021/22",
        "|שחקן=ערן זהבי |מספר אירוע=1, 5",
        "|אצטדיון=אצטדיון בלומפילד |מספר אירוע=3",
        "|מפעלים=ליגת העל |מספר אירוע=3",
        "|תוצאה=ניצחון |מספר אירוע=3",
        "|תוצאה מכבי=3 |מספר אירוע=3",
    ],
    "סטטיסטיקה/שליפות/מתקדמות/כמות משחקים המכילים אירוע שחקן": [
        "|שחקן=ערן זהבי |מספר אירוע=3",
        "|שחקן=ערן זהבי |מספר אירוע=3 |קטגוריית מפעל=ליגה",
        "|שחקן=ערן זהבי |מספר אירוע=3 |עונה=2021/22",
        "|שחקן=ערן זהבי |מספר אירוע=7 |תת אירוע=71",
        "|שחקן=ערן זהבי |מספר אירוע=3 |תוצאה=ניצחון",
        "|שחקן=ערן זהבי |מספר אירוע=3 |תוצאה מכבי=3",
        "|שחקן=ערן זהבי |מספר אירוע=3 |אצטדיון=אצטדיון בלומפילד",
    ],
}

session = requests.Session()
session.headers["User-Agent"] = "MaccabipediaPerfBenchmark/1.0"


def expand(wikitext: str) -> str:
    response = session.post(f"{BASE}/api.php", timeout=1800, data={
        "action": "expandtemplates", "text": wikitext, "prop": "wikitext",
        "format": "json", "formatversion": "2"})
    response.raise_for_status()
    return response.json()["expandtemplates"]["wikitext"].strip()


def main() -> None:
    failures = 0
    for template, cases in CASES.items():
        print(f"\n{template}")
        for args in cases:
            optimised = expand("{{" + template + " " + args + "}}")
            original = expand("{{" + template + FULL + " " + args + "}}")
            same = optimised == original
            failures += not same
            mark = "ok  " if same else "DIFF"
            print(f"  {mark} {optimised:>8s} vs {original:>8s}   {args}")

    print(f"\n{failures} mismatches" if failures else "\nall cases identical")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
