import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, FrozenSet

import requests
from dateutil.parser import parse as datetime_parser

from maccabistats.parse.maccabipedia.maccabipedia_cargo_chunks_crawler import MaccabiPediaCargoChunksCrawler

logger = logging.getLogger(__name__)


@dataclass
class MaccabiPediaPlayerData(object):
    name: str
    birth_date: datetime
    is_home_player: bool
    is_goalkeeper: bool = False


# Profiles.MainPosition, see the wiki's Players_Positions table
_GOALKEEPER_POSITION = 1
# Games_Events.SubType of "הרכב-שוער" and "ספסל-שוער"
_GOALKEEPER_SUB_EVENT_CODES = "111,211"
# Old games list many players by one name (לוי, מזרחי), which would match outfield players today
_RECENT_GOALKEEPERS_YEARS = 10
# A single keeper mark may be a mistake (it happened: an outfield player got a bench keeper's mark)
_MIN_GOALKEEPER_GAMES = 2


class MaccabiPediaPlayers(object):
    missing_birth_date_value = datetime_parser("1000")
    _instance = None
    # Pickles saved before goalkeepers were crawled load with none
    goalkeepers: FrozenSet[str] = frozenset()

    @classmethod
    def default_birth_day_value(cls, *args, **kwargs):
        return cls.missing_birth_date_value

    def __init__(self):
        # Using defaultdict in order for each player that does not have a date of birth in maccabipedia
        # will set to year 1000 (to notice visually in stats)
        self._players_data = self._crawl_players_data()
        self.players_dates = defaultdict(MaccabiPediaPlayers.default_birth_day_value,
                                         {player_name: player_data.birth_date for player_name, player_data in
                                          self._players_data.items()})
        self.home_players = {player_data.name for player_data in self._players_data.values() if
                             player_data.is_home_player}
        # Maccabi goalkeepers by their profile (so a debut is known too), opponents by the games they kept goal in
        self.goalkeepers = frozenset(
            {player_data.name for player_data in self._players_data.values() if player_data.is_goalkeeper}
            | self._crawl_recent_goalkeepers())

    @staticmethod
    def _crawl_recent_goalkeepers() -> FrozenSet[str]:
        since = (datetime.now() - timedelta(days=365 * _RECENT_GOALKEEPERS_YEARS)).strftime("%Y-%m-%d")

        # Only the uploader uses these, so a blocked Cargo response shouldn't fail the whole crawl
        try:
            goalkeepers_events = MaccabiPediaCargoChunksCrawler(
                tables_name="Games_Events",
                tables_fields="Games_Events._pageName, Games_Events.PlayerName",
                where_condition=f"Games_Events.SubType IN ({_GOALKEEPER_SUB_EVENT_CODES}) AND Games_Events.Date >= '{since}'")
            games_per_goalkeeper = Counter(player_name for player_name, _ in
                                           {(event["PlayerName"], event["_pageName"]) for event in goalkeepers_events})
        except (ValueError, requests.RequestException):
            logger.exception("Could not crawl the recent goalkeepers, keeping only the profiles' goalkeepers")
            return frozenset()

        return frozenset(player_name for player_name, games in games_per_goalkeeper.items()
                         if games >= _MIN_GOALKEEPER_GAMES and " " in player_name.strip())

    @staticmethod
    def _crawl_players_data() -> Dict[str, MaccabiPediaPlayerData]:
        players_data_iterator = MaccabiPediaCargoChunksCrawler(
            tables_name="Profiles",
            tables_fields="Profiles._pageName, Profiles.DoB, Profiles.HomePlayer, Profiles.MainPosition")

        players_data = dict()
        for player_raw_data in players_data_iterator:
            # Player Date of birth is missing for some players, we just take the default value for those
            # Birth date format is YYYY_MM_DD:
            birth_date = datetime_parser(
                player_raw_data['DoB']) if 'DoB' in player_raw_data else MaccabiPediaPlayers.missing_birth_date_value
            player_name = player_raw_data['_pageName']
            # We have players and coaches in the same table today, for coaches we don't set HomePlayer:
            is_home_player = bool(player_raw_data.get('HomePlayer', False))  # Should be 0 or 1

            is_goalkeeper = player_raw_data.get('MainPosition') == _GOALKEEPER_POSITION

            players_data[player_name] = MaccabiPediaPlayerData(name=player_name, birth_date=birth_date,
                                                               is_home_player=is_home_player,
                                                               is_goalkeeper=is_goalkeeper)

        return players_data

    @classmethod
    def get_players_data(cls):
        if cls._instance is None:
            cls._instance = cls()

        return cls._instance

