"""Generate a content manifest covering one season of one sport.

Derives every page title the season needs (games, Maccabi players, coaches,
opponents, stadiums, competitions, season page, uniforms, premiere songs for
football) from prod's Special:CargoExport, and writes one title per line to
content-manifests/season-<sport>-<YYYY-YY>.manifest.

Usage:
    uv run python infra/local-wiki/scripts/generate_season_manifest.py football 2024/25
    uv run python infra/local-wiki/scripts/generate_season_manifest.py basketball 2023/24
    uv run python infra/local-wiki/scripts/generate_season_manifest.py volleyball 2024/25

Then import (full sequence: README → "Seeding a full season"):
    uv run python scripts/download_pages_from_prod.py pages scripts/content-manifests/season-football-2024-25.manifest
    bash scripts/seed-content.sh season-football-2024-25

SPORTS below is the only per-sport registry in the pipeline — a new sport is
one entry here (plus the README sports line).
"""
import argparse
import html
import sys
from dataclasses import dataclass
from pathlib import Path

import requests

CARGO_EXPORT = "https://www.maccabipedia.co.il/index.php"
# maccabistats placeholder values that must not become page titles.
SENTINELS = {"Cant found coach", "Cant found referee", "Cant found stadium", ""}
LIMIT = 2000


@dataclass(frozen=True)
class SportConfig:
    games_table: str
    events_table: str       # per-player rows; Team=1 is Maccabi in all three sports
    prefix: str             # namespace prefix for players/coaches/opponents/competitions/season
    stadium_prefix: str     # stadiums: football+volleyball main-ns, basketball prefixed
    uniforms_table: str
    include_songs: bool     # Songs table is club-wide; pulled once, with football


SPORTS = {
    "football": SportConfig(
        games_table="Football_Games",
        events_table="Games_Events",
        prefix="",
        stadium_prefix="",
        uniforms_table="Football_Uniforms",
        include_songs=True,
    ),
    "basketball": SportConfig(
        games_table="Basketball_Games",
        events_table="Basketball_Player_Game_Events_Summary",
        prefix="כדורסל:",
        stadium_prefix="כדורסל:",
        uniforms_table="Basketball_Uniforms",
        include_songs=False,
    ),
    "volleyball": SportConfig(
        games_table="Volleyball_Games",
        events_table="Volleyball_Players_Game_Events",
        prefix="כדורעף:",
        stadium_prefix="",  # volleyball stadium pages live in main ns (mostly absent; export skips)
        uniforms_table="Volleyball_Uniforms",
        include_songs=False,
    ),
}


def cargo_fetch(tables, fields, where, **extra):
    """One Special:CargoExport call, validated per the repo's Cargo lesson."""
    params = {
        "title": "Special:CargoExport",
        "format": "json",
        "limit": LIMIT,
        "tables": tables,
        "fields": fields,
        "where": where,
        **extra,
    }
    response = requests.get(CARGO_EXPORT, params=params, timeout=60)
    response.raise_for_status()
    if "application/json" not in response.headers.get("Content-Type", ""):
        raise ValueError(f"Cargo returned non-JSON for {tables}: {response.text[:300]}")
    return response.json()


def _clean(values, prefix=""):
    # Cargo stores some titles HTML-entity-encoded (e.g. בית&quot;ר — the
    # known wiki-wide &quot; quirk); unescape so manifests hold canonical
    # page titles.
    return [
        prefix + html.unescape(value)
        for value in values
        if value and value not in SENTINELS
    ]


def collect_season_titles(sport, season, fetch=cargo_fetch):
    """Return a deduped, ordered list of page titles covering one sport's season."""
    config = SPORTS[sport]
    games = fetch(
        config.games_table,
        "_pageName,Opponent,Stadium,CoachMaccabi,Competition",
        f'Season="{season}"',
    )
    players = fetch(
        f"{config.events_table},{config.games_table}",
        f"{config.events_table}.PlayerName=PlayerName",
        f'{config.games_table}.Season="{season}" AND {config.events_table}.Team=1',
        **{"join on": f"{config.events_table}._pageName={config.games_table}._pageName",
           "group by": f"{config.events_table}.PlayerName"},
    )
    uniforms = fetch(config.uniforms_table, "_pageName", f'Season="{season}"')

    titles = []
    titles += _clean(row["_pageName"] for row in games)  # game pages carry their own prefix
    titles += _clean((row["PlayerName"] for row in players), config.prefix)
    titles += _clean((row["CoachMaccabi"] for row in games), config.prefix)
    titles += _clean((row["Opponent"] for row in games), config.prefix)
    titles += _clean((row["Stadium"] for row in games), config.stadium_prefix)
    titles += _clean((row["Competition"] for row in games), config.prefix)
    titles.append(f"{config.prefix}עונת {season}")
    titles += _clean(row["_pageName"] for row in uniforms)
    if config.include_songs:
        songs = fetch("Songs", "_pageName", f'PremiereSeason="{season}"')
        titles += _clean(row["_pageName"] for row in songs)

    return list(dict.fromkeys(titles))  # dedupe, keep order


def main():
    parser = argparse.ArgumentParser(description="Generate a season manifest for the local wiki")
    parser.add_argument("sport", choices=sorted(SPORTS))
    parser.add_argument("season", help='season as on the wiki, e.g. "2024/25"')
    args = parser.parse_args()

    titles = collect_season_titles(args.sport, args.season)
    stem = f"season-{args.sport}-" + args.season.replace("/", "-")
    out_path = Path(__file__).parent / "content-manifests" / f"{stem}.manifest"
    header = (
        f"# Auto-generated by generate_season_manifest.py for {args.sport} season {args.season}.\n"
        f"# Regenerate rather than hand-edit.\n"
    )
    out_path.write_text(header + "\n".join(titles) + "\n", encoding="utf-8")
    print(f"wrote {len(titles)} titles -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
