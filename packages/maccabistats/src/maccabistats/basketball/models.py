"""A basketball game as maccabistats reads it from MaccabiPedia.

These are read models. A value the wiki does not have stays ``None`` and never becomes 0 or "",
so "nobody filled it in" is never mistaken for "zero points".
"""
from dataclasses import dataclass
from datetime import date

HOME = "בית"
AWAY = "חוץ"
NEUTRAL = "נייטרלי"


@dataclass(frozen=True)
class BasketballCompetitionFlags:
    """The competition's row in the wiki's catalog (Basketball_Competitions)."""
    current_name: str | None
    is_league: bool
    is_trophy: bool
    is_international: bool
    is_official: bool


@dataclass(frozen=True)
class BasketballGameVideos:
    full_game: str | None = None
    full_game_2: str | None = None
    highlights: str | None = None
    highlights_2: str | None = None
    fans: str | None = None
    fans_2: str | None = None

    @property
    def all(self) -> tuple[str, ...]:
        candidates = (self.full_game, self.full_game_2, self.highlights, self.highlights_2, self.fans, self.fans_2)
        return tuple(video for video in candidates if video)


@dataclass(frozen=True)
class BasketballTeamInGame:
    """One side of one game. A period nobody filled in is ``None``, not 0."""
    name: str | None
    coach: str | None
    score: int | None
    quarters: tuple[int | None, int | None, int | None, int | None]
    halves: tuple[int | None, int | None]
    overtimes: tuple[int | None, int | None, int | None, int | None]

    @property
    def overtime_points(self) -> int:
        return sum(points or 0 for points in self.overtimes)


@dataclass(frozen=True)
class BasketballGameData:
    page_name: str
    date: date | None
    hour: str | None
    season: str | None
    competition: str | None
    leg: str | None
    opponent: str | None
    home_away: str | None
    stadium: str | None
    # None when the competition has no row in the wiki's catalog
    competition_flags: BasketballCompetitionFlags | None
    # As stored: None, 1 or 2
    technical: int | None
    # As stored: 1 Maccabi won, 2 tie, 3 Maccabi lost. Wins and losses below are judged from the score
    result_opt: int | None
    main_referee: str | None
    assistant_referees: tuple[str, ...]
    crowd: int | None
    has_article: bool
    videos: BasketballGameVideos
    maccabi: BasketballTeamInGame
    opponent_team: BasketballTeamInGame

    def __str__(self) -> str:
        return self.page_name

    @property
    def is_home(self) -> bool:
        return self.home_away == HOME

    @property
    def is_away(self) -> bool:
        return self.home_away == AWAY

    @property
    def is_neutral(self) -> bool:
        return self.home_away == NEUTRAL

    @property
    def is_technical(self) -> bool:
        return bool(self.technical)

    @property
    def has_result(self) -> bool:
        """A game page with no result typed in is stored as 0:0, so 0:0 is not a result."""
        scores = (self.maccabi.score, self.opponent_team.score)
        return None not in scores and scores != (0, 0)

    @property
    def score_diff(self) -> int | None:
        """Maccabi's points minus the opponent's; None when the game has no result."""
        if not self.has_result:
            return None
        return self.maccabi.score - self.opponent_team.score

    @property
    def is_maccabi_win(self) -> bool:
        return self.has_result and self.score_diff > 0

    @property
    def is_maccabi_loss(self) -> bool:
        return self.has_result and self.score_diff < 0

    @property
    def overtimes_played(self) -> int:
        """Counted from the overtime points; the wiki's IsOvertime column is never filled."""
        return sum(1 for maccabi_points, opponent_points in zip(self.maccabi.overtimes, self.opponent_team.overtimes)
                   if (maccabi_points or 0) + (opponent_points or 0) > 0)

    @property
    def is_overtime(self) -> bool:
        return self.overtimes_played > 0
