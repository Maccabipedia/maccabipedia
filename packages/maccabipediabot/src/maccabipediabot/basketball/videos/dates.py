"""Comparing a game's date with a video's upload date.

Kept apart from both the matcher and the confidence score because both need it: the
matcher to choose between candidate games, the score to say how sure we are.

Cargo returns dates as "2026-05-17" while page titles and the bots use "17-05-2026",
so both are accepted.
"""
from datetime import datetime

_GAME_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y")


def parse_game_date(game_date: str) -> datetime | None:
    for date_format in _GAME_DATE_FORMATS:
        try:
            return datetime.strptime(game_date, date_format)
        except ValueError:
            continue
    return None


def parse_upload_date(upload_date: str) -> datetime | None:
    """A video's publish time, however the source spells it.

    The two sources disagree: the watch page and yt-dlp give "20261122", while an RSS
    feed gives "2026-11-22T10:52:14+00:00". Taking the first eight characters works for
    the first and silently fails for the second, which would leave every video in the
    scheduled run with no date evidence at all.
    """
    text = upload_date.strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        text = text[:10].replace("-", "")
    else:
        text = text[:8]
    try:
        return datetime.strptime(text, "%Y%m%d")
    except ValueError:
        return None


def days_between_game_and_upload(game_date: str, upload_date: str | None) -> int | None:
    """How many days after the game the video went up, or None if either is unreadable."""
    if not upload_date:
        return None
    game = parse_game_date(game_date or "")
    upload = parse_upload_date(upload_date)
    if game is None or upload is None:
        return None
    return (upload - game).days
