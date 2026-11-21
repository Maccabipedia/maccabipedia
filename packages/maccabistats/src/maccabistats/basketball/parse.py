"""Load every basketball game from MaccabiPedia's Cargo tables."""
import logging
from datetime import date
from collections import defaultdict
from typing import Dict, List, Tuple

from maccabistats.basketball.models import (
    MACCABI_NAME,
    BasketballCompetitionFlags,
    BasketballGameData,
    BasketballGameVideos,
    BasketballPlayerInGame,
    BasketballTeamInGame,
)
from maccabistats.basketball.stats import BasketballGamesStats
from maccabistats.parse.maccabipedia.maccabipedia_cargo_chunks_crawler import MaccabiPediaCargoChunksCrawler

logger = logging.getLogger(__name__)

_GAMES_TABLE = "Basketball_Games"
_COMPETITIONS_TABLE = "Basketball_Competitions"
_PERIODS = ("First", "Second", "Third", "Fourth")
_SIDES = ("Maccabi", "Opponent")
# IsOvertime is not read: the wiki's store template never fills it, so it is empty on every row.
_GAMES_FIELDS = ",".join(
    ["_pageName", "Date", "Hour", "Season", "Competition", "Leg", "Opponent", "HomeAway", "Stadium",
     "TotalPointsMaccabi", "TotalPointsOpponent", "ResultOpt", "Technical", "CoachMaccabi", "CoachOpponent",
     "MainReferee", "AssistantReferees", "Crowd", "HasArticle",
     "FullGameVideo", "FullGameVideo2", "HighlightsVideo", "HighlightsVideo2", "FansVideo", "FansVideo2"]
    + [f"{period}QuarterPoints{side}" for period in _PERIODS for side in _SIDES]
    + [f"{period}HalfPoints{side}" for period in _PERIODS[:2] for side in _SIDES]
    + [f"{period}OvertimePoints{side}" for period in _PERIODS for side in _SIDES]
)
_COMPETITIONS_FIELDS = "_pageName,OriginalName,CurrentName,League,International,Trophy,Official"
_PLAYERS_TABLE = "Basketball_Player_Game_Events_Summary"
# The model's field for each Cargo column. FieldGoals are the two-point shots.
_PLAYER_STATS_COLUMNS = {
    "minutes": "MinutesPlayed", "points": "TotalPoints",
    "two_points_scored": "FieldGoalsScored", "two_points_attempts": "FieldGoalsAttempts",
    "three_points_scored": "ThreePointsScored", "three_points_attempts": "ThreePointsAttempts",
    "free_throws_scored": "FreeThrowsScored", "free_throws_attempts": "FreeThrowsAttempts",
    "rebounds": "TotalRebounds", "offensive_rebounds": "OffensiveRebounds", "defensive_rebounds": "DefensiveRebounds",
    "assists": "Assists", "steals": "Steals", "blocks": "Blocks", "turnovers": "Turnovers",
    "personal_fouls": "TotalPersonalFouls", "technical_fouls": "TechnicalPersonalFouls",
}
_PLAYERS_FIELDS = ",".join(["_ID", "_pageName", "PlayerName", "PlayerNumber", "IsCaptain", "IsStartingFive",
                            "IsPlayed", "Team"] + list(_PLAYER_STATS_COLUMNS.values()))
# The Team column of a player row
_MACCABI_TEAM = 1
_OPPONENT_TEAM = 0
# Smaller than Cargo's 5000 on purpose: the rows are wide and the shared host answers 508 under load.
_ROWS_PER_REQUEST = 2500
_REQUEST_TIMEOUT_SECONDS = 120


def _text(raw: Dict, field: str) -> str | None:
    # Cargo types a column by its values, so a season like 1957 arrives as a number.
    value = raw.get(field)
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip()


def _date(raw: Dict) -> date | None:
    raw_date = _text(raw, "Date")
    if raw_date is None:
        return None
    try:
        return date.fromisoformat(raw_date[:10])
    except ValueError:
        # One unreadable date should not fail the load of every game; the game is kept with no date
        logger.warning(f"Unreadable date {raw_date!r} on {raw.get('_pageName')}")
        return None


def _flag(raw: Dict, field: str) -> bool:
    return raw.get(field) in (1, "1", True)


def player_from_cargo(raw: Dict) -> BasketballPlayerInGame:
    """:param raw: One Basketball_Player_Game_Events_Summary row as the crawler yields it"""
    return BasketballPlayerInGame(
        name=_text(raw, "PlayerName"),
        number=raw.get("PlayerNumber"),
        is_captain=_flag(raw, "IsCaptain"),
        is_starting_five=_flag(raw, "IsStartingFive"),
        is_played=_flag(raw, "IsPlayed"),
        **{stat: raw.get(column) for stat, column in _PLAYER_STATS_COLUMNS.items()},
    )


def _team_from_cargo(raw: Dict, side: str, name: str | None,
                     players: Tuple[BasketballPlayerInGame, ...]) -> BasketballTeamInGame:
    return BasketballTeamInGame(
        name=name,
        coach=_text(raw, f"Coach{side}"),
        score=raw.get(f"TotalPoints{side}"),
        quarters=tuple(raw.get(f"{period}QuarterPoints{side}") for period in _PERIODS),
        halves=tuple(raw.get(f"{period}HalfPoints{side}") for period in _PERIODS[:2]),
        overtimes=tuple(raw.get(f"{period}OvertimePoints{side}") for period in _PERIODS),
        players=players,
    )


def competition_flags_from_cargo(raw: Dict) -> BasketballCompetitionFlags:
    return BasketballCompetitionFlags(
        current_name=_text(raw, "CurrentName"),
        is_league=_flag(raw, "League"),
        is_trophy=_flag(raw, "Trophy"),
        is_international=_flag(raw, "International"),
        is_official=_flag(raw, "Official"),
    )


PlayersBySide = Dict[Tuple[str, int], List[BasketballPlayerInGame]]


def game_from_cargo(raw: Dict, competitions: Dict[str, BasketballCompetitionFlags],
                    players_by_side: PlayersBySide | None = None) -> BasketballGameData:
    """
    :param raw: One Basketball_Games row as the crawler yields it (no key for an empty value)
    :param competitions: The catalog, by the competition's name as game pages write it
    :param players_by_side: The box scores, by (the game's page name, the Team column)
    """
    players_by_side = players_by_side or {}
    competition = _text(raw, "Competition")
    opponent = _text(raw, "Opponent")
    return BasketballGameData(
        page_name=raw["_pageName"],
        date=_date(raw),
        hour=_text(raw, "Hour"),
        season=_text(raw, "Season"),
        competition=competition,
        leg=_text(raw, "Leg"),
        opponent=opponent,
        home_away=_text(raw, "HomeAway"),
        stadium=_text(raw, "Stadium"),
        competition_flags=competitions.get(competition),
        technical=raw.get("Technical"),
        result_opt=raw.get("ResultOpt"),
        main_referee=_text(raw, "MainReferee"),
        # A list column: an empty one arrives as [""]
        assistant_referees=tuple(str(name).strip() for name in raw.get("AssistantReferees", []) if str(name).strip()),
        crowd=raw.get("Crowd"),
        has_article=_flag(raw, "HasArticle"),
        videos=BasketballGameVideos(
            full_game=_text(raw, "FullGameVideo"), full_game_2=_text(raw, "FullGameVideo2"),
            highlights=_text(raw, "HighlightsVideo"), highlights_2=_text(raw, "HighlightsVideo2"),
            fans=_text(raw, "FansVideo"), fans_2=_text(raw, "FansVideo2")),
        maccabi=_team_from_cargo(raw, "Maccabi", MACCABI_NAME,
                                 tuple(players_by_side.get((raw["_pageName"], _MACCABI_TEAM), ()))),
        opponent_team=_team_from_cargo(raw, "Opponent", opponent,
                                       tuple(players_by_side.get((raw["_pageName"], _OPPONENT_TEAM), ()))),
    )


def _crawl(table: str, fields: str, order_by: str) -> List[Dict]:
    return list(MaccabiPediaCargoChunksCrawler(
        tables_name=table, tables_fields=fields, limit=_ROWS_PER_REQUEST, order_by=order_by,
        unescape_all_strings=True, timeout=_REQUEST_TIMEOUT_SECONDS))


def _count_rows(table: str) -> int:
    count_rows = list(MaccabiPediaCargoChunksCrawler(
        tables_name=table, tables_fields="COUNT(_pageName)=RowsCount", timeout=_REQUEST_TIMEOUT_SECONDS))
    return int(count_rows[0]["RowsCount"])


def _crawl_whole_table(table: str, fields: str, unique_field: str, order_by: str = "_pageName") -> List[Dict]:
    """
    The crawler stops at the first request that returns fewer rows than asked, so a response cut
    short would end the crawl early with no error; and a page saved mid-crawl can move a row across
    a request's edge, so one row is read twice and another is skipped while the total still adds up.
    So the crawl must match the table's row count and repeat no unique_field; it is tried twice.
    """
    for attempt in ("first", "second"):
        rows = _crawl(table, fields, order_by)
        if not rows:
            raise RuntimeError(f"MaccabiPedia returned no rows for {table}")

        rows_on_wiki = _count_rows(table)
        distinct_rows = len({row.get(unique_field) for row in rows})
        if len(rows) == rows_on_wiki and distinct_rows == len(rows):
            return rows
        logger.warning(f"{table}: the {attempt} crawl returned {len(rows)} rows ({distinct_rows} distinct "
                       f"{unique_field}), the wiki counts {rows_on_wiki}")

    raise RuntimeError(f"{table}: crawled {len(rows)} rows ({distinct_rows} distinct {unique_field}) twice, "
                       f"but the wiki counts {rows_on_wiki}")


def _crawl_competitions() -> Dict[str, BasketballCompetitionFlags]:
    competitions = {}
    for raw in _crawl_whole_table(_COMPETITIONS_TABLE, _COMPETITIONS_FIELDS, unique_field="OriginalName"):
        name = _text(raw, "OriginalName")
        if name is None:
            logger.warning(f"A {_COMPETITIONS_TABLE} row has no OriginalName, skipping it: {raw}")
            continue
        competitions[name] = competition_flags_from_cargo(raw)
    return competitions


def _crawl_players() -> PlayersBySide:
    """
    The table is some 60,000 rows over many requests, and no column of its own is unique (a page can
    list one player twice), so it is ordered by Cargo's row id. The id only orders this one crawl:
    Cargo gives a page's rows new ids whenever the page is saved, so nothing keeps it.
    """
    rows = _crawl_whole_table(_PLAYERS_TABLE, _PLAYERS_FIELDS, unique_field="_ID", order_by="_ID")
    players_by_side = defaultdict(list)
    # Within a page the ids follow the page's own order of players
    for raw in sorted(rows, key=lambda row: row["_ID"]):
        players_by_side[(raw["_pageName"], raw.get("Team"))].append(player_from_cargo(raw))
    return players_by_side


def load_basketball_from_maccabipedia(with_players: bool = True) -> BasketballGamesStats:
    """
    Crawl every basketball game from MaccabiPedia. Nothing is saved; see serialize_basketball_games.

    :param with_players: Also crawl the players' box scores, which is most of the requests.
                         Without them every team's ``players`` is empty.
    """
    competitions = _crawl_competitions()
    players_by_side = _crawl_players() if with_players else {}
    games_rows = _crawl_whole_table(_GAMES_TABLE, _GAMES_FIELDS, unique_field="_pageName")
    games = [game_from_cargo(raw, competitions, players_by_side) for raw in games_rows]

    # Rows the games did not take: their page has no game row, or their Team is neither side
    taken_sides = {(raw["_pageName"], team) for raw in games_rows for team in (_MACCABI_TEAM, _OPPONENT_TEAM)}
    player_rows_without_game = [(page_name, team, player)
                                for (page_name, team), players in players_by_side.items()
                                if (page_name, team) not in taken_sides for player in players]

    logger.info(f"Loaded {len(games)} basketball games, {len(competitions)} competitions and "
                f"{sum(len(players) for players in players_by_side.values())} player rows from MaccabiPedia "
                f"({len(player_rows_without_game)} player rows belong to no game)")
    return BasketballGamesStats(games, player_rows_without_game)
