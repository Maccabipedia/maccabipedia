from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta
from typing import AbstractSet, List, Mapping, Optional

from maccabistats.models.player_game_events import GameEventTypes, GoalTypes

logger = logging.getLogger(__name__)

maccabistats_events_to_maccabipedia_events = {GameEventTypes.LINE_UP.value: "הרכב",
                                              GameEventTypes.BENCHED.value: "ספסל",
                                              GameEventTypes.GOAL_SCORE.value: "גול",
                                              GameEventTypes.GOAL_ASSIST.value: "בישול",
                                              GameEventTypes.SUBSTITUTION_IN.value: "מחליף",
                                              GameEventTypes.SUBSTITUTION_OUT.value: "מוחלף",
                                              GameEventTypes.YELLOW_CARD.value: "כרטיס צהוב",
                                              GameEventTypes.FIRST_YELLOW_CARD.value: "כרטיס צהוב-ראשון",
                                              GameEventTypes.SECOND_YELLOW_CARD.value: "כרטיס צהוב-שני",
                                              GameEventTypes.RED_CARD.value: "כרטיס אדום",
                                              GameEventTypes.CAPTAIN.value: "קפטן",
                                              GameEventTypes.PENALTY_MISSED.value: "פנדל-החמצה",
                                              GameEventTypes.PENALTY_STOPPED.value: "פנדל-עצירה",
                                              }

maccabistats_sub_events_to_maccabipedia_events = {GoalTypes.OWN_GOAL.value: "עצמי",
                                                  GoalTypes.PENALTY.value: "פנדל",
                                                  GoalTypes.UNKNOWN.value: None,
                                                  GoalTypes.HEADER.value: "נגיחה",
                                                  GoalTypes.FREE_KICK.value: "בעיטה חופשית",
                                                  GoalTypes.NORMAL_KICK.value: None,
                                                  GoalTypes.UNCATEGORIZED.value: None,
                                                  GoalTypes.BICYCLE_KICK.value: "עקרב",
                                                  GoalTypes.CORNER.value: "קרנר",
                                                  GoalTypes.CHEST.value: "חזה",
                                                  }

SQUAD_RANK = {"הרכב": 0,
              "קפטן": 1,
              "ספסל": 2,

              "שוער": 4,  # Goal keeper should be written before players
              None: 5  # No sub event
              }

SUBS_RANK = defaultdict(lambda: 5, {"מוחלף": 6,
                                    "מחליף": 7})

# Assists, Goals then the rest (only if the events are at the same minute)
GOALS_RANK = defaultdict(lambda: 2, {"פנדל": 2,  # In case we scored a goal from penalty, the miss should be before
                                     "בישול": 3,
                                     "גול": 4,

                                     "החמצה": 7,
                                     "עצירה": 8})

SQUAD = [maccabistats_events_to_maccabipedia_events[GameEventTypes.LINE_UP.value],
         maccabistats_events_to_maccabipedia_events[GameEventTypes.BENCHED.value],
         maccabistats_events_to_maccabipedia_events[GameEventTypes.CAPTAIN.value]]

CARDS_AND_SUBS = [maccabistats_events_to_maccabipedia_events[GameEventTypes.RED_CARD.value],
                  maccabistats_events_to_maccabipedia_events[GameEventTypes.YELLOW_CARD.value],
                  maccabistats_events_to_maccabipedia_events[GameEventTypes.SUBSTITUTION_IN.value],
                  maccabistats_events_to_maccabipedia_events[GameEventTypes.SUBSTITUTION_OUT.value]]

GOALS_INVOLVED = [maccabistats_events_to_maccabipedia_events[GameEventTypes.GOAL_SCORE.value],
                  maccabistats_events_to_maccabipedia_events[GameEventTypes.GOAL_ASSIST.value],
                  "פנדל"]

_MACCABIPEDIA_PROPERTY_SEPARATOR = "::"

MACCABI_TEAM = "מכבי"
OPPONENT_TEAM = "יריבה"


class PlayerEvent(object):
    def __init__(self, name: str, number: str, time_occur: timedelta, event_type: str,
                 sub_event_type: str, maccabi_player: bool, game_part: Optional[str] = None):
        """
        :param name: The player name
        :param number: The player number
        :param time_occur: The time the event has occurred to this player
        :param event_type: The player event type (look at maccabistats.models.player_game_events.py) like: "הרכב"
        :param sub_event_type: The player sub event type, like goal by *head*(head=sub event type),
                               the sub type is just goal types atm, may be change in the future, like: "חופשית"
        :param maccabi_player: does this player is maccabi player
        :param game_part: In which game part this event occur? first/second half? extra time? and so on
        """
        self.name = name
        self.number = number or "אין-מספר"
        self.minute_occur = int(time_occur.seconds / 60)
        self.event_type = event_type
        self.sub_event_type = sub_event_type
        self.team = MACCABI_TEAM if maccabi_player else OPPONENT_TEAM
        self.game_part = game_part

        # Not for export:
        self.maccabi_player = maccabi_player

    @staticmethod
    def _translate_event_to_maccabipedia(event) -> GameEventTypes:
        """
        Translate the event name to hebrew
        :param event: maccabistats event type to translate (to maccabipedia one).
        """
        if event.value not in maccabistats_events_to_maccabipedia_events:
            raise RuntimeError("There is no matching maccabipedia event for {event}".format(event=event.value))
        else:
            return maccabistats_events_to_maccabipedia_events[event.value]

    @staticmethod
    def _translate_sub_event_to_maccabipedia(sub_event) -> GoalTypes:
        """
        Translate the event name to hebrew
        :param sub_event: maccabistats sub event type to translate (to maccabipedia one).
        """
        if sub_event.value not in maccabistats_sub_events_to_maccabipedia_events:
            raise RuntimeError(
                "There is no matching maccabipedia sub event for {sub_event}".format(sub_event=sub_event.value))
        else:
            return maccabistats_sub_events_to_maccabipedia_events[sub_event.value]

    def __eq__(self, other):
        if not isinstance(other, PlayerEvent):
            return False

        return self.__dict__ == other.__dict__

    @staticmethod
    def _raise_if_we_compare_events_from_two_different_groups(first_type: str, second_type: str) -> None:
        """
        This class is built in order ot compare event and order them on maccabipedia game pages.
        We should not compare (just for easier implementation) events which are not on the same group.
        Like: Squad event and a Goal event.
        """
        squad = (first_type in SQUAD) == (second_type in SQUAD)
        cards_and_subs = (first_type in CARDS_AND_SUBS) == (second_type in CARDS_AND_SUBS)
        goals_involved = (first_type in GOALS_INVOLVED) == (second_type in GOALS_INVOLVED)

        # Events must be in same group, we don't handle compare of not same group events (we don't need):
        if not squad or not cards_and_subs or not goals_involved:
            raise RuntimeError(f"Events should be in the same group: {first_type} and {second_type} ")

    def __lt__(self, other: PlayerEvent) -> bool:
        """
        Compare two events, True if "self" is less than "other", False otherwise.
        less than means that "self" event should appear before "other" event on the maccabipedia game page.
        """
        self._raise_if_we_compare_events_from_two_different_groups(self.event_type, other.event_type)

        # On the same group, maccabi players should appear before the opponent
        if self.maccabi_player and not other.maccabi_player:
            return True
        elif not self.maccabi_player and other.maccabi_player:
            return False

        # Both events belongs to players on the same team for sure from now on:
        if self.event_type in SQUAD:  # Squad, Captain, Bench. GoalKeeper first, Sort by shirt number in order of "tie".
            return (SQUAD_RANK[self.event_type], SQUAD_RANK[self.sub_event_type], self.number) < (
                SQUAD_RANK[other.event_type], SQUAD_RANK[other.sub_event_type], other.number)

        if self.event_type in CARDS_AND_SUBS:
            return (self.minute_occur, SUBS_RANK[self.event_type]) < (other.minute_occur, SUBS_RANK[other.event_type])

        if self.event_type in GOALS_INVOLVED:
            return (self.minute_occur, GOALS_RANK[self.event_type]) < (other.minute_occur, GOALS_RANK[other.event_type])

    def __maccabipedia__(self) -> str:
        """
        Return the player event as maccabipedia format expect it
        """
        # Hacky part for backward compatible (we don't want to add game part in events we didn't had one).
        game_part_property = "" if self.game_part is None else f"::{self.game_part}"

        if self.sub_event_type is not None:
            return f"{self.name}::{self.number}::{self.event_type}-{self.sub_event_type}::{self.minute_occur}::{self.team}{game_part_property}\n"
        else:
            return f"{self.name}::{self.number}::{self.event_type}::{self.minute_occur}::{self.team}{game_part_property}\n"

    def __repr__(self) -> str:
        return self.__maccabipedia__()

    @classmethod
    def from_maccabistats_event_type(cls, name: str, number: int, time_occur: timedelta, event_type: GameEventTypes,
                                     sub_event_type: GoalTypes, maccabi_player: bool) -> PlayerEvent:
        """
        :param name: The player name
        :param number: The player number
        :param time_occur: The time the event has occurred to this player
        :param event_type: The player event type (look at maccabistats.models.player_game_events.py)
        :param sub_event_type: The player sub event type, like goal by *head*(head=sub event type),
                               the sub type is just goal types atm, may be change in the future.
        :param maccabi_player: does this player is maccabi player
        """
        event_type = PlayerEvent._translate_event_to_maccabipedia(event_type)
        sub_event_type = PlayerEvent._translate_sub_event_to_maccabipedia(sub_event_type) if sub_event_type else None

        return PlayerEvent(name, number, time_occur, event_type, sub_event_type, maccabi_player)

    @classmethod
    def from_maccabipedia_format(cls, maccabipedia_text_format: str) -> PlayerEvent:
        """
        Creates a PlayerEvent from maccabipedia text format, like:
        צבי סטודינסקי::אין-מספר::הרכב::0::מכבי

        format:
        name::number::event-sub_type::minute::is_maccabi_team::game_part

        name - Player name
        number - Player number
        event - The main event (like goal or assist)
        sub_type - Optional, like goal in free kick. Not all events has sub events (like captain as main event)
        minute - The minute which the event occurs at
        is_maccabi_team - This event belongs to maccabi player?
        game_part - Optional, For minutes that may be in more than one game part, like minute 46 - first/second half?
        """
        # Remove leading and ending new lines + split
        properties = maccabipedia_text_format.strip('\n').split(_MACCABIPEDIA_PROPERTY_SEPARATOR)
        if not 5 <= len(properties) <= 6:  # Might have game_part - optional
            raise TypeError(
                f"{maccabipedia_text_format} should have 5 properties (separated by {_MACCABIPEDIA_PROPERTY_SEPARATOR}).")

        name = properties[0]
        number = properties[1]
        minute_occur = timedelta(minutes=int(properties[3]))
        team = properties[4] == MACCABI_TEAM

        event_and_sub_event = properties[2].split('-')
        event_type_name = event_and_sub_event[0]
        sub_event_type_name = None
        if len(event_and_sub_event) > 1:
            sub_event_type_name = event_and_sub_event[1]

        game_part = None
        if len(properties) == 6:
            game_part = properties[5]

        return PlayerEvent(name, number, minute_occur, event_type_name, sub_event_type_name, team, game_part)


def mark_goalkeepers(events: List[PlayerEvent], goalkeepers_by_team: Mapping[str, AbstractSet[str]]) -> None:
    """
    Write the line-up and bench events of known goalkeepers as הרכב-שוער / ספסל-שוער.
    The club site doesn't say who the goalkeepers are, MaccabiPedia does.

    :param goalkeepers_by_team: the goalkeepers' names per team ("מכבי"/"יריבה"), since the teams are
                                known from different sources: Maccabi's players have a profile page, the opponents don't.
    """
    line_up = maccabistats_events_to_maccabipedia_events[GameEventTypes.LINE_UP.value]
    benched = maccabistats_events_to_maccabipedia_events[GameEventTypes.BENCHED.value]
    for event in events:
        if event.event_type in (line_up, benched) and event.sub_event_type is None \
                and event.name in goalkeepers_by_team.get(event.team, frozenset()):
            event.sub_event_type = "שוער"
            logger.info(f"Marked {event.name} ({event.team}) as goalkeeper: {event.event_type}-{event.sub_event_type}")

    for team in (MACCABI_TEAM, OPPONENT_TEAM):
        if not any(event.team == team and event.event_type == line_up and event.sub_event_type == "שוער" for event in events):
            logger.warning(f"No known goalkeeper in the {team} line-up, mark it by hand")
