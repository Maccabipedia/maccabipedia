"""The basketball games collection, the way MaccabiGamesStats holds the football games."""
from datetime import date
from typing import Iterator, List, Optional, Tuple

from maccabistats.basketball.models import BasketballGameData, BasketballPlayerInGame
from maccabistats.version import version


class BasketballGamesStats:
    def __init__(self, games: List[BasketballGameData],
                 player_rows_without_game: Optional[List[Tuple[str, int, BasketballPlayerInGame]]] = None):
        """
        :param player_rows_without_game: Box-score rows that fit no game, as (page name, the row's
                                         Team column, the player). Kept for the errors finder.
        """
        # Games with no date go last
        self.games = sorted(games, key=lambda game: (game.date or date.max, game.page_name))
        self.player_rows_without_game = list(player_rows_without_game or [])
        self.version = version

    def __len__(self) -> int:
        return len(self.games)

    def __iter__(self) -> Iterator[BasketballGameData]:
        return iter(self.games)

    def __getitem__(self, item):
        return self.games[item]

    def __repr__(self) -> str:
        if not self.games:
            return "No basketball games"
        return f"{len(self)} basketball games, from {self.games[0].date} to {self.games[-1].date}"
