"""Is the cost of a leaderboard query the rows it returns, or the query itself?

Module:שיאנים fetches every event type and filters in Lua, so each of a page's
four leaderboards pulls the same wide result and discards three quarters of it.
Two different fixes follow from which half the cost is in:

  rows dominate  -> push the event type into SQL. Four narrow queries instead of
                    four wide ones. A small change, no restructuring.
  per-query cost -> only merging the four invokes helps, which means solving the
                    signed <shtml> tab strip that sits between them.

Measured against production's Cargo, read-only.
"""
import statistics
import sys
import time

import requests

PROD = "https://www.maccabipedia.co.il"
STADIUM = "אצטדיון בלומפילד"
REPEATS = 3

BASE = {
    "tables": "Football_Games,Games_Events,Competitions",
    "join on": "Football_Games._pageID=Games_Events._pageID,"
               "Football_Games.Competition=Competitions.OriginalName",
    "fields": "Games_Events.PlayerName=player,Games_Events.EventType=eventType,"
              "Games_Events.SubType=subType,Competitions.League=league,"
              "Competitions.Trophy=trophy,Competitions.International=intl,"
              "COUNT(*)=n",
    "group by": "Games_Events.PlayerName,Games_Events.EventType,"
                "Games_Events.SubType,Competitions.League,"
                "Competitions.Trophy,Competitions.International",
    "limit": 20000,
    "format": "json",
}
WHERE = ("Games_Events.Team=1 AND Competitions.Official=1 "
         "AND Games_Events.PlayerName IS NOT NULL "
         "AND Games_Events.PlayerName != ''")

CASES = {
    "every event type (what the module does now)": "",
    "goals only (EventType 3)": " AND Games_Events.EventType IN (3)",
    "appearances only (EventType 1,5)": " AND Games_Events.EventType IN (1,5)",
}

session = requests.Session()
session.headers["User-Agent"] = "MaccabipediaPerfBenchmark/1.0"


def run(where: str) -> tuple[int, float]:
    params = dict(BASE, title="Special:CargoExport", **{"where": where})
    started = time.monotonic()
    response = session.get(f"{PROD}/index.php", params=params, timeout=600)
    elapsed = time.monotonic() - started
    response.raise_for_status()
    if "application/json" not in response.headers.get("Content-Type", ""):
        raise SystemExit(f"CargoExport returned {response.text[:200]}")
    return len(response.json()), elapsed


def main() -> None:
    scope = sys.argv[1] if len(sys.argv) > 1 else "stadium"
    extra = ("" if scope == "wiki"
             else f" AND Football_Games.Stadium IN ('{STADIUM}')")
    print(f"scope: {'whole wiki' if scope == 'wiki' else STADIUM}\n")
    print(f"{'query':44s} {'rows':>8s} {'seconds':>9s}")
    print("-" * 66)
    for label, narrowing in CASES.items():
        timings, rows = [], 0
        for _ in range(REPEATS):
            rows, elapsed = run(WHERE + extra + narrowing)
            timings.append(elapsed)
        print(f"{label:44s} {rows:>8,} {statistics.median(timings):>8.2f}s")


if __name__ == "__main__":
    main()
