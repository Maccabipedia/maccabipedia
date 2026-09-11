"""Score how sure we are of a proposed match, from 1 to 10.

The point of the score is review order: a human should be able to trust the top of the
list and spend their attention on the bottom of it. So the score is built only from
evidence that can be checked, and the heaviest weight goes to the one piece of evidence
the matcher does NOT read from the video title — when the video was uploaded.

    10  unique score in the season, opponent recognised outright, uploaded within days
     9  the same, but the upload came weeks or months later
     7  the same, but the video is an archive upload with no usable date
     1  the video was uploaded BEFORE the game: the pairing cannot be right

Everything else sits in between, losing a point per piece of missing evidence.
"""
from dataclasses import dataclass

from collections import defaultdict

from maccabipediabot.basketball.videos.aliases import normalize_team_name, resolve_opponent
from maccabipediabot.basketball.videos.cargo import GameRow
from maccabipediabot.basketball.videos.dates import days_between_game_and_upload
from maccabipediabot.basketball.videos.matcher import Bucket, VideoMatch

MIN_SCORE = 1
MAX_SCORE = 10

_BASE_SCORE = 7
_CONFIRM_WINDOW_DAYS = 4
_SAME_SEASON_DAYS = 300


@dataclass(frozen=True)
class Evidence:
    """What, besides the date, supports this match."""
    # Only one game that season ended with this score, so the opponent was not needed
    # to choose between candidates.
    score_unique_in_season: bool
    # The opponent name was resolved through the translations map rather than assumed
    # to be already-correct Hebrew.
    opponent_recognised: bool
    # The resolved name equals the page's opponent, rather than merely containing it.
    opponent_exact: bool
    # The title said what kind of video this is, instead of it being read off the length.
    kind_stated: bool


def date_points(days_apart: int | None) -> int | None:
    """Points from the upload date, or None when the score should be the minimum."""
    if days_apart is None:
        return 0            # archive upload or unknown: no evidence either way
    if days_apart < 0:
        return None         # uploaded before the game: impossible
    if days_apart <= _CONFIRM_WINDOW_DAYS:
        return 3
    if days_apart <= _SAME_SEASON_DAYS:
        return 2            # late, but still tied to the season
    return 0                # years later: an archive upload, says nothing


def collect_evidence(match: VideoMatch, row: GameRow, season_rows: list[GameRow]) -> Evidence:
    """Read off what supports this match, beyond the upload date."""
    parsed = match.parsed
    if parsed is None:
        # A EuroLeague match: its key is the round, which is as specific as a score.
        return Evidence(score_unique_in_season=True,
                        opponent_recognised=resolve_opponent(match.entry.title) is not None,
                        opponent_exact=False, kind_stated=True)

    score = (parsed.maccabi_points, parsed.opponent_points)
    same_score = [candidate for candidate in season_rows
                  if (candidate.maccabi_points, candidate.opponent_points) == score]
    resolved = resolve_opponent(parsed.opponent_raw)
    return Evidence(
        score_unique_in_season=len(same_score) == 1,
        opponent_recognised=resolved is not None,
        opponent_exact=(resolved is not None
                        and normalize_team_name(resolved) == normalize_team_name(row.opponent)),
        kind_stated=parsed.kind is not None,
    )


def score_match(match: VideoMatch, row: GameRow | None, evidence: Evidence) -> int:
    """A 1-10 confidence for one proposed match."""
    if row is None or not match.page_name:
        return MIN_SCORE

    days_apart = days_between_game_and_upload(row.date, match.entry.published)
    points = date_points(days_apart)
    if points is None:
        return MIN_SCORE

    score = _BASE_SCORE + points
    if not evidence.score_unique_in_season:
        score -= 2
    if not evidence.opponent_recognised:
        score -= 1
    if not evidence.opponent_exact:
        score -= 1
    if not evidence.kind_stated:
        score -= 1
    return max(MIN_SCORE, min(MAX_SCORE, score))


def score_all(matches: list[VideoMatch], rows: list[GameRow]) -> None:
    """Attach a confidence score to every match that names a page."""
    rows_by_page = {row.page_name: row for row in rows}
    rows_by_season: dict[str, list[GameRow]] = defaultdict(list)
    for row in rows:
        rows_by_season[row.season].append(row)

    for match in matches:
        row = rows_by_page.get(match.page_name or "")
        if row is None:
            match.confidence = MIN_SCORE if match.bucket == Bucket.EXACT else None
            continue
        evidence = collect_evidence(match, row, rows_by_season.get(row.season, []))
        match.confidence = score_match(match, row, evidence)
        match.days_after_game = days_between_game_and_upload(row.date, match.entry.published)
