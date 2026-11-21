"""The basketball games collection and its stats, the way MaccabiGamesStats holds the football games.

Filters return a new BasketballGamesStats, so they chain: ``games.league_games.home_games.maccabi_wins``.
"""
from __future__ import annotations

import datetime
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, Iterator, List, NamedTuple, Optional, Tuple, Union

from dateutil.parser import parse as datetime_parser

from maccabistats.basketball.models import PLAYER_STATS, BasketballGameData, BasketballPlayerInGame
from maccabistats.version import version

DateLike = Union[datetime.datetime, datetime.date, str]


def _as_date(value: DateLike) -> datetime.date:
    # Text is read the way the football filters read it
    if isinstance(value, str):
        value = datetime_parser(value)
    if isinstance(value, datetime.datetime):
        return value.date()
    return value


def _wins_fraction(wins_count: int, losses_count: int) -> float:
    decided = wins_count + losses_count
    return round(wins_count / decided, 3) if decided else 0.0


@dataclass(frozen=True)
class BasketballRecord:
    """Maccabi's record over a group of games: against one opponent, under one coach, in one season."""
    name: str
    games_count: int
    wins_count: int
    losses_count: int
    points_for_maccabi: int
    points_against_maccabi: int

    @property
    def wins_percentage(self) -> float:
        """A fraction between 0 and 1, like football's, out of the games that have a winner."""
        return _wins_fraction(self.wins_count, self.losses_count)


class BasketballPlayerTotal(NamedTuple):
    """
    A player's total of one stat. games_with_data is the number of his games in which that stat
    is known for him: his side's box score recorded it at all, and his own line has a value.
    Old box scores have points and little else, so a total over 10 games with data out of 300
    played is not a career total. A stat nobody on the side had in a game (a modern game with no
    blocks) reads as not recorded, so games_with_data can be a little low for rare stats.
    """
    name: str
    value: int
    games_with_data: int


class BasketballResultsStats:
    def __init__(self, basketball_games_stats: BasketballGamesStats):
        self.games = basketball_games_stats.games
        # Points are counted from games played on the court: an awarded game's score fields hold
        # the official 20:0 (or 2:0), not points anyone scored
        self._played_games = [game for game in self.games if game.has_score and not game.is_technical]

    @property
    def total_games_count(self) -> int:
        return len(self.games)

    @property
    def wins_count(self) -> int:
        return sum(game.is_maccabi_win for game in self.games)

    @property
    def losses_count(self) -> int:
        return sum(game.is_maccabi_loss for game in self.games)

    @property
    def wins_percentage(self) -> float:
        """
        A fraction between 0 and 1, like football's. Out of the games that have a winner, so a game
        with no result typed in does not lower it; 0.0 when there is no such game.
        """
        return _wins_fraction(self.wins_count, self.losses_count)

    @property
    def losses_percentage(self) -> float:
        return _wins_fraction(self.losses_count, self.wins_count)

    @property
    def total_points_for_maccabi(self) -> int:
        """Awarded (technical) games are not counted in any of the points numbers."""
        return sum(game.maccabi.score for game in self._played_games)

    @property
    def total_points_against_maccabi(self) -> int:
        return sum(game.opponent_team.score for game in self._played_games)

    @property
    def total_points_diff_for_maccabi(self) -> int:
        return self.total_points_for_maccabi - self.total_points_against_maccabi

    def biggest_wins(self, limit: int = 10) -> List[BasketballGameData]:
        wins = [game for game in self._played_games if game.is_maccabi_win]
        return sorted(wins, key=lambda game: game.score_diff, reverse=True)[:limit]

    def biggest_losses(self, limit: int = 10) -> List[BasketballGameData]:
        losses = [game for game in self._played_games if game.is_maccabi_loss]
        return sorted(losses, key=lambda game: game.score_diff)[:limit]

    def highest_scoring_games(self, limit: int = 10) -> List[BasketballGameData]:
        """By both teams' points together."""
        return sorted(self._played_games, key=lambda game: game.maccabi.score + game.opponent_team.score, reverse=True)[:limit]

    def most_points_for_maccabi_games(self, limit: int = 10) -> List[BasketballGameData]:
        return sorted(self._played_games, key=lambda game: game.maccabi.score, reverse=True)[:limit]


class BasketballStreaksStats:
    """
    A streak is a run of consecutive games of this collection, in date order, that all meet the
    condition. Only games with a result and a date take part: a game with no result neither breaks
    a streak nor adds to it, and a game with no date has no place in the order. So the streak
    follows the filter - ``league_games.streaks`` ignores the cup games played in between. The
    current streak is the one that ends at the last game.
    """

    def __init__(self, basketball_games_stats: BasketballGamesStats):
        self._stats = basketball_games_stats
        self._games = [game for game in basketball_games_stats.games if game.has_result and game.date is not None]

    def _longest(self, condition: Callable[[BasketballGameData], bool]) -> BasketballGamesStats:
        longest, current = [], []
        for game in self._games:
            current = current + [game] if condition(game) else []
            # Strictly longer: of equal streaks the earliest is returned
            if len(current) > len(longest):
                longest = current
        return self._stats._filtered(longest, "Longest streak")

    def _current(self, condition: Callable[[BasketballGameData], bool]) -> BasketballGamesStats:
        streak = []
        for game in reversed(self._games):
            if not condition(game):
                break
            streak.insert(0, game)
        return self._stats._filtered(streak, "Current streak")

    def get_longest_wins_streak_games(self) -> BasketballGamesStats:
        return self._longest(lambda game: game.is_maccabi_win)

    def get_longest_losses_streak_games(self) -> BasketballGamesStats:
        return self._longest(lambda game: game.is_maccabi_loss)

    def get_current_wins_streak(self) -> BasketballGamesStats:
        return self._current(lambda game: game.is_maccabi_win)

    def get_current_losses_streak(self) -> BasketballGamesStats:
        return self._current(lambda game: game.is_maccabi_loss)


class BasketballPlayersStats:
    """Maccabi's players over these games, from the box scores. The opponents' players are not counted."""

    def __init__(self, basketball_games_stats: BasketballGamesStats):
        self.games = basketball_games_stats.games

    def _count(self, condition: Callable[[BasketballPlayerInGame], bool]) -> List[Tuple[str, int]]:
        games_by_player: Dict[str, int] = defaultdict(int)
        for game in self.games:
            # A set, so a player the page lists twice counts the game once
            for name in {player.name for player in game.maccabi.players if condition(player)}:
                games_by_player[name] += 1
        return sorted(games_by_player.items(), key=lambda item: item[1], reverse=True)

    @property
    def most_played(self) -> List[Tuple[str, int]]:
        """(player, games he played in), most first."""
        return self._count(lambda player: player.is_played)

    @property
    def most_starting_five(self) -> List[Tuple[str, int]]:
        return self._count(lambda player: player.is_starting_five)

    @property
    def most_captains(self) -> List[Tuple[str, int]]:
        return self._count(lambda player: player.is_captain)

    def get_players_total(self, stat: str) -> List[BasketballPlayerTotal]:
        """
        Every player's total of one stat (see models.PLAYER_STATS), highest first, over the games
        in which that stat is known for him (see BasketballPlayerTotal).
        """
        if stat not in PLAYER_STATS:
            raise ValueError(f"Unknown player stat {stat!r}, expected one of {PLAYER_STATS}")

        values: Dict[str, int] = defaultdict(int)
        games_with_data: Dict[str, int] = defaultdict(int)
        for game in self.games:
            if not game.maccabi.has_recorded(stat):
                continue
            # A player with an empty value is not known to have 0: the game is not counted for him.
            # A page that lists one player twice splits his line, so both lines are summed
            lines = [player for player in game.maccabi.played_players if getattr(player, stat) is not None]
            for name in {player.name for player in lines}:
                games_with_data[name] += 1
            for player in lines:
                values[player.name] += getattr(player, stat)

        totals = [BasketballPlayerTotal(name, values[name], games) for name, games in games_with_data.items()]
        return sorted(totals, key=lambda total: total.value, reverse=True)

    @property
    def best_scorers(self) -> List[BasketballPlayerTotal]:
        return self.get_players_total("points")

    @property
    def best_rebounders(self) -> List[BasketballPlayerTotal]:
        return self.get_players_total("rebounds")

    @property
    def best_assisters(self) -> List[BasketballPlayerTotal]:
        return self.get_players_total("assists")

    def get_best_single_games(self, stat: str, limit: int = 10) -> List[Tuple[str, int, BasketballGameData]]:
        """(player, his number of that stat, the game), the highest single games first."""
        if stat not in PLAYER_STATS:
            raise ValueError(f"Unknown player stat {stat!r}, expected one of {PLAYER_STATS}")

        single_games = [(player.name, getattr(player, stat), game)
                        for game in self.games for player in game.maccabi.played_players if getattr(player, stat)]
        return sorted(single_games, key=lambda single_game: single_game[1], reverse=True)[:limit]


class BasketballGamesStats:
    _DEFAULT_DESCRIPTION = "All games"

    def __init__(self, games: List[BasketballGameData],
                 player_rows_without_game: Optional[List[Tuple[str, int, BasketballPlayerInGame]]] = None,
                 description: Optional[str] = None):
        """
        :param player_rows_without_game: Box-score rows that fit no game, as (page name, the row's
                                         Team column, the player). Kept for the errors finder.
        """
        # Games with no date go last
        self.games = sorted(games, key=lambda game: (game.date or datetime.date.max, game.page_name))
        self.player_rows_without_game = list(player_rows_without_game or [])
        self.description = description or self._DEFAULT_DESCRIPTION
        self.version = version

    def _filtered(self, games: List[BasketballGameData], description: str) -> BasketballGamesStats:
        if self.description != self._DEFAULT_DESCRIPTION:
            description = f"{self.description} -> {description}"
        # The rows of no game belong to no filter either; they are passed on as they are, so the
        # errors finder reports them from any collection
        return BasketballGamesStats(games, self.player_rows_without_game, description)

    def _filter(self, condition: Callable[[BasketballGameData], bool], description: str) -> BasketballGamesStats:
        return self._filtered([game for game in self.games if condition(game)], description)

    # region stats

    @property
    def results(self) -> BasketballResultsStats:
        return BasketballResultsStats(self)

    @property
    def streaks(self) -> BasketballStreaksStats:
        return BasketballStreaksStats(self)

    @property
    def players(self) -> BasketballPlayersStats:
        return BasketballPlayersStats(self)

    def _records_by(self, key: Callable[[BasketballGameData], Optional[str]]) -> List[BasketballRecord]:
        games_by_key: Dict[str, List[BasketballGameData]] = defaultdict(list)
        for game in self.games:
            if key(game) is not None:
                games_by_key[key(game)].append(game)

        records = []
        for name, games in games_by_key.items():
            results = BasketballResultsStats(self._filtered(games, name))
            records.append(BasketballRecord(name=name, games_count=len(games), wins_count=results.wins_count,
                                            losses_count=results.losses_count,
                                            points_for_maccabi=results.total_points_for_maccabi,
                                            points_against_maccabi=results.total_points_against_maccabi))
        return records

    @property
    def opponents(self) -> List[BasketballRecord]:
        """Maccabi's record against each opponent, by the name the game pages give it, most games first."""
        return sorted(self._records_by(lambda game: game.opponent), key=lambda record: record.games_count, reverse=True)

    @property
    def coaches(self) -> List[BasketballRecord]:
        """Maccabi's record under each of its coaches, most games first."""
        return sorted(self._records_by(lambda game: game.maccabi.coach), key=lambda record: record.games_count, reverse=True)

    @property
    def seasons(self) -> List[BasketballRecord]:
        """Maccabi's record in each season, earliest first."""
        return sorted(self._records_by(lambda game: game.season), key=lambda record: record.name)

    # endregion

    # region home_away

    @property
    def home_games(self) -> BasketballGamesStats:
        return self._filter(lambda game: game.is_home, "Home games")

    @property
    def away_games(self) -> BasketballGamesStats:
        return self._filter(lambda game: game.is_away, "Away games")

    @property
    def neutral_games(self) -> BasketballGamesStats:
        return self._filter(lambda game: game.is_neutral, "Neutral games")

    # endregion

    # region competitions filters, by the competition's flags in the wiki's catalog

    def _filter_by_flag(self, flag: str, description: str) -> BasketballGamesStats:
        return self._filter(lambda game: game.competition_flags is not None and getattr(game.competition_flags, flag),
                            description)

    @property
    def league_games(self) -> BasketballGamesStats:
        return self._filter_by_flag("is_league", "League games")

    @property
    def trophy_games(self) -> BasketballGamesStats:
        return self._filter_by_flag("is_trophy", "Trophy games")

    @property
    def international_games(self) -> BasketballGamesStats:
        return self._filter_by_flag("is_international", "International games")

    @property
    def official_games(self) -> BasketballGamesStats:
        return self._filter_by_flag("is_official", "Official games")

    @property
    def non_official_games(self) -> BasketballGamesStats:
        """Games of a competition the catalog marks as not official. A competition with no catalog row is in neither."""
        return self._filter(lambda game: game.competition_flags is not None and not game.competition_flags.is_official,
                            "Non-official games")

    # endregion

    # region results

    @property
    def maccabi_wins(self) -> BasketballGamesStats:
        return self._filter(lambda game: game.is_maccabi_win, "Maccabi wins")

    @property
    def maccabi_losses(self) -> BasketballGamesStats:
        return self._filter(lambda game: game.is_maccabi_loss, "Maccabi losses")

    @property
    def games_with_result(self) -> BasketballGamesStats:
        return self._filter(lambda game: game.has_result, "Games with a result")

    @property
    def technical_result_games(self) -> BasketballGamesStats:
        return self._filter(lambda game: game.is_technical, "Technical games")

    @property
    def overtime_games(self) -> BasketballGamesStats:
        return self._filter(lambda game: game.is_overtime, "Overtime games")

    # endregion

    # region date based. A game with no date is in none of them

    def played_before(self, date: DateLike) -> BasketballGamesStats:
        """:param date: A date or text of one (2006-02-02). Games on that day are included."""
        day = _as_date(date)
        return self._filter(lambda game: game.date is not None and game.date <= day, f"Played before: {day}")

    def played_after(self, date: DateLike) -> BasketballGamesStats:
        """:param date: A date or text of one (2006-02-02). Games on that day are included."""
        day = _as_date(date)
        return self._filter(lambda game: game.date is not None and game.date >= day, f"Played after: {day}")

    def played_at(self, date: DateLike) -> BasketballGamesStats:
        day = _as_date(date)
        return self._filter(lambda game: game.date == day, f"Played at: {day}")

    @property
    def first_game_date(self) -> Optional[str]:
        """Of the games that have a date, as DD-MM-YYYY like football's; None when there is none."""
        dates = [game.date for game in self.games if game.date is not None]
        return dates[0].strftime("%d-%m-%Y") if dates else None

    @property
    def last_game_date(self) -> Optional[str]:
        dates = [game.date for game in self.games if game.date is not None]
        return dates[-1].strftime("%d-%m-%Y") if dates else None

    # endregion

    # region free-style filters

    def get_games_by_competition(self, competition_types: Union[List[str], str]) -> BasketballGamesStats:
        """By the competition's name as the game pages write it (the catalog's OriginalName)."""
        if isinstance(competition_types, str):
            competition_types = [competition_types]
        return self._filter(lambda game: game.competition in competition_types, f"Competitions: {competition_types}")

    def get_games_by_season(self, season: str) -> BasketballGamesStats:
        return self._filter(lambda game: game.season == season, f"Season: {season}")

    def get_games_by_stadium(self, stadium_name: str) -> BasketballGamesStats:
        return self._filter(lambda game: game.stadium == stadium_name, f"Stadium: {stadium_name}")

    def get_games_against_team(self, team_name: str) -> BasketballGamesStats:
        """By the opponent's name as the game pages give it; a club's older names are other opponents."""
        return self._filter(lambda game: game.opponent == team_name, f"Against team: {team_name}")

    def get_games_by_coach(self, coach_name: str) -> BasketballGamesStats:
        return self._filter(lambda game: game.maccabi.coach == coach_name, f"Coach: {coach_name}")

    def get_games_by_referee(self, referee_name: str) -> BasketballGamesStats:
        return self._filter(lambda game: referee_name == game.main_referee or referee_name in game.assistant_referees,
                            f"Referee: {referee_name}")

    def get_games_by_player_name(self, player_name: str) -> BasketballGamesStats:
        """Games whose Maccabi box score lists the player, whether he played or not."""
        return self._filter(lambda game: any(player.name == player_name for player in game.maccabi.players),
                            f"Player: {player_name}")

    def get_games_by_played_player_name(self, player_name: str) -> BasketballGamesStats:
        return self._filter(lambda game: any(player.name == player_name for player in game.maccabi.played_players),
                            f"Played player: {player_name}")

    # endregion

    # region available values

    def _available(self, value: Callable[[BasketballGameData], Optional[str]]) -> List[str]:
        return sorted({value(game) for game in self.games if value(game) is not None})

    @property
    def available_competitions(self) -> List[str]:
        return self._available(lambda game: game.competition)

    @property
    def available_opponents(self) -> List[str]:
        return self._available(lambda game: game.opponent)

    @property
    def available_seasons(self) -> List[str]:
        return self._available(lambda game: game.season)

    @property
    def available_coaches(self) -> List[str]:
        return self._available(lambda game: game.maccabi.coach)

    @property
    def available_stadiums(self) -> List[str]:
        return self._available(lambda game: game.stadium)

    @property
    def available_referees(self) -> List[str]:
        return sorted({referee for game in self.games
                       for referee in (game.main_referee, *game.assistant_referees) if referee is not None})

    @property
    def available_players_names(self) -> List[str]:
        return sorted({player.name for game in self.games for player in game.maccabi.players})

    # endregion

    def __len__(self) -> int:
        return len(self.games)

    def __iter__(self) -> Iterator[BasketballGameData]:
        return iter(self.games)

    def __getitem__(self, item):
        return self.games[item]

    def __repr__(self) -> str:
        if self.first_game_date is None:
            return f"{self.description} | {len(self)} basketball games"
        return f"{self.description} | {len(self)} basketball games | (from {self.first_game_date} to {self.last_game_date})"
