"""The basketball games collection and its stats, the way MaccabiGamesStats holds the football games.

Filters return a new BasketballGamesStats, so they chain: ``games.league_games.home_games.maccabi_wins``.
"""
from __future__ import annotations

import datetime
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, Iterator, List, Optional, Tuple, Union

from maccabistats.basketball.models import PLAYER_STATS, BasketballGameData, BasketballPlayerInGame
from maccabistats.version import version

DateLike = Union[datetime.date, str]


def _as_date(value: DateLike) -> datetime.date:
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(value)


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
        decided = self.wins_count + self.losses_count
        return round(self.wins_count * 100 / decided, 3) if decided else 0.0


@dataclass(frozen=True)
class BasketballPlayerTotal:
    """
    A player's total of one stat. games_with_data is the number of his games whose box score
    recorded that stat at all - old box scores have points and little else, so a total over
    10 games with data out of 300 played is not a career total.
    """
    name: str
    value: int
    games_with_data: int


class BasketballResultsStats:
    def __init__(self, basketball_games_stats: BasketballGamesStats):
        self.games = basketball_games_stats.games
        self._with_score = [game for game in self.games if game.has_score]

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
        """Out of the games that have a winner."""
        decided = self.wins_count + self.losses_count
        return round(self.wins_count * 100 / decided, 3) if decided else 0.0

    @property
    def losses_percentage(self) -> float:
        decided = self.wins_count + self.losses_count
        return round(self.losses_count * 100 / decided, 3) if decided else 0.0

    @property
    def total_points_for_maccabi(self) -> int:
        return sum(game.maccabi.score for game in self._with_score)

    @property
    def total_points_against_maccabi(self) -> int:
        return sum(game.opponent_team.score for game in self._with_score)

    @property
    def total_points_diff_for_maccabi(self) -> int:
        return self.total_points_for_maccabi - self.total_points_against_maccabi

    def _played(self) -> List[BasketballGameData]:
        # An awarded game's score is the official 20:0 (or 2:0), not a score from the court
        return [game for game in self._with_score if not game.is_technical]

    def biggest_wins(self, limit: int = 10) -> List[BasketballGameData]:
        wins = [game for game in self._played() if game.is_maccabi_win]
        return sorted(wins, key=lambda game: game.score_diff, reverse=True)[:limit]

    def biggest_losses(self, limit: int = 10) -> List[BasketballGameData]:
        losses = [game for game in self._played() if game.is_maccabi_loss]
        return sorted(losses, key=lambda game: game.score_diff)[:limit]

    def highest_scoring_games(self, limit: int = 10) -> List[BasketballGameData]:
        """By both teams' points together."""
        return sorted(self._played(), key=lambda game: game.maccabi.score + game.opponent_team.score, reverse=True)[:limit]

    def most_points_for_maccabi_games(self, limit: int = 10) -> List[BasketballGameData]:
        return sorted(self._played(), key=lambda game: game.maccabi.score, reverse=True)[:limit]


class BasketballStreaksStats:
    """
    A streak is a run of consecutive games of this collection, in date order, that all meet the
    condition. Only games with a result take part: a game with no result neither breaks a streak
    nor adds to it. So the streak follows the filter - ``league_games.streaks`` ignores the cup
    games played in between. The current streak is the one that ends at the last game.
    """

    def __init__(self, basketball_games_stats: BasketballGamesStats):
        self._stats = basketball_games_stats
        self._games = [game for game in basketball_games_stats.games if game.has_result]

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
    def most_captain(self) -> List[Tuple[str, int]]:
        return self._count(lambda player: player.is_captain)

    def get_players_total(self, stat: str) -> List[BasketballPlayerTotal]:
        """
        Every player's total of one stat (see models.PLAYER_STATS), highest first, over the games
        whose box score recorded that stat for Maccabi.
        """
        if stat not in PLAYER_STATS:
            raise ValueError(f"Unknown player stat {stat!r}, expected one of {PLAYER_STATS}")

        values: Dict[str, int] = defaultdict(int)
        games_with_data: Dict[str, int] = defaultdict(int)
        for game in self.games:
            if not game.maccabi.has_recorded(stat):
                continue
            for name in {player.name for player in game.maccabi.played_players}:
                games_with_data[name] += 1
            for player in game.maccabi.played_players:
                values[player.name] += getattr(player, stat) or 0

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
        if self.description == self._DEFAULT_DESCRIPTION:
            return BasketballGamesStats(games, description=description)
        return BasketballGamesStats(games, description=f"{self.description} -> {description}")

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

        return [BasketballRecord(name=name, games_count=len(games),
                                 wins_count=sum(game.is_maccabi_win for game in games),
                                 losses_count=sum(game.is_maccabi_loss for game in games),
                                 points_for_maccabi=sum(game.maccabi.score for game in games if game.has_score),
                                 points_against_maccabi=sum(game.opponent_team.score for game in games if game.has_score))
                for name, games in games_by_key.items()]

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
        """:param date: A date, or its ISO text (2006-02-02). Games on that day are not included."""
        day = _as_date(date)
        return self._filter(lambda game: game.date is not None and game.date < day, f"Played before: {day}")

    def played_after(self, date: DateLike) -> BasketballGamesStats:
        """:param date: A date, or its ISO text (2006-02-02). Games on that day are not included."""
        day = _as_date(date)
        return self._filter(lambda game: game.date is not None and game.date > day, f"Played after: {day}")

    def played_at(self, date: DateLike) -> BasketballGamesStats:
        day = _as_date(date)
        return self._filter(lambda game: game.date == day, f"Played at: {day}")

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
        if not self.games:
            return f"{self.description}: no basketball games"
        return f"{self.description}: {len(self)} basketball games, from {self.games[0].date} to {self.games[-1].date}"
