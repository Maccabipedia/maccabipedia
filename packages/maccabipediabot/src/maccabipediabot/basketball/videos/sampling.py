"""Pick a spread of proposed matches and check them against an independent signal.

The matcher's only evidence is the score and the opponent, both read from the same
title. The check here is the video's real upload date, which the matcher never sees:
the club posts a game's video within a day or two of the game, so an upload date close
to the page's date confirms the pairing from a different direction.

That signal does not exist for archival uploads — a 1985 game put online in 2015 — and
those are reported as such rather than being counted as confirmations.
"""
import logging
import random
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from maccabipediabot.basketball.videos.cargo import GameRow
from maccabipediabot.basketball.videos.matcher import Bucket, VideoMatch

logger = logging.getLogger(__name__)

# A video posted within this many days of the game confirms the match.
_CONFIRM_WINDOW_DAYS = 4
# Beyond this, the upload is an archival one and says nothing about which game it is.
_ARCHIVAL_THRESHOLD_DAYS = 300

DEFAULT_SEED = 20260911


class Verdict(Enum):
    CONFIRMED = "confirmed"
    DATE_MISMATCH = "date mismatch"
    NO_DATE_SIGNAL = "no date signal"


@dataclass(frozen=True)
class SampleCheck:
    match: VideoMatch
    game_date: str
    opponent: str
    home_away: str
    upload_date: str | None
    days_apart: int | None
    verdict: Verdict


def _decade(season: str) -> str:
    return f"{season[:3]}0s" if len(season) >= 3 else "unknown"


def _stratum(match: VideoMatch, rows_by_page: dict[str, GameRow]) -> tuple:
    row = rows_by_page.get(match.page_name)
    kind = match.kind.value if match.kind else "unknown"
    return (_decade(match.entry.season), row.home_away if row else "", kind)


def choose_verification_sample(matches: Iterable[VideoMatch], rows_by_page: dict[str, GameRow],
                               size: int = 20, seed: int = DEFAULT_SEED) -> list[VideoMatch]:
    """A spread of writable matches across decades, home and away, and video kinds.

    Round-robins over the strata so no decade or kind dominates, and falls back to
    whatever is left when a stratum runs dry. Deterministic for a given seed.
    """
    writable = [match for match in matches if match.bucket == Bucket.EXACT and match.slot]
    by_stratum: dict[tuple, list[VideoMatch]] = {}
    for match in writable:
        by_stratum.setdefault(_stratum(match, rows_by_page), []).append(match)

    shuffler = random.Random(seed)
    for group in by_stratum.values():
        group.sort(key=lambda match: match.entry.video_id)  # stable before shuffling
        shuffler.shuffle(group)

    strata = sorted(by_stratum)
    shuffler.shuffle(strata)
    chosen: list[VideoMatch] = []
    while len(chosen) < size:
        took_one = False
        for stratum in strata:
            if len(chosen) >= size:
                break
            group = by_stratum[stratum]
            if group:
                chosen.append(group.pop())
                took_one = True
        if not took_one:
            break  # every stratum is empty
    return chosen


def _days_between(game_date: str, upload_date: str) -> int | None:
    try:
        game = datetime.strptime(game_date, "%d-%m-%Y")
        upload = datetime.strptime(upload_date, "%Y%m%d")
    except ValueError:
        return None
    return (upload - game).days


def _verdict_for(days_apart: int | None) -> Verdict:
    if days_apart is None:
        return Verdict.NO_DATE_SIGNAL
    # Only a LATE upload can be archival. A video posted before the game was played
    # cannot be that game's video, however long before, so that stays a mismatch.
    if days_apart > _ARCHIVAL_THRESHOLD_DAYS:
        return Verdict.NO_DATE_SIGNAL
    if 0 <= days_apart <= _CONFIRM_WINDOW_DAYS:
        return Verdict.CONFIRMED
    return Verdict.DATE_MISMATCH


def verify_sample(sample: list[VideoMatch], rows_by_page: dict[str, GameRow],
                  fetch_upload_date: Callable[[str], str | None]) -> list[SampleCheck]:
    """Check each sampled match against its video's real upload date.

    `fetch_upload_date` is injected so this stays testable and so the caller decides
    how politely to hit YouTube.
    """
    checks = []
    for match in sample:
        row = rows_by_page.get(match.page_name)
        game_date = row.date if row else ""
        upload_date = fetch_upload_date(match.entry.video_id)
        days_apart = _days_between(game_date, upload_date) if upload_date else None
        checks.append(SampleCheck(
            match=match,
            game_date=game_date,
            opponent=row.opponent if row else "",
            home_away=row.home_away if row else "",
            upload_date=upload_date,
            days_apart=days_apart,
            verdict=_verdict_for(days_apart),
        ))
        logger.info("%s | %s | uploaded %s | %s",
                    match.entry.video_id, game_date, upload_date, checks[-1].verdict.value)
    return checks
