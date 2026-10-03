import logging
from collections import defaultdict
from datetime import timedelta
from itertools import chain, repeat
from typing import List, Tuple

from maccabistats.models.game_data import GameData
from maccabistats.models.player_game_events import GameEventTypes
from maccabistats.stats.maccabi_games_stats import MaccabiGamesStats

logger = logging.getLogger(__name__)

# Seasons that really ran past the year their name says, so a game dated in that later year is not an error:
#   1938    - the Arab revolt stopped the national league; the Tel Aviv league that counted towards it ended 14-01-1939.
#   1941/42 - the war-time league finished with a title play-off against Maccabi Rishon LeZion and Homenetmen
#             in September-October 1943 (Maccabi won it).
_PROLONGED_SEASONS_LAST_YEAR = {"1938": 1939, "1941/42": 1943}
"""
This class is responsible to find errors in MaccabiGamesStats object, 
such as games that the amount of goals does not match to the final score sum,
empty events and so on.

This should be run manually.
"""


class ErrorsFinder:
    """ Each public function on this class wil lbe run automatically by 'get_all_errors_numbers'. """

    def __init__(self, maccabi_games_stats: MaccabiGamesStats) -> None:
        self.maccabi_games_stats = maccabi_games_stats

    def get_games_without_11_maccabi_players_on_lineup(self):
        """ Each team should have 11 players with lineup event! but we care more about maccabi, skip technical games """

        missing_lineup_games = [game for game in self.maccabi_games_stats
                                if not game.technical_result
                                if 11 != len(game.maccabi_team.lineup_players)]

        return self.maccabi_games_stats.create_maccabi_games_stats_with_filtered_games(missing_lineup_games,
                                                                'Games without 11 lineup players')

    def get_dates_with_more_than_one_game(self):
        """
        Each game should be played in a unique date (that how our MaccabiPedia football modeling system works atm)
        """
        games_by_date = defaultdict(list)

        for game in self.maccabi_games_stats:
            games_by_date[game.date.date()].append(game)

        problematic_dates = {date: games for date, games in games_by_date.items() if len(games) > 1}
        return problematic_dates

    def get_lineup_players_with_substitution_in(self):
        """ Players that opened on lineup, should'nt has substitution in event. """

        players_with_games = [(player, game) for game in self.maccabi_games_stats for player in
                              game.maccabi_team.players
                              if player.has_event_type(GameEventTypes.LINE_UP) and player.has_event_type(
                GameEventTypes.SUBSTITUTION_IN)]

        return players_with_games

    def get_games_with_missing_goals_events(self):
        """ Total score should be equals to the total goals event, excluding games that were finished by technical result """

        games = [game for game in self.maccabi_games_stats
                 if (game.maccabi_team.score + game.not_maccabi_team.score != len(
                game.goals())) and not game.technical_result]

        return self.maccabi_games_stats.create_maccabi_games_stats_with_filtered_games(games, 'Games with missing goals events')

    def get_games_with_wrong_goals_team_belonging(self):
        """ Maccabi score in the game should be equal to the maccabi score that written in the last goal event
            We exclude technical games and the games that has some missing goals events which is counter by
            get_games_with_missing_goals_events """

        games_with_wrong_goals_count = self.get_games_with_missing_goals_events()

        def game_has_wrong_goals_belonging(game_to_check: GameData) -> bool:
            if game_to_check.technical_result:
                return False

            if game_to_check in games_with_wrong_goals_count:
                return False

            maccabi_score, not_maccabi_score = 0, 0
            if game_to_check.goals():
                last_goal = game_to_check.goals()[-1]
                maccabi_score, not_maccabi_score = last_goal['maccabi_score'], last_goal['not_maccabi_score']

            return maccabi_score != game_to_check.maccabi_score or not_maccabi_score != not_maccabi_score

        games = list(filter(game_has_wrong_goals_belonging, self.maccabi_games_stats))

        return self.maccabi_games_stats.create_maccabi_games_stats_with_filtered_games(games, 'Games with wrong goals belonging')

    def get_players_with_event_but_without_lineup_or_substitution(self):
        """ Every player that has any event should has atleast lineup or substitution or bench in event """

        players_with_games = [(player, game) for game in self.maccabi_games_stats for player in
                              game.maccabi_team.players
                              if len(player.events) > 0 and  # Got any event but no lineup or subs in
                              not player.has_event_type(GameEventTypes.LINE_UP) and not player.has_event_type(
                GameEventTypes.SUBSTITUTION_IN)
                              and not player.has_event_type(GameEventTypes.BENCHED)]
        return players_with_games

    def get_goals_scored_at_minute_zero(self):
        zero_time = str(timedelta(0))
        all_goals_and_games = list(
            chain.from_iterable([zip(game.goals(), repeat(game)) for game in self.maccabi_games_stats]))
        return list(filter(lambda item: item[0]['time_occur'] == zero_time, all_goals_and_games))

    def get_games_with_incorrect_season(self):
        """ Finds games which their date does not match the seasons (date between seasons). """

        def validate_season(game):
            last_year = _PROLONGED_SEASONS_LAST_YEAR.get(game.season)
            if last_year is None:
                last_year = int(game.season[:2] + game.season[-2:])
                if game.season[-2:] == "00":  # We should add 100 year to the max season in this counting system:
                    last_year += 100
            return int(game.season[:4]) <= game.date.year <= last_year

        games_with_incorrect_season = [(game.season, str(game.date.date()), game) for game in self.maccabi_games_stats
                                       if not validate_season(game)]

        return games_with_incorrect_season

    def get_players_with_unknown_events(self):
        players_with_unknown_events = [(player, game) for game in self.maccabi_games_stats for player in
                                       game.maccabi_team.players if
                                       player.has_event_type(GameEventTypes.UNKNOWN)]
        return players_with_unknown_events

    def get_missing_league_games_fixtures(self):
        """
        For each season get the max fixture number and check whether the len of this season games equal to it
        """
        missing_fixtures_from_all_seasons = []

        seasons = self.maccabi_games_stats.league_games.seasons

        for season in seasons:
            current_season_fixtures = [game.league_fixture for game in season if game.league_fixture]
            if not current_season_fixtures:  # If we are dealing with no league games in this season
                continue

            should_be_fixtures = set(range(1, max(current_season_fixtures) + 1))
            missing_fixtures = should_be_fixtures.difference(current_season_fixtures)

            if missing_fixtures:
                [missing_fixtures_from_all_seasons.append((season[0].season, missing_fixture)) for missing_fixture in
                 missing_fixtures]

        return missing_fixtures_from_all_seasons

    def get_double_league_games_fixtures(self):
        """
        For each season check whether we have double fixtures (numbers)
        """
        fixtures_from_all_seasons = defaultdict(list)

        seasons = self.maccabi_games_stats.league_games.seasons

        for season in seasons:
            if not season:
                continue

            # This season is not empty. Games with no fixture number (most seasons before 1950 carry
            # none on the wiki) are not "the same fixture" as each other, so they are skipped.
            for game in season:
                if game.league_fixture is None:
                    continue
                fixtures_from_all_seasons[f"Season {season[0].season} Fixture {game.league_fixture}"].append(game)

        double_fixtures = [(season_and_fixture, self.maccabi_games_stats.create_maccabi_games_stats_with_filtered_games(games, f'Double fixture: {season_and_fixture}')) for season_and_fixture, games in
                           fixtures_from_all_seasons.items() if
                           len(games) > 1]

        return double_fixtures

    def get_league_games_without_fixture(self):
        """
        League games with no fixture number ("מחזור N"). The double-fixture check skips them,
        so this is where they are reported.
        """
        games = [game for game in self.maccabi_games_stats.league_games if game.league_fixture is None]
        return self.maccabi_games_stats.create_maccabi_games_stats_with_filtered_games(
            games, 'League games without a fixture number')

    def get_games_without_stadium(self):
        """
        Returns the games without defined stadium
        """

        return [game for game in self.maccabi_games_stats.games if not game.stadium]

    def get_games_without_referee(self):
        """
        Returns the games without defined referee
        """

        return [game for game in self.maccabi_games_stats.games if not game.referee]

    def get_players_which_play_more_than_x_years(self, number_of_years: int = 20) -> \
            List[Tuple[str, MaccabiGamesStats]]:
        """
        Returns the players who play more than the given years.
        This may indicate on naming errors
        :return: Player name and his games
        """
        players_who_played_too_much = []
        for player_name in self.maccabi_games_stats.available_players_names:
            player_games = self.maccabi_games_stats.get_games_by_player_name(player_name)
            if player_games[-1].date - player_games[0].date > timedelta(days=365 * number_of_years):
                players_who_played_too_much.append((player_name, player_games))

        players_who_played_too_much.sort(key=lambda item: item[1][-1].date - item[1][0].date)
        return players_who_played_too_much

    def get_players_with_any_event_that_did_not_count_as_played(self) -> List[Tuple[str, GameData]]:
        players_with_events_that_did_not_play = []
        played_player_events = {GameEventTypes.SUBSTITUTION_IN, GameEventTypes.LINE_UP}

        for game in self.maccabi_games_stats:
            for player in game.maccabi_team.players:
                player_events = set([event.event_type for event in player.events])

                # We have special event for benched player, we can't count this event as "any event" in this function
                if GameEventTypes.BENCHED in player_events:
                    continue

                # If player did not played and has any other events besides it
                if not player_events.intersection(played_player_events) and \
                        player_events.difference(played_player_events):
                    players_with_events_that_did_not_play.append((player.name, game))

        return players_with_events_that_did_not_play

    def get_benched_players_that_has_events_without_sub_in(self) -> List[Tuple[str, GameData]]:
        benched_players_with_weird_events = []

        for game in self.maccabi_games_stats:
            for player in game.maccabi_team.players:
                player_events = set([event.event_type for event in player.events])

                if GameEventTypes.BENCHED not in player_events:
                    continue

                # If this player has only bench event it's ok
                if len(player_events) == 1:
                    continue

                if GameEventTypes.SUBSTITUTION_IN in player_events:
                    continue

                # This player has any other event besides sub-in, we must count him as sub-in in order to fix it
                benched_players_with_weird_events.append((player.name, game))

        return benched_players_with_weird_events

    def get_items_category_with_empty_names(self) -> List[str]:
        """
        return the category name that may contain invalid item name (coaches, opponents, players and so on),
        it may happen due to exception while we extract the data from maccabipedia
        """
        bad_items_category = []

        if any(True for name in self.maccabi_games_stats.available_players_names if not name.strip()):
            bad_items_category.append('players_names')
        if any(True for name in self.maccabi_games_stats.available_competitions if not name.strip()):
            bad_items_category.append('competition')
        if any(True for name in self.maccabi_games_stats.available_stadiums if not name.strip()):
            bad_items_category.append('stadiums')
        if any(True for name in self.maccabi_games_stats.available_coaches if not name.strip()):
            bad_items_category.append('coaches')
        if any(True for name in self.maccabi_games_stats.available_referees if not name.strip()):
            bad_items_category.append('referees')
        if any(True for name in self.maccabi_games_stats.available_opponents if not name.strip()):
            bad_items_category.append('opponents')

        return bad_items_category

    def get_players_with_two_yellows_without_red_card_in_the_same_game(self) -> List[Tuple[str, GameData]]:
        players_and_games = []

        for game in self.maccabi_games_stats:
            # YELLOW_CARD event indicates a yellow which is not first/yellow (which is part of red card)
            players_with_two_yellows = [player_name for player_name, count in
                                        game.maccabi_team.yellow_carded_players_with_amount.items() if count > 1]
            for player_name in players_with_two_yellows:
                players_and_games.append((player_name, game))

        return players_and_games

    def get_players_with_substitution_out_but_never_played(self) -> List[Tuple[str, GameData]]:
        """
        Players that have a substitution-out event but never appeared in the lineup or came on as a sub.
        This indicates a data entry error on the wiki.
        """
        players_and_games = []
        for game in self.maccabi_games_stats:
            for player in game.maccabi_team.players:
                if player.has_event_type(GameEventTypes.SUBSTITUTION_OUT) and not player.played_in_game:
                    players_and_games.append((player.name, game))
        return players_and_games

    def get_games_with_same_player_on_both_teams(self) -> List[Tuple[str, GameData]]:
        """
        Games where the same player name appears on both Maccabi and the opponent team.
        Usually indicates a naming collision or a data entry error.
        """
        results = []
        for game in self.maccabi_games_stats:
            maccabi_names = {p.name for p in game.maccabi_team.players}
            opponent_names = {p.name for p in game.not_maccabi_team.players}
            for name in maccabi_names & opponent_names:
                results.append((name, game))
        return results

    def get_players_with_duplicate_events(self) -> List[Tuple[str, GameData]]:
        """
        Players that have two or more identical events (same type + same minute) in the same game.
        Indicates a duplicate entry on the wiki.
        """
        results = []
        for game in self.maccabi_games_stats:
            for player in game.maccabi_team.players:
                seen = set()
                for event in player.events:
                    key = (event.event_type, event.time_occur)
                    if key in seen:
                        results.append((player.name, game))
                        break
                    seen.add(key)
        return results

    def get_all_errors_numbers(self):
        """ Iterate over all this class functions without this one, and summarize the results. """
        errors_finders = [func for func in dir(self) if
                          callable(getattr(self, func)) and func != "get_all_errors_numbers" and not func.startswith(
                              "_")]

        for func_name in errors_finders:
            error_finder_func = getattr(self, func_name)
            logger.info("{func_name}: returned {count} items".format(func_name=func_name,
                                                                     count=len(error_finder_func())))

    def __str__(self) -> str:
        return f'ErrorsFinder: [{self.maccabi_games_stats}]'

    def __repr__(self) -> str:
        return str(self)
