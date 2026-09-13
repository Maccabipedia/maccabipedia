"""Pick a deliberately awkward sample of production pages to verify against.

Two friendly pages proving nothing is the usual way this goes wrong. The sample
is chosen for the cases most likely to break: the biggest result sets, the
oldest data, names carrying quotes, and opponents that appear under several
names.

Usage:  sample_pages.py opponents|seasons [count]
"""
import sys

sys.path.insert(0, "infra/perf")
from wiki_api import WikiApi  # noqa: E402

PROD = "https://www.maccabipedia.co.il"


def opponents(api: WikiApi, count: int) -> list[str]:
    def query(**extra):
        return api.get(action="cargoquery", tables="Football_Games",
                       fields="Football_Games.Opponent=name,COUNT(*)=n",
                       group_by="Football_Games.Opponent", formatversion=2,
                       **extra)["cargoquery"]

    most = query(order_by="COUNT(*) DESC", limit=count)
    fewest = query(order_by="COUNT(*) ASC", limit=count)
    # Oldest: whoever Maccabi played in its earliest recorded games.
    oldest = api.get(action="cargoquery", tables="Football_Games",
                     fields="Football_Games.Opponent=name,Football_Games.Date=d",
                     order_by="Football_Games.Date ASC", limit=count,
                     formatversion=2)["cargoquery"]

    names = [row["title"]["name"] for row in most]
    names += [row["title"]["name"] for row in fewest]
    names += [row["title"]["name"] for row in oldest]
    # Cargo holds the stripped spelling; the page title may carry the quote.
    resolved, seen = [], set()
    for name in names:
        if name in seen or not name:
            continue
        seen.add(name)
        payload = api.get(action="query", titles=name, redirects=1,
                          formatversion=2)["query"]
        page = payload["pages"][0]
        if not page.get("missing"):
            resolved.append(page["title"])
    return resolved


def seasons(api: WikiApi, count: int) -> list[str]:
    rows = api.get(action="cargoquery", tables="Football_Games",
                   fields="Football_Games.Season=s,COUNT(*)=n",
                   group_by="Football_Games.Season",
                   order_by="Football_Games.Season ASC",
                   limit=500, formatversion=2)["cargoquery"]
    all_seasons = [row["title"]["s"] for row in rows if row["title"]["s"]]
    # Oldest, newest, and the busiest in between.
    busiest = sorted(rows, key=lambda r: -int(r["title"]["n"]))[:count]
    picked = all_seasons[:count] + all_seasons[-count:]
    picked += [row["title"]["s"] for row in busiest]
    out, seen = [], set()
    for season in picked:
        title = f"עונת {season}"
        if title in seen:
            continue
        seen.add(title)
        out.append(title)
    return out


def main() -> None:
    kind = sys.argv[1] if len(sys.argv) > 1 else "opponents"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    api = WikiApi(PROD, pace_seconds=0.3)
    picker = {"opponents": opponents, "seasons": seasons}[kind]
    for title in picker(api, count):
        print(title)


if __name__ == "__main__":
    main()
