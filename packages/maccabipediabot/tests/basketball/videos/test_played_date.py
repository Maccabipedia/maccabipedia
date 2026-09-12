"""The game date read out of a video description.

Every description here is a real one from the club's channel.
"""
import pytest

from maccabipediabot.basketball.videos.played_date import PlayedDate, parse_played_date


@pytest.mark.parametrize("description,season,expected", [
    ("מחזור 6. נערך ביד אליהו ב-14/1/88. מכבי: מגי 31, גמצ'י 17.",
     "1987/88", PlayedDate(1988, 1, 14)),
    ("סל ניצחון של מוראטי. משחק 5. יד אליהו, 17/12/92.",
     "1992/93", PlayedDate(1992, 12, 17)),
    ("כפר בלום,16/10/95.", "1995/96", PlayedDate(1995, 10, 16)),
    ("פזארו, 19/10/00. מכבי: האפמן 21.", "2000/01", PlayedDate(2000, 10, 19)),
    ("יד אליהו, 27/1/83, מחזור 5. מכבי: ויליאמס 19, סילבר 14",
     "1982/83", PlayedDate(1983, 1, 27)),
])
def test_reads_a_day_from_a_numeric_date(description, season, expected):
    assert parse_played_date(description, season) == expected


@pytest.mark.parametrize("description,expected", [
    ("נערך בקלן באוקטובר 1981. מכבי: מיקי 27", PlayedDate(1981, 10)),
    ("נערך ביד אליהו בנובמבר 1994", PlayedDate(1994, 11)),
    ("נערך בסלוניקי באפריל 2000", PlayedDate(2000, 4)),
    ("נערך ביד אליהו במרץ 1999", PlayedDate(1999, 3)),
])
def test_reads_a_month_when_that_is_all_the_description_gives(description, expected):
    parsed = parse_played_date(description)
    assert parsed == expected
    assert parsed.day is None
    assert parsed.iso is None


@pytest.mark.parametrize("description", [
    "מחזור 14 ואחרון. מכבי: מגי 22 ו-10 רב', מרסר 10 ו-12 רב'. ספליט: פראסוביץ' 20.",
    "www.maccabifans.co.il",
    "טופ-16",
    "מכבי עולה ל-1:0 בסדרה הטוב מ-5",
    "",
])
def test_says_nothing_rather_than_guessing(description):
    """A round number, a score and a series standing must never read as a date."""
    assert parse_played_date(description) is None


@pytest.mark.parametrize("season,two_digit_year,expected_year", [
    ("1987/88", "14/1/88", 1988),
    ("1999/00", "19/10/00", 2000),
    ("1995/96", "16/10/95", 1995),
    ("2009/10", "3/1/10", 2010),
])
def test_two_digit_years_resolve_against_the_season(season, two_digit_year, expected_year):
    """"00" is 2000 and "95" is 1995, so no fixed pivot works for a channel spanning both."""
    parsed = parse_played_date(f"יד אליהו, {two_digit_year}.", season)
    assert parsed.year == expected_year


def test_agreement_with_a_cargo_date():
    assert PlayedDate(1988, 1, 14).covers("1988-01-14") is True
    assert PlayedDate(1988, 2, 18).covers("1988-03-03") is False
    # A month-only description agrees with any day in that month.
    assert PlayedDate(1981, 10).covers("1981-10-22") is True
    assert PlayedDate(1981, 10).covers("1981-11-22") is False
    # An unreadable Cargo date is unknown, never a contradiction.
    assert PlayedDate(1988, 1, 14).covers("") is None
