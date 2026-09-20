"""Opponent goalkeepers, as MaccabiPedia's own game pages recorded them.

maccabistats knows Maccabi's goalkeepers from their profiles, but opponents have no profile
page, so the only record of them keeping goal is the games themselves.
"""
import logging
from collections import Counter
from typing import FrozenSet

import requests
from maccabistats.parse.maccabipedia.maccabipedia_cargo_chunks_crawler import MaccabiPediaCargoChunksCrawler

logger = logging.getLogger(__name__)

# Games_Events.SubType of "הרכב-שוער" and "ספסל-שוער"
_GOALKEEPER_SUB_EVENT_CODES = "111,211"
_OPPONENT_TEAM = 0
# A single keeper mark may be a mistake (it happened: an outfield player got a bench keeper's mark)
_MIN_GOALKEEPER_GAMES = 2


def fetch_opponent_goalkeepers() -> FrozenSet[str]:
    """Opponents who kept goal in at least 2 MaccabiPedia games.

    Marking goalkeepers is optional, so a failed query returns none instead of failing the upload.
    """
    try:
        goalkeeper_events = MaccabiPediaCargoChunksCrawler(
            tables_name="Games_Events",
            tables_fields="Games_Events._pageName, Games_Events.PlayerName",
            where_condition=f"Games_Events.SubType IN ({_GOALKEEPER_SUB_EVENT_CODES}) "
                            f"AND Games_Events.Team={_OPPONENT_TEAM}")
        goalkeepers = trusted_goalkeeper_names(goalkeeper_events)
    except (ValueError, requests.RequestException):
        logger.exception("Could not fetch the opponents' goalkeepers, uploading without marking them")
        return frozenset()

    logger.info(f"Found {len(goalkeepers)} opponent goalkeepers")
    return goalkeepers


def trusted_goalkeeper_names(goalkeeper_events) -> FrozenSet[str]:
    """The goalkeepers' names, without those we can't trust: one-word names (old games list many
    players as לוי, מזרחי) and names marked in a single game (which may be a mistake).
    """
    games_per_goalkeeper = Counter(player_name for player_name, _ in
                                   {(event["PlayerName"], event["_pageName"]) for event in goalkeeper_events})

    return frozenset(player_name for player_name, games in games_per_goalkeeper.items()
                     if games >= _MIN_GOALKEEPER_GAMES and " " in player_name.strip())
