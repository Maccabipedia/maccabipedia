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
import re
from dataclasses import dataclass

from collections import defaultdict

from maccabipediabot.basketball.videos.aliases import (
    normalize_team_name,
    opponent_matches,
    resolve_opponent,
)
from maccabipediabot.basketball.videos.cargo import GameRow
from maccabipediabot.basketball.videos.dates import days_between_game_and_upload, parse_game_date
from maccabipediabot.basketball.videos.matcher import Bucket, VideoMatch

MIN_SCORE = 1
MAX_SCORE = 10

_BASE_SCORE = 7
_CONFIRM_WINDOW_DAYS = 4
_SAME_SEASON_DAYS = 300


@dataclass(frozen=True)
class Evidence:
    """What, besides the date, supports this match.

    Deliberately narrow: only things that bear on whether this video shows THIS game.
    Two properties that look like quality signals are left out on purpose.

    Whether the title stated the kind of video, or the kind had to be read off its
    length, says nothing about which game it is — it decides which parameter the link
    goes in, not whether the link is right. It used to cost a point, which held 655
    otherwise-perfect archive matches below their real confidence.

    Whether the opponent name matched exactly or by containment is likewise not a
    weakness: the alias table maps each club to the distinctive part of its name
    precisely because Cargo spells the same club differently by era, so containment is
    the designed-for normal case rather than a near miss.
    """
    # Only one game that season ended with this score, so the opponent was not needed
    # to choose between candidates.
    score_unique_in_season: bool
    # The opponent named in the title is the opponent on the page we chose. This has to
    # be checked against the CHOSEN ROW, not merely be readable: a match made on the
    # upload date alone can name a club the page does not, and recording only "the name
    # parsed" let those score a perfect 10 while the two names disagreed.
    opponent_agrees: bool
    # The names are the same once normalised, rather than one merely containing the
    # other. An exact agreement identifies the game as firmly as a unique score does,
    # which is what lets a shared score stop costing anything.
    opponent_exact: bool = False
    # Whether a year written in the title agrees with the year the game was played, or
    # None when the title names no year. The season used for matching comes from the
    # PLAYLIST, never the title, so this is independent — and it is the only such
    # evidence available for archive uploads, whose dates say nothing.
    title_year_agrees: bool | None = None


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


_YEAR_RE = re.compile(r"(?<!\d)(19[5-9]\d|20[0-2]\d)(?!\d)")
# The channel also writes the season in two digits: "ליגת העל 08/09, מח' 6". Requiring
# consecutive halves keeps this off scores (96:95 has no slash) and off dates like
# "16/02". The century is ambiguous, so both readings count — this is corroborating
# evidence, not an identifier.
_SHORT_SEASON_RE = re.compile(r"(?<!\d)(\d{2})\s*/\s*(\d{2})(?!\d)")


def years_in_title(title: str) -> set[int]:
    years = {int(year) for year in _YEAR_RE.findall(title)}
    for first, second in _SHORT_SEASON_RE.findall(title):
        if int(second) != (int(first) + 1) % 100:
            continue
        for century in (1900, 2000):
            years.add(century + int(first))
            years.add(century + int(second))
    return years


def title_year_agrees(title: str, game_date: str) -> bool | None:
    """Does a year written in the title match the year the game was played?

    None when the title names no year. A season spans two calendar years, so either
    side of the game's own year counts as agreement.
    """
    years = years_in_title(title)
    if not years:
        return None
    game = parse_game_date(game_date or "")
    if game is None:
        return None
    return bool(years & {game.year - 1, game.year, game.year + 1})


def collect_evidence(match: VideoMatch, row: GameRow, season_rows: list[GameRow]) -> Evidence:
    """Read off what supports this match, beyond the upload date."""
    year_agrees = title_year_agrees(match.entry.title, row.date)
    parsed = match.parsed
    if parsed is None:
        # A EuroLeague match: its key is the season plus the round, which picks out one
        # game as sharply as a score does, and the matcher already required the opponent
        # to agree before returning EXACT.
        return Evidence(score_unique_in_season=True, opponent_agrees=True,
                        opponent_exact=True, title_year_agrees=year_agrees)

    score = (parsed.maccabi_points, parsed.opponent_points)
    same_score = [candidate for candidate in season_rows
                  if (candidate.maccabi_points, candidate.opponent_points) == score]
    resolved = resolve_opponent(parsed.opponent_raw)
    return Evidence(
        score_unique_in_season=len(same_score) == 1,
        opponent_agrees=opponent_matches(parsed.opponent_raw, row.opponent),
        opponent_exact=(resolved is not None
                        and normalize_team_name(resolved) == normalize_team_name(row.opponent)),
        title_year_agrees=year_agrees,
    )


def score_match(match: VideoMatch, row: GameRow | None, evidence: Evidence) -> int:
    """A 1-10 confidence for one proposed match."""
    if row is None or not match.page_name:
        return MIN_SCORE

    days_apart = days_between_game_and_upload(row.date, match.entry.published)
    points = date_points(days_apart)
    if points is None:
        return MIN_SCORE

    if evidence.title_year_agrees is False:
        # The title names a year that is not the year of this game. Whatever else lines
        # up, something is wrong with the pairing.
        return MIN_SCORE + 1

    date_confirms = points == 3

    score = _BASE_SCORE + points
    if points == 0 and evidence.title_year_agrees:
        # No usable upload date, but the title's own year backs the match. Coarser than
        # a same-day upload, so it is worth less than one — but it is real evidence, and
        # for the archive era it is the only kind there is.
        score += 2
    settled_independently = date_confirms or evidence.opponent_exact
    if not evidence.score_unique_in_season and not settled_independently:
        # A score shared by two games that season is a weakness only while nothing else
        # settles which game it was. Two things do. An upload dated to the game confirms
        # the pick from a direction the title cannot reach. So does an opponent name that
        # matches the page exactly — 1984/85 has two games ending 88:87, against Cibona
        # Zagreb and against Hapoel Tel Aviv, and a title naming Cibona has identified its
        # game as firmly as a unique score would. Only a loose or unrecognised name leaves
        # real doubt.
        score -= 2
    if not evidence.opponent_agrees:
        # Two points, not one. At one point a date-confirmed match whose opponent
        # CONTRADICTS the page still scored 9 — and 9 is the floor the unattended job
        # writes at, so the single piece of evidence pointing the other way was worth
        # nothing in practice. These now land at 8 and wait for a human.
        score -= 2
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
