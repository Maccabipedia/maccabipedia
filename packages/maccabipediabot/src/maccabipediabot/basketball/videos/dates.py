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


def days_between_game_and_upload(game_date: str, upload_date: str | None) -> int | None:
    """How many days after the game the video went up, or None if either is unreadable."""
    if not upload_date:
        return None
    game = parse_game_date(game_date or "")
    if game is None:
        return None
    try:
        upload = datetime.strptime(upload_date[:8], "%Y%m%d")
    except ValueError:
        return None
    return (upload - game).days
