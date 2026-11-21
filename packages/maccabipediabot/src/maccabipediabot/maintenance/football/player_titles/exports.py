"""Cargo exports for the title rule, each checked before anything is built on it.

A paged export can come back short (a page boundary that moved, a silent limit) and still
look healthy, and a short export would write a smaller page. So every export is compared
with its own COUNT and checked for a repeated key.
"""
from __future__ import annotations

import html

from maccabipediabot.maintenance.football.player_titles.api import Api
from maccabipediabot.maintenance.football.player_titles.rule import SeasonPlayed, Title

PAGE_SIZE = 500

# The filter the profile template uses for "Maccabi won this".
WON_FILTER = 'Achievement IN ("זכיה", "מקום 1")'

# Games_Events.Team is an Integer flag: 1 = Maccabi, 0 = the opponent.
MACCABI_TEAM_ID = 1

LEAGUE_KIND = "ליגה"
CUP_KIND = "גביע"
NAMED_KINDS = ("גביע הטוטו", "אלוף האלופים", "גביע ליליאן", "גביע אסיה לאלופות")


class ExportError(RuntimeError):
    """An export that cannot be trusted: short, repeated, or not what was asked for."""


def cargo_rows(api: Api, *, key: tuple[str, ...], count_field: str, **query: str) -> list[dict[str, str]]:
    """Every row of a Cargo query, paged in the caller's `order_by`.

    Values are HTML-decoded: `action=cargoquery` returns a `"` as `&quot;` while the
    database, and so the wiki, holds the raw character.
    """
    rows: list[dict[str, str]] = []
    offset = 0
    while True:
        response = api(action="cargoquery", limit=PAGE_SIZE, offset=offset, **query)
        page = [
            {field: html.unescape(value or "") for field, value in row["title"].items()}
            for row in response["cargoquery"]
        ]
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    count_query = {name: value for name, value in query.items() if name not in ("fields", "group_by", "order_by")}
    count_response = api(action="cargoquery", fields=count_field, limit=1, **count_query)
    expected = int(count_response["cargoquery"][0]["title"]["n"])
    if len(rows) != expected:
        raise ExportError(f"{query['tables']}: the export has {len(rows)} rows, the wiki counts {expected}")

    seen: set[tuple[str, ...]] = set()
    for row in rows:
        row_key = tuple(row[field] for field in key)
        if row_key in seen:
            raise ExportError(f"{query['tables']}: the key {row_key} appears more than once")
        seen.add(row_key)
    return rows


def won_titles(api: Api) -> list[Title]:
    """Every competition Maccabi won, one per season and competition."""
    rows = cargo_rows(
        api, key=("Season", "Competition"), count_field="COUNT(*)=n",
        tables="Achievements", fields="Season, Competition", where=WON_FILTER,
        order_by="Season, Competition",
    )
    return [Title(row["Season"], row["Competition"]) for row in rows]


def seasons_played(api: Api) -> list[SeasonPlayed]:
    """Every (player, season) with a Maccabi game-sheet row.

    The same query as תבנית:סטטיסטיקה/שליפות/מתקדמות/עונות שבהן שיחק שחקן, for all players
    at once - including its join to Competitions, which drops a game whose competition has
    no row there.
    """
    rows = cargo_rows(
        api, key=("Player", "Season"),
        count_field='COUNT(DISTINCT CONCAT(e.PlayerName, "@@", g.Season))=n',
        tables="Football_Games=g, Games_Events=e, Competitions=c",
        join_on="g._pageID=e._pageID, g.Competition=c.OriginalName",
        fields="e.PlayerName=Player, g.Season=Season",
        where=f"e.Team={MACCABI_TEAM_ID}",
        group_by="e.PlayerName, g.Season",
        order_by="e.PlayerName, g.Season",
    )
    return [SeasonPlayed(row["Player"], row["Season"]) for row in rows]


def competition_kinds(api: Api) -> dict[str, set[str]]:
    """For each of the profile's six title lists, the competitions it counts.

    Mirrors the filters of תבנית:פרופיל כדורגל/הרכבת רשימת זכיות/שחקן: the league and cup
    lists go by the competition's flags, the four named lists by its original or current
    name. A competition can belong to more than one list.
    """
    rows = cargo_rows(
        api, key=("OriginalName",), count_field="COUNT(*)=n",
        tables="Competitions", fields="OriginalName, CurrentName, League, Trophy",
        order_by="OriginalName",
    )
    kinds: dict[str, set[str]] = {kind: set() for kind in (LEAGUE_KIND, CUP_KIND, *NAMED_KINDS)}
    for row in rows:
        if row["League"] == "1":
            kinds[LEAGUE_KIND].add(row["OriginalName"])
        if row["Trophy"] == "1":
            kinds[CUP_KIND].add(row["OriginalName"])
        for name in NAMED_KINDS:
            if name in (row["OriginalName"], row["CurrentName"]):
                kinds[name].add(row["OriginalName"])
    return kinds
