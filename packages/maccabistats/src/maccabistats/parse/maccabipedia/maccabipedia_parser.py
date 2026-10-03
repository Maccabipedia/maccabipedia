# -*- coding: utf-8 -*-


import html
import logging
from collections import defaultdict
from datetime import timedelta
from typing import Dict, Iterable, Set

from dateutil.parser import parse as datetime_parser

from maccabistats.models.game_data import GameData
from maccabistats.models.player_game_events import GameEvent, GameEventTypes, GoalTypes, GoalGameEvent, AssistTypes, \
    AssistGameEvent
from maccabistats.models.player_in_game import PlayerInGame
from maccabistats.models.team_in_game import TeamInGame
from maccabistats.parse.maccabipedia.maccabipedia_cargo_chunks_crawler import MaccabiPediaCargoChunksCrawler

logger = logging.getLogger(__name__)

_PAGE_NAME_FIELD_NAME = "_pageName"
_MACCABI_TEAM = 1
_NOT_MACCABI_TEAM = 0


# MaccabiPedia to Maccabistats event mapping
def _unknown_event():
    return GameEventTypes.UNKNOWN


_EMPTY_SUB_EVENT = ""
_DUPLICATE_MACCABIPEDIA_EVENT = "DUPLICATE"
# If we cant find an event, unknown will be set
MACCABI_PEDIA_EVENTS = defaultdict(_unknown_event,
                                   {1: defaultdict(_unknown_event, {_EMPTY_SUB_EVENT: GameEventTypes.LINE_UP,
                                                                    111: GameEventTypes.LINE_UP}),  # Special for GK
                                    2: defaultdict(_unknown_event, {_EMPTY_SUB_EVENT: GameEventTypes.BENCHED,
                                                                    211: GameEventTypes.BENCHED}),
                                    3: GameEventTypes.GOAL_SCORE,  # Special case, parse also the sub-goal-type
                                    4: GameEventTypes.GOAL_ASSIST,  # Special case, parse also the sub-assist-type

                                    5: defaultdict(_unknown_event, {_EMPTY_SUB_EVENT: GameEventTypes.SUBSTITUTION_IN}),
                                    6: defaultdict(_unknown_event, {_EMPTY_SUB_EVENT: GameEventTypes.SUBSTITUTION_OUT}),
                                    7: defaultdict(_unknown_event, {71: GameEventTypes.YELLOW_CARD,
                                                                    72: GameEventTypes.SECOND_YELLOW_CARD,
                                                                    73: GameEventTypes.RED_CARD,
                                                                    74: GameEventTypes.FIRST_YELLOW_CARD}),
                                    8: defaultdict(_unknown_event, {81: _DUPLICATE_MACCABIPEDIA_EVENT,
                                                                    82: GameEventTypes.PENALTY_MISSED,
                                                                    83: GameEventTypes.PENALTY_STOPPED,
                                                                    84: _DUPLICATE_MACCABIPEDIA_EVENT}),
                                    # No support atm for penalty save
                                    9: defaultdict(_unknown_event, {_EMPTY_SUB_EVENT: GameEventTypes.CAPTAIN}),
                                   # EventType=13: "display only" events (e.g. goals in technically-cancelled games) — ignore for stats
                                   13: defaultdict(lambda: _DUPLICATE_MACCABIPEDIA_EVENT, {})})

MACCABIPEDIA_GOALS_TYPE = {30: GoalTypes.UNCATEGORIZED,
                           31: GoalTypes.NORMAL_KICK,
                           32: GoalTypes.HEADER,
                           33: GoalTypes.OWN_GOAL,
                           34: GoalTypes.FREE_KICK,
                           35: GoalTypes.PENALTY,
                           36: GoalTypes.BICYCLE_KICK,
                           37: GoalTypes.UNKNOWN,
                           38: GoalTypes.CORNER,
                           39: GoalTypes.CHEST,
                           }

MACCABIPEDIA_ASSISTS_TYPE = {40: AssistTypes.UNCATEGORIZED,
                             41: AssistTypes.NORMAL_ASSIST,
                             42: AssistTypes.FREE_KICK_ASSIST,
                             43: AssistTypes.CORNER_ASSIST,
                             44: AssistTypes.PENALTY_WINNING_ASSIST,
                             45: AssistTypes.THROW_IN_ASSIST,
                             46: AssistTypes.UNKNOWN,
                             47: AssistTypes.HEADER_ASSIST,
                             }


def _without_quote_marks(name: str) -> str:
    """ The wiki strips ' and " from a game's opponent field when it saves the page (not the Hebrew ׳ ״). """
    return name.replace('"', '').replace("'", '')


def build_opponent_names_lookup(opponent_page_names: Iterable[str]) -> Dict[str, str]:
    """
    Map an opponent name as a game stores it (quote marks stripped) to the opponent page's name.
    Two pages that differ only by quote marks would be indistinguishable, so such a key is left out
    and those games keep the stored name.
    """
    pages_by_key: Dict[str, Set[str]] = defaultdict(set)
    for page_name in opponent_page_names:
        page_name = html.unescape(page_name)
        pages_by_key[_without_quote_marks(page_name)].add(page_name)

    ambiguous = {key: pages for key, pages in pages_by_key.items() if len(pages) > 1}
    for key, pages in ambiguous.items():
        logger.warning(f"Opponent pages {sorted(pages)} differ only by quote marks, games with {key!r} keep that name")

    return {key: pages.pop() for key, pages in pages_by_key.items() if key not in ambiguous}


def restore_opponent_name(stored_name: str, opponent_names_lookup: Dict[str, str]) -> str:
    """ ביתר ירושלים -> בית"ר ירושלים; a name with no opponent page (e.g. 'מכבי פת') is kept as stored. """
    return opponent_names_lookup.get(_without_quote_marks(stored_name), stored_name)


class MaccabiPediaParser(object):

    def __init__(self):
        """
        Fetching games table and games_events table from maccabipedia and merge the results (group by the page name)
        """

        # Json as it downloaded from maccabipedia mediawiki api
        self._games_metadata_as_json = self._get_games_metadata()
        self._games_events_as_json = self._get_games_events()
        self._opponent_names_lookup = build_opponent_names_lookup(
            row["OriginalName"] for row in MaccabiPediaCargoChunksCrawler.create_opponents_crawler()
            if row.get("OriginalName"))

        # Dict from pageName to json
        # TODO: should check if there are more than 1 item in any list, means two game share the same date
        self._game_metadata_by_game = defaultdict(list)
        [self._game_metadata_by_game[game[_PAGE_NAME_FIELD_NAME]].append(game) for game in self._games_metadata_as_json]
        self._games_events_by_game = defaultdict(list)
        [self._games_events_by_game[game_event[_PAGE_NAME_FIELD_NAME]].append(game_event) for game_event in
         self._games_events_as_json]

    @staticmethod
    def _get_games_metadata():
        return [game_metadata_as_json for game_metadata_as_json in
                MaccabiPediaCargoChunksCrawler.create_games_crawler()]

    @staticmethod
    def _get_games_events():
        return [game_events_as_json for game_events_as_json in
                MaccabiPediaCargoChunksCrawler.create_games_events_crawler()]

    def _parse_player_event(self, player_event):
        """
        Parse event from json to maccabistats event format, Maccabipedia contains "double" events (two events for one maccabistats event),
        We ignore those (return None).

        :param player_event: dict

        :rtype: maccabistats.models.player_game_events.GameEvent or None
        """

        event_time = timedelta(minutes=player_event["Minute"])
        # While upgrading MaccabiPedia from 1.35 to 1.39, cargo returned Nulls (instead of "" as before):
        sub_type = player_event.get("SubType", "")

        if GameEventTypes.GOAL_SCORE == MACCABI_PEDIA_EVENTS[player_event["EventType"]]:
            return GoalGameEvent(time_occur=event_time, goal_type=MACCABIPEDIA_GOALS_TYPE[sub_type])
        if GameEventTypes.GOAL_ASSIST == MACCABI_PEDIA_EVENTS[player_event["EventType"]]:
            return AssistGameEvent(time_occur=event_time,
                                   assist_type=MACCABIPEDIA_ASSISTS_TYPE[sub_type])
        elif GameEventTypes.UNKNOWN == MACCABI_PEDIA_EVENTS[player_event["EventType"]]:
            return GameEvent(game_event_type=GameEventTypes.UNKNOWN, time_occur=event_time)
        else:
            event_type = MACCABI_PEDIA_EVENTS[player_event["EventType"]][sub_type]
            if event_type == GameEventTypes.UNKNOWN:
                logger.warning(f"Encountered unknown event at this event: {player_event}")

            if event_type == _DUPLICATE_MACCABIPEDIA_EVENT:
                return None
            else:
                return GameEvent(game_event_type=event_type, time_occur=event_time)

    def _extract_players_events_for_team(self, game_events_as_json, log_errors: bool):
        """
        Extract all the players events from the game events.

        :param game_events_as_json: list of game events as json
        :type game_events_as_json: list of dict

        :rtype: list of maccabistats.models.player_in_game.PlayerInGame
        """

        players = []
        # Order all the events by player name:   "PlayerName" to list of his events
        players_events_by_name = defaultdict(list)
        [players_events_by_name[player_event["PlayerName"]].append(player_event) for player_event in
         game_events_as_json]

        for player_name, player_json_events in players_events_by_name.items():

            player_number = set(event.get("PlayerNumber", "") for event in player_json_events)

            if log_errors and len(player_number) > 1:
                # Removing any 0 from this player number Set,
                # 0 may indicates we are not sure about his number or it's a mistake

                # We don't log a case when player has only empty numbers,
                # because this is is an information we could not have for the entire games (1920-1950 are hardest)
                non_empty_number = (player_number - {''}) - {0}

                if len(non_empty_number) > 1:
                    logger.warning(f"Found more than 1 player_number for player: {player_name}, "
                                   f"numbers: {player_number}, "
                                   f"game: {player_json_events[0]['_pageName']}")

                elif len(non_empty_number) == 1:
                    logger.warning(f"Player: {player_name} has a number in this game: {non_empty_number}, "
                                   f" but at least one event is missing this number, "
                                   f"game: {player_json_events[0]['_pageName']}")

            player_number = player_number.pop()  # Take the first/only number
            # Adds all events, remove the None ones (means they are duplicates
            player_parsed_events = list(
                filter(None.__ne__, [self._parse_player_event(event) for event in player_json_events]))

            # TODO: handle the case that the number is 0 (no number probably and 0 is because of the db default)
            players.append(PlayerInGame(player_name, player_number, player_parsed_events))

        return players

    def _build_maccabistats_game(self, game_metadata, game_events):
        """
        Build maccabistats game object, creates two teams with their players (and events).

        :param game_metadata: json of the game metadata (coaches names, date and so on)
        :type game_metadata: dict
        :param game_events: players events as json
        :type game_events: list of dict

        :rtype: GameData
        """

        maccabi_players = self._extract_players_events_for_team(
            [event for event in game_events if event['Team'] == _MACCABI_TEAM],
            log_errors=True)
        maccabi_team = TeamInGame("מכבי תל אביב", game_metadata.get("CoachMaccabi", ''), game_metadata["ResultMaccabi"],
                                  maccabi_players)

        not_maccabi_players = self._extract_players_events_for_team(
            [event for event in game_events if event['Team'] == _NOT_MACCABI_TEAM],
            log_errors=False)

        opponent_name = restore_opponent_name(game_metadata.get("Opponent", ""), self._opponent_names_lookup)
        not_maccabi_team = TeamInGame(opponent_name,game_metadata.get("CoachOpponent", ''),
                                      game_metadata["ResultOpponent"], not_maccabi_players)

        home_team, away_team = (maccabi_team, not_maccabi_team) if game_metadata.get("HomeAway", '') == "בית" else (
            not_maccabi_team, maccabi_team)

        # 'Technical' is 1: for win, 2: for lose, -1: for non technical result game (regular game)
        technical = True if game_metadata['Technical'] in [1, 2] else False

        return GameData(competition=game_metadata["Competition"], fixture=game_metadata.get("Leg", ''),
                        date_as_hebrew_string="",
                        stadium=game_metadata.get("Stadium", ''), crowd=game_metadata.get("Crowd", ''),
                        referee=game_metadata.get("Refs", ''),
                        home_team=home_team,
                        away_team=away_team, season_string=str(game_metadata["Season"]), half_parsed_events=[],
                        date=datetime_parser(f"{game_metadata['Date']} {game_metadata.get('Hour', '')}"),
                        technical_result=technical)

    def parse(self):
        """
        Building game data from each page name (game metadata & game events).

        :return: List of the merged games from maccabipedia (with the games events)
        :rtype: list of GameData
        """

        parsed_games = []
        for game_name in self._game_metadata_by_game.keys():
            logger.info(f"Parsing game at {game_name}")
            # Take the first game from each date, we should assume its ok or we will have a lot of problems
            parsed_games.append(self._build_maccabistats_game(self._game_metadata_by_game[game_name][0],
                                                              self._games_events_by_game[game_name]))

        return parsed_games
