"""Load every basketball game from MaccabiPedia's Cargo tables."""
import logging
from datetime import date
from typing import Dict, List

from maccabistats.basketball.models import (
    BasketballCompetitionFlags,
    BasketballGameData,
    BasketballGameVideos,
    BasketballTeamInGame,
)
from maccabistats.basketball.stats import BasketballGamesStats
from maccabistats.parse.maccabipedia.maccabipedia_cargo_chunks_crawler import MaccabiPediaCargoChunksCrawler

logger = logging.getLogger(__name__)

MACCABI_NAME = "מכבי תל אביב"

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
# Smaller than Cargo's 5000 on purpose: the rows are wide and the shared host answers 508 under load.
_ROWS_PER_REQUEST = 2500
_REQUEST_TIMEOUT_SECONDS = 120


def _text(raw: Dict, field: str) -> str | None:
    # Cargo types a column by its values, so a season like 1957 arrives as a number.
    value = raw.get(field)
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip()


def _flag(raw: Dict, field: str) -> bool:
    return raw.get(field) in (1, "1", True)


def _team_from_cargo(raw: Dict, side: str, name: str | None) -> BasketballTeamInGame:
    return BasketballTeamInGame(
        name=name,
        coach=_text(raw, f"Coach{side}"),
        score=raw.get(f"TotalPoints{side}"),
        quarters=tuple(raw.get(f"{period}QuarterPoints{side}") for period in _PERIODS),
        halves=tuple(raw.get(f"{period}HalfPoints{side}") for period in _PERIODS[:2]),
        overtimes=tuple(raw.get(f"{period}OvertimePoints{side}") for period in _PERIODS),
    )


def competition_flags_from_cargo(raw: Dict) -> BasketballCompetitionFlags:
    return BasketballCompetitionFlags(
        current_name=_text(raw, "CurrentName"),
        is_league=_flag(raw, "League"),
        is_trophy=_flag(raw, "Trophy"),
        is_international=_flag(raw, "International"),
        is_official=_flag(raw, "Official"),
    )


def game_from_cargo(raw: Dict, competitions: Dict[str, BasketballCompetitionFlags]) -> BasketballGameData:
    """
    :param raw: One Basketball_Games row as the crawler yields it (no key for an empty value)
    :param competitions: The catalog, by the competition's name as game pages write it
    """
    raw_date = _text(raw, "Date")
    competition = _text(raw, "Competition")
    opponent = _text(raw, "Opponent")
    return BasketballGameData(
        page_name=raw["_pageName"],
        date=date.fromisoformat(raw_date[:10]) if raw_date else None,
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
        maccabi=_team_from_cargo(raw, "Maccabi", MACCABI_NAME),
        opponent_team=_team_from_cargo(raw, "Opponent", opponent),
    )


def _crawl(table: str, fields: str) -> List[Dict]:
    return list(MaccabiPediaCargoChunksCrawler(
        tables_name=table, tables_fields=fields, limit=_ROWS_PER_REQUEST, order_by="_pageName",
        unescape_all_strings=True, timeout=_REQUEST_TIMEOUT_SECONDS))


def _count_rows(table: str) -> int:
    count_rows = list(MaccabiPediaCargoChunksCrawler(
        tables_name=table, tables_fields="COUNT(_pageName)=RowsCount", timeout=_REQUEST_TIMEOUT_SECONDS))
    return int(count_rows[0]["RowsCount"])


def _crawl_whole_table(table: str, fields: str) -> List[Dict]:
    """
    The crawler stops at the first request that returns fewer rows than asked, so a response cut
    short would end the crawl early with no error; and a page saved mid-crawl can move a row across
    a request's edge. So the crawl is checked against the table's row count, and repeated once.
    """
    for attempt in ("first", "second"):
        rows = _crawl(table, fields)
        if not rows:
            raise RuntimeError(f"MaccabiPedia returned no rows for {table}")

        rows_on_wiki = _count_rows(table)
        if len(rows) == rows_on_wiki:
            return rows
        logger.warning(f"{table}: the {attempt} crawl returned {len(rows)} rows, the wiki counts {rows_on_wiki}")

    raise RuntimeError(f"{table}: crawled {len(rows)} rows twice, but the wiki counts {rows_on_wiki}")


def load_basketball_from_maccabipedia() -> BasketballGamesStats:
    """Crawl every basketball game from MaccabiPedia. Nothing is saved; see serialize_basketball_games."""
    competitions = {raw["OriginalName"]: competition_flags_from_cargo(raw)
                    for raw in _crawl_whole_table(_COMPETITIONS_TABLE, _COMPETITIONS_FIELDS)}
    games = [game_from_cargo(raw, competitions) for raw in _crawl_whole_table(_GAMES_TABLE, _GAMES_FIELDS)]

    logger.info(f"Loaded {len(games)} basketball games and {len(competitions)} competitions from MaccabiPedia")
    return BasketballGamesStats(games)
