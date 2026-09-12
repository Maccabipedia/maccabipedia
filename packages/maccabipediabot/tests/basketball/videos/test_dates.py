"""Tests for comparing a game's date with a video's upload date.

Both halves arrive in more than one spelling, and getting either wrong silently costs
the match its strongest piece of evidence rather than raising anything.
"""
import pytest

from maccabipediabot.basketball.videos.dates import (
    days_between_game_and_upload,
    parse_game_date,
    parse_upload_date,
)


@pytest.mark.parametrize("game_date,expected", [
    ("2026-05-17", (2026, 5, 17)),   # as Cargo returns it
    ("17-05-2026", (2026, 5, 17)),   # as page titles and the bots write it
])
def test_game_dates_are_read_in_both_spellings(game_date, expected):
    parsed = parse_game_date(game_date)
    assert parsed is not None
    assert (parsed.year, parsed.month, parsed.day) == expected


@pytest.mark.parametrize("upload_date,expected", [
    ("20261122", (2026, 11, 22)),                       # watch page and yt-dlp
    ("2026-11-22T10:52:14+00:00", (2026, 11, 22)),      # RSS feed
    ("2026-11-22", (2026, 11, 22)),
])
def test_upload_dates_are_read_in_both_spellings(upload_date, expected):
    parsed = parse_upload_date(upload_date)
    assert parsed is not None
    assert (parsed.year, parsed.month, parsed.day) == expected


def test_an_rss_timestamp_yields_the_same_answer_as_a_compact_one():
    """The scheduled run gets its dates from RSS, where they arrive as ISO timestamps.
    Reading only the first eight characters of those gives "2026-11-" and fails, which
    would leave every video in that run with no date evidence."""
    assert days_between_game_and_upload("2026-11-22", "2026-11-22T10:52:14+00:00") == 0
    assert days_between_game_and_upload("2026-11-22", "20261122") == 0


@pytest.mark.parametrize("game_date,upload_date,expected", [
    ("2026-11-22", "20261122", 0),
    ("2026-11-22", "20261126", 4),
    ("2026-11-22", "20261101", -21),
    ("22-11-2026", "2026-11-23T08:00:00+00:00", 1),
])
def test_days_between(game_date, upload_date, expected):
    assert days_between_game_and_upload(game_date, upload_date) == expected


@pytest.mark.parametrize("game_date,upload_date", [
    ("", "20261122"),
    ("not a date", "20261122"),
    ("2026-11-22", ""),
    ("2026-11-22", "rubbish"),
    ("2026-11-22", None),
])
def test_unreadable_input_gives_no_answer_rather_than_a_wrong_one(game_date, upload_date):
    assert days_between_game_and_upload(game_date, upload_date) is None
