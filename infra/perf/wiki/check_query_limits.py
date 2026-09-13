"""Will the modules' grouped queries fit inside their row limit on PRODUCTION?

Every module here reads one grouped aggregate and computes the displayed numbers
from it. If that aggregate returns more rows than the limit, Cargo truncates it
silently -- no error, no warning, just leaderboards that are quietly wrong. The
local wiki holds 222 games; production holds 8,367, so a limit that is roomy
locally proves nothing.

Two separate ceilings can bite:
  * the limit the module asks for (limit = 20000 in the Lua), and
  * $wgCargoMaxQueryLimit on the wiki, which silently caps what it will return.

Run against production. Read-only.
"""
import sys

import requests


MODULE_LIMIT = 20000

# The aggregates the modules actually run, in their unfiltered (worst) form.
AGGREGATES = {
    "שיאנים/נתונים — events per player": dict(
        tables="Football_Games,Games_Events,Competitions",
        join_on="Football_Games._pageID=Games_Events._pageID,"
                "Football_Games.Competition=Competitions.OriginalName",
        where="Games_Events.Team=1 AND Competitions.Official=1 "
              "AND Games_Events.PlayerName IS NOT NULL "
              "AND Games_Events.PlayerName != ''",
        group_by="Games_Events.PlayerName,Games_Events.EventType,"
                 "Games_Events.SubType,Competitions.League,"
                 "Competitions.Trophy,Competitions.International",
    ),
    "סטטיסטיקה משחקים — games by result": dict(
        tables="Football_Games,Competitions",
        join_on="Football_Games.Competition=Competitions.OriginalName",
        group_by="Competitions.League,Competitions.Trophy,"
                 "Competitions.International,Competitions.Official,"
                 "Football_Games.ResultOpt,Football_Games.ResultMaccabi,"
                 "Football_Games.ResultOpponent",
    ),
    "סטטיסטיקה משחקים — cards": dict(
        tables="Football_Games,Games_Events,Competitions",
        join_on="Football_Games._pageID=Games_Events._pageID,"
                "Football_Games.Competition=Competitions.OriginalName",
        where="Games_Events.Team=1 AND Games_Events.SubType IN (71,72,73)",
        group_by="Competitions.League,Competitions.Trophy,"
                 "Competitions.International,Competitions.Official,"
                 "Games_Events.SubType",
    ),
}


def export(base: str, spec: dict, limit: int) -> int:
    """Rows Special:CargoExport returns for this aggregate at the given limit.

    CargoExport hands back the whole set in one response, so this is one request
    per aggregate rather than paging the API 40 times against production.
    """
    response = requests.get(
        f"{base}/index.php", timeout=1800,
        headers={"User-Agent": "MaccabipediaPerfBenchmark/1.0"},
        params={
            "title": "Special:CargoExport", "format": "json",
            "tables": spec["tables"], "join on": spec["join_on"],
            "where": spec.get("where", "1=1"),
            "fields": spec["group_by"].split(",")[0] + "=first",
            "group by": spec["group_by"], "limit": limit,
        })
    response.raise_for_status()
    if "application/json" not in response.headers.get("Content-Type", ""):
        raise SystemExit(f"CargoExport returned {response.headers.get('Content-Type')}:"
                         f"\n{response.text[:300]}")
    return len(response.json())


def group_count(base: str, spec: dict) -> int:
    """The true number of groups -- asked for well above the module's limit."""
    return export(base, spec, MODULE_LIMIT * 5)


def rows_returned(base: str, spec: dict) -> int:
    """What the wiki hands back at exactly the limit the module asks for."""
    return export(base, spec, MODULE_LIMIT)


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "https://www.maccabipedia.co.il"
    print(f"{base}\nmodule asks for limit={MODULE_LIMIT:,}\n")
    print(f"{'aggregate':40s} {'rows needed':>12s} {'returned':>10s}  verdict")
    print("-" * 88)

    worst = 0
    for label, spec in AGGREGATES.items():
        needed = group_count(base, spec)
        returned = rows_returned(base, spec)
        worst = max(worst, needed)
        if needed > MODULE_LIMIT:
            verdict = "TRUNCATED — module limit too low"
        elif returned < needed:
            verdict = f"CAPPED by the wiki at {returned:,}"
        else:
            verdict = f"fits, {MODULE_LIMIT - needed:,} rows of headroom"
        print(f"{label:40s} {needed:>12,} {returned:>10,}  {verdict}")

    print(f"\nlargest aggregate: {worst:,} rows "
          f"({worst / MODULE_LIMIT:.0%} of the module limit)")


if __name__ == "__main__":
    main()
