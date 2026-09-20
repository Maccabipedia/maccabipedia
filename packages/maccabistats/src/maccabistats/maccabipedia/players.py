from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, FrozenSet

from dateutil.parser import parse as datetime_parser

from maccabistats.parse.maccabipedia.maccabipedia_cargo_chunks_crawler import MaccabiPediaCargoChunksCrawler


@dataclass
class MaccabiPediaPlayerData(object):
    name: str
    birth_date: datetime
    is_home_player: bool
    is_goalkeeper: bool = False


# Profiles.MainPosition, see the wiki's Players_Positions table
_GOALKEEPER_POSITION = 1


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
        # By their profile, so a keeper is known from his debut. Opponents have no profile - the bot looks them up
        self.goalkeepers = frozenset(player_data.name for player_data in self._players_data.values()
                                     if player_data.is_goalkeeper)

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

