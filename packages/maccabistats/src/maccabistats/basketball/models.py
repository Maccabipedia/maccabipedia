"""A basketball game as maccabistats reads it from MaccabiPedia.

These are read models. A value the wiki does not have stays ``None`` and never becomes 0 or "",
so "nobody filled it in" is never mistaken for "zero points".
"""
from dataclasses import dataclass
from datetime import date

HOME = "בית"
AWAY = "חוץ"
NEUTRAL = "נייטרלי"

MACCABI_NAME = "מכבי תל אביב"

TECHNICAL_WIN = 1
TECHNICAL_LOSS = 2


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
    # As stored: None, 1 (awarded to Maccabi) or 2 (awarded to the opponent)
    technical: int | None
    # As stored: 1 Maccabi won, 2 tie, 3 Maccabi lost. Not used for wins and losses below
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
        return self.technical in (TECHNICAL_WIN, TECHNICAL_LOSS)

    @property
    def has_score(self) -> bool:
        """A game page with no result typed in is stored as 0:0, so 0:0 is not a score."""
        scores = (self.maccabi.score, self.opponent_team.score)
        return None not in scores and scores != (0, 0)

    @property
    def has_result(self) -> bool:
        """An awarded (technical) game has a result whatever its score fields hold."""
        return self.is_technical or self.has_score

    @property
    def score_diff(self) -> int | None:
        """Maccabi's points minus the opponent's; None when no score was typed in."""
        if not self.has_score:
            return None
        return self.maccabi.score - self.opponent_team.score

    @property
    def is_maccabi_win(self) -> bool:
        """As on the wiki: in an awarded game the technical flag alone decides, otherwise the score."""
        if self.is_technical:
            return self.technical == TECHNICAL_WIN
        return self.has_score and self.score_diff > 0

    @property
    def is_maccabi_loss(self) -> bool:
        if self.is_technical:
            return self.technical == TECHNICAL_LOSS
        return self.has_score and self.score_diff < 0

    @property
    def overtimes_played(self) -> int:
        """Counted from the overtime points; the wiki's IsOvertime column is never filled."""
        return sum(1 for maccabi_points, opponent_points in zip(self.maccabi.overtimes, self.opponent_team.overtimes)
                   if (maccabi_points or 0) + (opponent_points or 0) > 0)

    @property
    def is_overtime(self) -> bool:
        return self.overtimes_played > 0
