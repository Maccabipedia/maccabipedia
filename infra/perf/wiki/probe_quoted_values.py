"""Are quote characters stored in Cargo, or stripped on the way in?

Decides whether the module must strip them from the names it is handed. The
answer can differ per column, so check each one the module filters on.
"""
import sys

sys.path.insert(0, "infra/perf")
from wiki_api import WikiApi  # noqa: E402

COLUMNS = [
    ("Football_Games", "Opponent"),
    ("Football_Games", "Stadium"),
    ("Football_Games", "Refs"),
    ("Football_Games", "Competition"),
    ("Games_Events", "PlayerName"),
]


def main() -> None:
    api = WikiApi("http://localhost:8080", pace_seconds=0.1)
    for table, column in COLUMNS:
        field = f"{table}.{column}"
        rows = api.get(action="cargoquery", tables=table,
                       fields=f"{field}=value",
                       where=f"{field} LIKE '%''%' OR {field} LIKE '%\"%'",
                       group_by=field, limit=10, formatversion=2)
        values = [row["title"]["value"] for row in rows["cargoquery"]]
        print(f"  {field:32s} {len(values)} values hold a quote: {values[:4]}")


if __name__ == "__main__":
    main()
