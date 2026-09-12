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

from wiki_api import DEFAULT_BASE_URL, WikiApi


@dataclass(frozen=True)
class BenchmarkPage:
    label: str
    title: str
    note: str


def _players_by_event_count(api: WikiApi, direction: str) -> list[tuple[str, int]]:
    """Players ordered by event count. `direction` is 'DESC' (heaviest) or 'ASC' (lightest)."""
    rows = api.cargo_query(
        tables="Games_Events",
        fields="PlayerName=name,COUNT(*)=events",
        where="PlayerName IS NOT NULL AND PlayerName != ''",
        group_by="PlayerName",
        order_by=f"COUNT(*) {direction}",
        limit=300,
    )
    counted = [(row["name"], int(row["events"])) for row in rows if row.get("name")]
    return [(name, events) for name, events in counted if events > 0]


def _seasons_by_game_count(api: WikiApi) -> list[tuple[str, int]]:
    """Seasons with their game counts.

    The richest season is the one with the most games, NOT the most recent:
    a season that has only just started has almost no data and would make a
    misleading 'heaviest page' benchmark.
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
    payload = api.get(action="query", list="allpages",
                      apprefix="פורטל", aplimit=50, apnamespace=0)
    found: list[tuple[str, str]] = []
    for index, page in enumerate(payload.get("query", {}).get("allpages", [])):
        title = page["title"]
        found.append((PORTAL_SLUGS.get(title, f"portal_{index}"), title))
    return found


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

    heaviest = _players_by_event_count(api, "DESC")
    lightest = _players_by_event_count(api, "ASC")
    heavy_existing = api.existing_titles([name for name, _ in heaviest])
    light_existing = api.existing_titles([name for name, _ in lightest])
    heavy = [(name, events) for name, events in heaviest if name in heavy_existing]
    light = [(name, events) for name, events in lightest if name in light_existing]
    if heavy and light:
        for label, (name, events), note in (
            ("player_max", heavy[0], "most events — worst case"),
            ("player_median", heavy[len(heavy) // 2], "mid-range events"),
            ("player_min", light[0], "fewest events — best case"),
        ):
            pages.append(BenchmarkPage(label, name, f"{note} ({events} events)"))

    seasons = _seasons_by_game_count(api)
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
    parser.add_argument("--out", type=Path, default=Path(".claude/tmp/perf/page_set.json"))
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
