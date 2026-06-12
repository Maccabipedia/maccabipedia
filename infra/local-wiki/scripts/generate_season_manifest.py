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
API_ENDPOINT = "https://www.maccabipedia.co.il/api.php"
# maccabistats placeholder values that must not become page titles.
SENTINELS = {"Cant found coach", "Cant found referee", "Cant found stadium", ""}
LIMIT = 2000


@dataclass(frozen=True)
class SportConfig:
    games_table: str
    events_table: str       # per-player rows; Team=1 is Maccabi in all three sports
    prefix: str             # namespace prefix for players/coaches/opponents/competitions/season
    stadium_format: str     # stadium page title per sport, '{}' = the Cargo Stadium value
    uniforms_table: str
    include_songs: bool     # Songs table is club-wide; pulled once, with football
    profiles_table: str     # per-sport player profiles; ProfilePicture names the photo file
    referee_format: str = ""   # main-referee page title; '' = referees have no pages
    extra_titles: tuple = ()   # static per-sport pages every season links (e.g. the club page)


SPORTS = {
    "football": SportConfig(
        games_table="Football_Games",
        events_table="Games_Events",
        prefix="",
        stadium_format="{}",
        uniforms_table="Football_Uniforms",
        profiles_table="Profiles",
        include_songs=True,
        referee_format="כדורגל:{} (שופט)",
        # הזנת מפעלי X: single data-entry page holding the WHOLE Competitions
        # catalog — the stats queries inner-join it, so without it every
        # aggregate (player/season stats) returns zero.
        extra_titles=("מכבי תל אביב", "הזנת מפעלי כדורגל"),
    ),
    "basketball": SportConfig(
        games_table="Basketball_Games",
        events_table="Basketball_Player_Game_Events_Summary",
        prefix="כדורסל:",
        stadium_format="כדורסל:{}",
        uniforms_table="Basketball_Uniforms",
        profiles_table="Basketball_Players",
        include_songs=False,
        extra_titles=("הזנת מפעלי כדורסל",),
    ),
    "volleyball": SportConfig(
        games_table="Volleyball_Games",
        events_table="Volleyball_Players_Game_Events",
        prefix="כדורעף:",
        stadium_format="כדורעף:{} (אולם)",
        uniforms_table="Volleyball_Uniforms",
        profiles_table="Volleyball_Players",
        include_songs=False,
        extra_titles=("כדורעף:מכבי תל אביב", "הזנת מפעלי כדורעף"),
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
    game_fields = "_pageName,Opponent,Stadium,CoachMaccabi,Competition"
    if config.referee_format:
        game_fields += ",Refs"  # only Football_Games has a main-referee field
    games = fetch(
        config.games_table,
        game_fields,
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

    # Profile photos: the profile templates pick the photo with #ifexist on
    # the קובץ: page, which must exist LOCALLY (the binary then streams from
    # the foreign repo) — so pull the file-description pages the players use.
    player_titles = _clean((row["PlayerName"] for row in players), config.prefix)
    profile_pictures = []
    if player_titles:
        quoted_names = ",".join(f'"{name}"' for name in player_titles if '"' not in name)
        profiles = fetch(
            config.profiles_table,
            "_pageName,ProfilePicture",
            f"_pageName IN ({quoted_names})",
        )
        profile_pictures = _clean((row.get("ProfilePicture") for row in profiles), "קובץ:")

    titles = []
    titles += _clean(row["_pageName"] for row in games)  # game pages carry their own prefix
    titles += player_titles
    titles += profile_pictures
    titles += _clean((row["CoachMaccabi"] for row in games), config.prefix)
    titles += _clean((row["Opponent"] for row in games), config.prefix)
    titles += [config.stadium_format.format(value)
               for value in _clean(row["Stadium"] for row in games)]
    titles += _clean((row["Competition"] for row in games), config.prefix)
    if config.referee_format:
        titles += [config.referee_format.format(value)
                   for value in _clean(row.get("Refs") for row in games)]
    titles.append(f"{config.prefix}עונת {season}")
    titles += list(config.extra_titles)
    titles += _clean(row["_pageName"] for row in uniforms)
    if config.include_songs:
        songs = fetch("Songs", "_pageName", f'PremiereSeason="{season}"')
        titles += _clean(row["_pageName"] for row in songs)

    return list(dict.fromkeys(titles))  # dedupe, keep order


def api_get(params):
    # POST, not GET: a 50-title batch overflows the request-line limit (414).
    # Prod's edge only rejects POST on the Special:Export form; api.php POSTs
    # are the normal bot path.
    response = requests.post(API_ENDPOINT, data={"format": "json", **params}, timeout=60)
    response.raise_for_status()
    return response.json()


def expand_with_redirects(titles, api=api_get):
    """Append redirect pages so the seeded wiki keeps short-form links blue.

    Two directions, both needed:
    - a collected title may itself BE a redirect (Cargo stores quote-stripped
      opponent names like ביתר ירושלים) — without its TARGET only the
      redirect imports and following it 404s;
    - redirects pointing AT a collected title (מכבי ת"א → מכבי תל אביב)
      make the free-text short-form links all over game summaries resolve.

    Follows API continuation — rdlimit=max caps a request at 500 redirect
    sources across the whole batch, which a batch of club/player pages can
    plausibly exceed.
    """
    expanded = list(titles)
    for start in range(0, len(titles), 50):
        batch = titles[start:start + 50]
        params = {
            "action": "query",
            "redirects": 1,
            "prop": "redirects",
            "rdlimit": "max",
            "titles": "|".join(batch),
        }
        while True:
            data = api(params)
            query = data.get("query", {})
            expanded += [redirect["to"] for redirect in query.get("redirects", [])]
            for page in query.get("pages", {}).values():
                expanded += [redirect["title"] for redirect in page.get("redirects", [])]
            if "continue" not in data:
                break
            params = {**params, **data["continue"]}
    return list(dict.fromkeys(expanded))


def main():
    parser = argparse.ArgumentParser(description="Generate a season manifest for the local wiki")
    parser.add_argument("sport", choices=sorted(SPORTS))
    parser.add_argument("season", help='season as on the wiki, e.g. "2024/25"')
    args = parser.parse_args()

    titles = expand_with_redirects(collect_season_titles(args.sport, args.season))
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
