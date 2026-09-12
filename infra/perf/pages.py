"""Resolve the benchmark page set from live Cargo data.

The set is derived rather than hardcoded so it tracks the real data
distribution: if parse cost scales with row count, the max/median/min players
show it. A hardcoded list would silently stop being representative.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from wiki_api import DEFAULT_BASE_URL, DEFAULT_OUT_DIR, WikiApi


@dataclass(frozen=True)
class BenchmarkPage:
    label: str
    title: str
    note: str


PLAYER_EVENTS_WHERE = "PlayerName IS NOT NULL AND PlayerName != ''"


def _players_by_event_count(api: WikiApi, direction: str,
                            offset: int = 0, limit: int = 300) -> list[tuple[str, int]]:
    """Players ordered by event count.

    `direction` is 'DESC' (heaviest first) or 'ASC' (lightest first). `offset`
    reaches into the middle of the distribution, which is how the true median is
    found -- taking the midpoint of a top-N slice would return the median of the
    heaviest N, which sits near the top of the wiki-wide distribution.
    """
    rows = api.cargo_query(
        tables="Games_Events",
        fields="PlayerName=name,COUNT(*)=events",
        where=PLAYER_EVENTS_WHERE,
        group_by="PlayerName",
        order_by=f"COUNT(*) {direction}",
        offset=offset,
        limit=limit,
    )
    counted = [(row["name"], int(row["events"])) for row in rows if row.get("name")]
    return [(name, events) for name, events in counted if events > 0]


def _distinct_player_count(api: WikiApi) -> int:
    rows = api.cargo_query(
        tables="Games_Events",
        fields="COUNT(DISTINCT PlayerName)=n",
        where=PLAYER_EVENTS_WHERE,
    )
    return int(rows[0]["n"]) if rows else 0


def _seasons_in_chronological_order(api: WikiApi) -> list[tuple[str, int]]:
    """Every season with its game count, oldest first.

    Ordering is by `Season ASC`, which is chronological because the season
    strings are `YYYY` / `YYYY/YY` and sort lexicographically in date order.
    The caller relies on that positional ordering, so do not reorder this query
    without changing the caller too.
    """
    rows = api.cargo_query(
        tables="Football_Games",
        fields="Season=season,COUNT(*)=games",
        where="Season IS NOT NULL AND Season != ''",
        group_by="Season",
        order_by="Season ASC",
        limit=500,
    )
    return [(row["season"], int(row["games"])) for row in rows if row.get("season")]


# Portal pages are hand-built navigation hubs, so they are not derivable from
# Cargo like the content pages are. They are discovered by title prefix instead.
PORTAL_SLUGS = {
    "פורטל שחקנים": "portal_players",
    "פורטל אנשי צוות": "portal_staff",
    "פורטל מדים": "portal_uniforms",
    "פורטל מפעלים": "portal_competitions",
    "פורטל מתקנים": "portal_venues",
    "פורטל צעיפים": "portal_scarves",
}


def _portals(api: WikiApi) -> list[tuple[str, str]]:
    """Every portal page, paged fully.

    The fallback label is keyed on the title, never on listing position: a new
    page whose title starts with 'פורטל' (a subpage counts) would shift every
    positional label, so a label-keyed before/after diff would silently compare
    two different pages.
    """
    found: list[tuple[str, str]] = []
    cont: dict[str, str] = {}
    while True:
        payload = api.get(action="query", list="allpages", apprefix="פורטל",
                          aplimit=500, apnamespace=0, **cont)
        for page in payload.get("query", {}).get("allpages", []):
            title = page["title"]
            found.append((PORTAL_SLUGS.get(title, f"portal:{title}"), title))
        if "continue" not in payload:
            return found
        cont = payload["continue"]


def _latest_game_page(api: WikiApi) -> str | None:
    rows = api.cargo_query(
        tables="Football_Games",
        fields="_pageName=page,Date=date",
        order_by="Date DESC",
        limit=5,
    )
    return rows[0]["page"] if rows else None


def resolve(api: WikiApi) -> list[BenchmarkPage]:
    pages: list[BenchmarkPage] = [
        BenchmarkPage("home", "עמוד ראשי", "site entry point")
    ]

    # Each selection is guarded on its own: the lightest players are mostly
    # one-appearance names that often have no page, and an empty result there
    # must not also drop the heaviest and median entries.
    def first_existing(candidates: list[tuple[str, int]]) -> tuple[str, int] | None:
        existing = api.existing_titles([name for name, _ in candidates])
        for name, events in candidates:
            if name in existing:
                return name, events
        return None

    def median_player() -> tuple[str, int] | None:
        """The median player *that has a page*.

        Games_Events holds opponent players too, and the wiki-wide median name
        has only one or two events and almost never has an article. So start at
        the true median offset and walk toward the heavier end until a page
        exists -- the first one found is the median of the population that
        actually gets benchmarked.
        """
        total = _distinct_player_count(api)
        window = 300
        offset = max(total // 2 - 1, 0)
        while offset >= 0:
            candidates = _players_by_event_count(api, "DESC", offset=offset, limit=window)
            if not candidates:
                break
            picked = first_existing(candidates)
            if picked is not None:
                return picked
            offset -= window
        return None

    # Three points spanning the real cost curve. The wiki-wide median player has
    # ~2 events, so a median/min pair would be two near-identical light pages and
    # would not show whether cost scales; `player_high` supplies the middle of
    # the curve, and each label says what it actually is.
    selections = (
        ("player_max", lambda: first_existing(
            _players_by_event_count(api, "DESC", limit=50)),
         "most events — worst case"),
        ("player_high", lambda: first_existing(
            _players_by_event_count(api, "DESC", offset=150, limit=150)),
         "high event count, short of the extreme"),
        ("player_median", median_player,
         "median among players with pages — the typical profile"),
    )
    for label, pick, note in selections:
        picked = pick()
        if picked is None:
            print(f"  (no existing page found for {label} — skipped)")
            continue
        name, events = picked
        pages.append(BenchmarkPage(label, name, f"{note} ({events} events)"))

    seasons = _seasons_in_chronological_order(api)
    existing_seasons = api.existing_titles([f"עונת {season}" for season, _ in seasons])
    available = [(season, games) for season, games in seasons
                 if f"עונת {season}" in existing_seasons]
    # A season that has only just started has almost no games yet, so exclude
    # thin seasons before taking "most recent" — otherwise the benchmark's
    # heavy season page is whichever one happens to be a fortnight old.
    FULL_SEASON_MIN_GAMES = 20
    complete = [(season, games) for season, games in available
                if games >= FULL_SEASON_MIN_GAMES]
    if available:
        earliest, earliest_games = available[0]
        pages.append(BenchmarkPage("season_old", f"עונת {earliest}",
                                   f"earliest season — thin data ({earliest_games} games)"))
    if complete:
        recent, recent_games = complete[-1]
        pages.append(BenchmarkPage("season_recent", f"עונת {recent}",
                                   f"latest complete season ({recent_games} games)"))

    game_page = _latest_game_page(api)
    if game_page:
        pages.append(BenchmarkPage("game", game_page, "most numerous page type"))

    for label, title in _portals(api):
        pages.append(BenchmarkPage(label, title, "navigation hub"))

    return pages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR / "page_set.json")
    args = parser.parse_args()

    api = WikiApi(args.base_url)
    pages = resolve(api)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps([asdict(page) for page in pages], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for page in pages:
        print(f"  {page.label:16s} {page.title:35s} {page.note}")
    print(f"\n{len(pages)} pages -> {args.out}")


if __name__ == "__main__":
    main()
