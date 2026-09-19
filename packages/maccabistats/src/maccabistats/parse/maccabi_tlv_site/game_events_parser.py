# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import timedelta
import logging

from maccabistats.parse.name_normalization import normalize_name
from maccabistats.models.player_game_events import GameEventTypes, GoalGameEvent, GameEvent, GoalTypes

logger = logging.getLogger(__name__)
fully_game_time_without_penalties = timedelta(minutes=120)


class CantFindEventException(Exception):
    pass


class ComplicatedEventException(Exception):
    pass


class TooManySameEventsException(Exception):
    pass


class FoundNoMatchingPlayersByNameException(Exception):
    pass


class MaccabiSiteGameEventsParser(object):
    """
    This class is responsible to parse the events from events page and add events that could not be added with squads page, like:
    subs-in if found in event page and wasn't found in squads page.
    subs-out for players that have subs-in event in the same game!
    yellow & red cards that found in events page and can't be found in squads page.
    assists events.
    goal type, like by head, by free-kick, by penalty ...

    for other events, if they found in events page and can't be found in squads page log is written, some of them might be a bug while parsing,
    others might be bug in maccabi site.
    """

    def __init__(self, maccabi_team, not_maccabi_team, bs_content, game_link):
        """
        There are 3 divs for each team ordered as: lineup_players, bench_players, coach.
        :type bs_content: bs4.element.Tag
        :type maccabi_team: maccabistats.models.team_in_game.TeamInGame
        :type not_maccabi_team: maccabistats.models.team_in_game.TeamInGame
        :param game_link: the maccabi-tlv game link, for debugging.
        :type game_link: str
        """

        logger.info("Parsing maccabi-{opponent}".format(opponent=not_maccabi_team.name))

        self.bs_content = bs_content
        self.maccabi_team = maccabi_team
        self.not_maccabi_team = not_maccabi_team
        self.game_link = game_link
        # We will save all the parsed events without matching events in squads page, to allow manipulate this data later.
        self.halfed_parsed_events = []

        self.events_bs_content_list = self.bs_content.select("article div.play-by-play-homepage ul.play-by-play li")

        # TODO - this should be oneliner
        self.event_type_to_handler_function = defaultdict(self.__handle_unknown_event)
        self.event_type_to_handler_function["red"] = self.__handle_red_card_event
        self.event_type_to_handler_function["yellow"] = self.__handle_yellow_card_event
        self.event_type_to_handler_function["assist"] = self.__handle_assist_event
        self.event_type_to_handler_function["goal"] = self.__handle_goal_event
        self.event_type_to_handler_function["sub"] = self.__handle_substitution_event
        self.event_type_to_handler_function["penalty-missed"] = self.__handle_penalty_missed_event
        self.event_type_to_handler_function["secondyellow"] = self.__handle_second_yellow_card_event
        self.event_type_to_handler_function["whistle"] = self.__handle_ignored_events

    def enrich_teams_with_events(self):
        """ Return the enriched (with game events) teams.
        :rtype: TeamInGame, TeamInGame
        """

        for event_id, event_bs_content in enumerate(self.events_bs_content_list):
            event_time_in_minute = timedelta(minutes=int(event_bs_content.select_one("div.min").get_text()))
            event_type = event_bs_content['class'][0]
            event_text = event_bs_content.select_one("p").get_text().strip()

            if fully_game_time_without_penalties <= event_time_in_minute:
                logger.info("Ignoring event in minute {min}".format(min=event_time_in_minute.seconds / 60.0))
                continue
            try:
                # should be like - defaultdict seems to call the default function when just trying to access the key:
                # self.event_type_to_handler_function[event_type](event_bs_content, event_text, event_time_in_minute)
                if event_type in self.event_type_to_handler_function:
                    self.event_type_to_handler_function[event_type](event_text, event_time_in_minute)
                else:
                    self.__handle_unknown_event(event_bs_content, event_text, event_time_in_minute)
            except ComplicatedEventException as e:
                logger.info("ComplicatedEventException : {details}".format(details=str(e)))
            except CantFindEventException:
                logger.warning("\nError parsing {event} at {event_time} from events page".format(event=event_text, event_time=event_time_in_minute))
            except Exception:
                logger.exception(
                    "\nUnknown error while parsing {event} at {event_time} from event page".format(event=event_text, event_time=event_time_in_minute))

        # Not inside the second yellow handler: the events page lists events newest first, so when a second yellow
        # is handled the player's first yellow isn't parsed yet (and the squad page shows only the yellow-red icon).
        self.__mark_first_yellow_cards()

        return self.maccabi_team, self.not_maccabi_team

    def __mark_first_yellow_cards(self):
        """ A sent-off player's earlier yellow card is the first of two, the way MaccabiPedia records it. """
        for player in self.maccabi_team.players + self.not_maccabi_team.players:
            for second_yellow in player.get_events_by_type(GameEventTypes.SECOND_YELLOW_CARD):
                earlier_yellows = [event for event in player.get_events_by_type(GameEventTypes.YELLOW_CARD)
                                   # <=: the site writes stoppage time as 45/90, so both cards can share a minute
                                   if event.time_occur <= second_yellow.time_occur]
                if earlier_yellows:
                    first_yellow = min(earlier_yellows, key=lambda event: event.time_occur)
                    first_yellow.event_type = GameEventTypes.FIRST_YELLOW_CARD
                    logger.info("Changed yellow card to first yellow card for player: {player}, {event}"
                                .format(player=player.name, event=first_yellow))

    def __find_one_player_with_name(self, player_name):
        """ Finds player by his name, validate that only 1 player have been found

        :rtype : PlayerInGame
        """

        player_name = normalize_name(player_name)

        if len(player_name) > 20:
            raise ComplicatedEventException(player_name)

        players = [player for player in self.maccabi_team.players if player.name == player_name]
        players.extend([player for player in self.not_maccabi_team.players if player.name == player_name])

        if len(players) > 1:
            logger.warning("Found more than 1 player named :{player_name}".format(player_name=player_name))
        elif len(players) == 0:
            raise FoundNoMatchingPlayersByNameException("Game link : {link}\n"
                                                        "Cant find player with that name : {name}".format(link=self.game_link,
                                                                                                          name=player_name))

        # In case there are some players, we prefer the last, attack player is more likely to score\assist goal (those event are the important here).
        return players[-1]

    def __get_one_player_by_event_details(self, player_name, event):
        """
        Find one player that match the event details (event object + player name), that solve the case when two players has the same name.
        The way to choose between them is by similarity to the given event.
        :param player_name: the player name to search
        :type player_name:str
        :param event: the event to look for similar event on player events.
        :type event: maccabistats.models.player_game_events.GameEvent
        :return: PlayerInGame
        """

        player_name = normalize_name(player_name)
        if len(player_name) > 20:
            raise ComplicatedEventException(player_name)

        players_events = [player.get_event_by_similar_event(event) for player in self.maccabi_team.players if player.name == player_name]
        players_events.extend([player.get_event_by_similar_event(event) for player in self.not_maccabi_team.players if player.name == player_name])
        players_events = list(filter(lambda e: e is not None, players_events))

        if len(players_events) > 1:
            logger.warning("Found more than 1 matching player events:{player_name}, event:{event}".format(player_name=player_name, event=event))
        elif len(players_events) == 0:
            raise CantFindEventException("Game link : {link}\nCant find player event by given details, player name:{name}, event:{event}"
                                         .format(link=self.game_link, name=player_name, event=event))

        return players_events[0]

    def __get_player_event(self, player, event):
        """ Check whether the given player got event in specific time
        :type player: maccabistats.models.player_in_game.PlayerInGame
        :type event: maccabistats.models.player_game_events.GameEvent
        :rtype: maccabistats.models.player_game_events.GameEvent
        """

        try:
            player_event = player.get_event_by_similar_event(event)
        except Exception as e:
            raise TooManySameEventsException("Probably Found {player_name} more than 1 matching event.\n"
                                             "    Game link : {link}\n"
                                             "    Event : {event}\n"
                                             "    Inner exception : {inner}".format(player_name=player.name,
                                                                                    link=self.game_link,
                                                                                    event=event,
                                                                                    inner=str(e)))

        if not player_event:
            raise CantFindEventException("Found {player_name} event in events page without matching event in squads page.\n"
                                         "    Game link : {link}\n"
                                         "    Event : {event}\n".format(player_name=player.name, link=self.game_link, event=event))

        return player_event

    def __handle_ignored_events(self, event_text, event_time_in_minute):
        pass

    def __handle_penalty_missed_event(self, event_text, event_time_in_minute):
        player_name = event_text.replace("פנדל הוחמץ על ידי", "").strip()
        player = self.__find_one_player_with_name(player_name)

        penalty_missed = GameEvent(GameEventTypes.PENALTY_MISSED, event_time_in_minute)
        player.add_event(penalty_missed)
        logger.info(
            "Added penalty missed for player: {player}".format(player=player_name))

    def __handle_second_yellow_card_event(self, event_text, event_time_in_minute):
        player_name = event_text.replace("כרטיס צהוב שני ל", "").strip()
        player = self.__find_one_player_with_name(player_name)

        second_yellow_event = GameEvent(GameEventTypes.SECOND_YELLOW_CARD, event_time_in_minute)
        try:
            player_event = self.__get_player_event(player, second_yellow_event)
            logger.info("Found second yellow event : {event}".format(event=player_event))
        except CantFindEventException:
            player.add_event(second_yellow_event)
            logger.info("Added second yellow event for player: {player}".format(player=player_name))

    def __handle_substitution_event(self, event_text, event_time_in_minute):
        player_name_sub_in, player_name_sub_out = event_text.strip().split("החליף את")
        player_sub_in = self.__find_one_player_with_name(player_name_sub_in)
        player_sub_out = self.__find_one_player_with_name(player_name_sub_out)

        sub_in_event = GameEvent(GameEventTypes.SUBSTITUTION_IN, event_time_in_minute)
        sub_out_event = GameEvent(GameEventTypes.SUBSTITUTION_OUT, event_time_in_minute)

        try:
            self.__get_player_event(player_sub_in, sub_in_event)
            logger.info("Found subs in event: {event}".format(event=sub_in_event))
        except CantFindEventException:
            player_sub_in.add_event(sub_in_event)
            logger.info("Added subs-in event for player: {player}".format(player=player_name_sub_in))

        try:
            self.__get_player_event(player_sub_out, sub_out_event)
            logger.info("Found subs out event: {event}".format(event=sub_out_event))
        except CantFindEventException:
            player_sub_in.add_event(sub_out_event)
            logger.info("Added subs-out event for player: {player}".format(player=player_name_sub_out))

    @staticmethod
    def __extract_goal_details(event_text, event_time_in_minute):
        """ Extracting final player name from the event_Text + creating goal event.
        :rtype: str, GoalGameEvent
        """

        player_name = normalize_name(event_text.replace("שער של", ""))
        goal_type = GoalTypes.UNKNOWN

        if "(פנדל)" in player_name:
            player_name = player_name.replace("(פנדל)", "").strip()
            goal_type = GoalTypes.PENALTY

        elif "פנדל הובקע על ידי" in player_name:
            player_name = player_name.replace("פנדל הובקע על ידי", "").strip()
            goal_type = GoalTypes.PENALTY

        elif "(שער עצמי)" in player_name:
            player_name = player_name.replace("(שער עצמי)", "").strip()
            goal_type = GoalTypes.OWN_GOAL

        goal_event = GoalGameEvent(event_time_in_minute, goal_type)

        return player_name, goal_event

    def __handle_goal_event(self, event_text, event_time_in_minute):
        player_name, goal_event = MaccabiSiteGameEventsParser.__extract_goal_details(event_text, event_time_in_minute)

        try:
            player_event = self.__get_one_player_by_event_details(player_name, goal_event)

            # Add goal type:
            if goal_event.goal_type is not GoalTypes.UNKNOWN:
                player_event.goal_type = goal_event.goal_type
                logger.info(
                    "Changed goal type to {goal_type} for player: {player}".format(goal_type=goal_event.goal_type,
                                                                                   player=player_name))
        except CantFindEventException:
            # We should hope no name that belong to two players in the same game will be related to goal.
            # by manually checking there are none (the above case takes care of them).
            try:
                player = self.__find_one_player_with_name(player_name)
                player.add_event(goal_event)
                logger.info("Added goal event for player: {player}".format(player=player.name))
            except FoundNoMatchingPlayersByNameException:
                logger.info("Adding event to half parsed event:{event}, for name:{name}".format(event=goal_event, name=player_name))
                self.halfed_parsed_events.append(dict(name=player_name, **goal_event.__dict__))

    def __handle_yellow_card_event(self, event_text, event_time_in_minute):
        player_name = event_text.replace("כרטיס צהוב ל", "").strip()
        player = self.__find_one_player_with_name(player_name)

        yellow_card_event = GameEvent(GameEventTypes.YELLOW_CARD, event_time_in_minute)

        try:
            self.__get_player_event(player, yellow_card_event)
        except CantFindEventException:
            player.add_event(yellow_card_event)
            logger.info("Added yellow card event for player: {player}".format(player=player.name))

    def __handle_red_card_event(self, event_text, event_time_in_minute):
        player_name = event_text.replace("כרטיס אדום ל", "").strip()
        player = self.__find_one_player_with_name(player_name)

        # Not seen in 2025/26-2026/27 (a second yellow comes as `secondyellow` only), so warn if the site starts doing it
        if GameEvent(GameEventTypes.SECOND_YELLOW_CARD, event_time_in_minute) in player.events:
            logger.warning("Found a red card at the minute of a second yellow for player: {player}, "
                           "treating it as the same sending-off. Game link: {link}".format(player=player.name, link=self.game_link))
            return

        red_card_event = GameEvent(GameEventTypes.RED_CARD, event_time_in_minute)
        try:
            player_event = self.__get_player_event(player, red_card_event)
            logger.info("Found red card event : {event}".format(event=player_event))
        except CantFindEventException:
            player.add_event(red_card_event)
            logger.info("Added red card event for player: {player}".format(player=player.name))

    def __handle_assist_event(self, event_text, event_time_in_minute):
        player_name = event_text.replace("בישול על ידי", "").strip()
        player = self.__find_one_player_with_name(player_name)

        assist_event = GameEvent(GameEventTypes.GOAL_ASSIST, event_time_in_minute)
        player.add_event(assist_event)
        logger.info("Added assist event for player: {player}".format(player=player_name))

    @staticmethod
    def __handle_unknown_event(event_bs_content, event_text, event_time_in_minute):
        event_type = event_bs_content['class'][0]
        logger.info("Unknown event type :{event_type} in minute :{minute}\n"
                    "With event text :{event_text}".format(event_type=event_type,
                                                           minute=event_time_in_minute, event_text=event_text))
