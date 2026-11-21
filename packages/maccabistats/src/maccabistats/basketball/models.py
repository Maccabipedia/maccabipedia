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


# The numbers of a player's line that a box score may or may not have recorded
PLAYER_STATS = ("minutes", "points", "two_points_scored", "two_points_attempts", "three_points_scored",
                "three_points_attempts", "free_throws_scored", "free_throws_attempts", "rebounds",
                "offensive_rebounds", "defensive_rebounds", "assists", "steals", "blocks", "turnovers",
                "personal_fouls", "technical_fouls")


@dataclass(frozen=True)
class BasketballPlayerInGame:
    """One player's line in one game's box score.

    Old box scores recorded little more than the points, and the wiki stores the numbers nobody
    recorded as 0 as often as it leaves them empty. So a 0 here does not mean the player had none:
    ask the team's ``has_recorded`` before counting a stat.
    """
    name: str
    number: int | None
    is_captain: bool
    is_starting_five: bool
    is_played: bool
    minutes: int | None
    points: int | None
    # The wiki's FieldGoals columns are the two-point shots: points = 2 * two + 3 * three + free throws
    two_points_scored: int | None
    two_points_attempts: int | None
    three_points_scored: int | None
    three_points_attempts: int | None
    free_throws_scored: int | None
    free_throws_attempts: int | None
    rebounds: int | None
    offensive_rebounds: int | None
    defensive_rebounds: int | None
    assists: int | None
    steals: int | None
    blocks: int | None
    turnovers: int | None
    personal_fouls: int | None
    technical_fouls: int | None

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class BasketballTeamInGame:
    """One side of one game. A period nobody filled in is ``None``, not 0."""
    name: str | None
    coach: str | None
    score: int | None
    quarters: tuple[int | None, int | None, int | None, int | None]
    halves: tuple[int | None, int | None]
    overtimes: tuple[int | None, int | None, int | None, int | None]
    # The box score, in the page's order. Empty when the game has none. A player the page lists
    # twice is here twice.
    players: tuple[BasketballPlayerInGame, ...] = ()

    @property
    def overtime_points(self) -> int:
        return sum(points or 0 for points in self.overtimes)

    @property
    def played_players(self) -> tuple[BasketballPlayerInGame, ...]:
        return tuple(player for player in self.players if player.is_played)

    def has_recorded(self, stat: str) -> bool:
        """Whether this side's box score recorded the stat at all: some player has more than 0 of it.

        Unrecorded stats are stored as 0 or left empty, so "nobody has any" is read as "not recorded".
        """
        if stat not in PLAYER_STATS:
            raise ValueError(f"Unknown player stat {stat!r}, expected one of {PLAYER_STATS}")
        return any((getattr(player, stat) or 0) > 0 for player in self.players)


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
