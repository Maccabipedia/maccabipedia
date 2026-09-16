"""Read the date a game was played out of a channel video's description.

The archive uploads name no date in the title — that is exactly what holds them below the
write floor — but the club writes the date in the DESCRIPTION, in one of two forms:

    מחזור 6. נערך ביד אליהו ב-14/1/88. מכבי: מגי 31, גמצ'י 17.
    נערך בקלן באוקטובר 1981. מכבי: מיקי 27, ויליאמס 25

The first gives a day, the second only a month. Both are evidence the title cannot give,
and both cut the other way too: a description dated three weeks from the page it was
matched to is a contradiction, not a missing confirmation.

Two-digit years are resolved against the season the video was filed under, because the
club's own century rule is ambiguous on its face — "00" is 2000 and "95" is 1995, and no
fixed pivot gets both right for a channel that spans 1979 to today.
"""
import re
from dataclasses import dataclass

# Requires two separators, so a round number ("מחזור 6"), a score ("31, 17") and a
# series standing ("1:0 בסדרה") cannot be read as a date.
_NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{2,4})\b")

_HEBREW_MONTHS: dict[str, int] = {
    "ינואר": 1, "פברואר": 2, "מרץ": 3, "מרס": 3, "אפריל": 4, "מאי": 5, "יוני": 6,
    "יולי": 7, "אוגוסט": 8, "ספטמבר": 9, "אוקטובר": 10, "נובמבר": 11, "דצמבר": 12,
}
_MONTH_YEAR_RE = re.compile(
    rf"ב?({'|'.join(_HEBREW_MONTHS)})\s+(\d{{4}})")


@dataclass(frozen=True)
class PlayedDate:
    """When the description says the game was played. `day` is None for a month-only note."""
    year: int
    month: int
    day: int | None = None

    @property
    def iso(self) -> str | None:
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}" if self.day else None

    def covers(self, game_date: str) -> bool | None:
        """Does this description agree with a Cargo date (YYYY-MM-DD)?

        None when the Cargo date cannot be read, so that a malformed date is never
        reported as a contradiction.
        """
        parts = game_date.split("-")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            return None
        year, month, day = (int(part) for part in parts)
        if (year, month) != (self.year, self.month):
            return False
        return self.day is None or self.day == day


def _year_from_two_digits(two_digits: int, season: str) -> int:
    """Resolve "88" against the season the video is filed under.

    A season reads "1987/88", so both centuries it can mean are right there; without one
    fall back to the pivot that suits a channel whose archive starts in 1979.
    """
    for season_year in re.findall(r"\d{4}", season):
        century = int(season_year) // 100 * 100
        for candidate in (century + two_digits, century + 100 + two_digits):
            # The video is filed under a season, so the game is within a year of it.
            if abs(candidate - int(season_year)) <= 1:
                return candidate
    return 1900 + two_digits if two_digits >= 50 else 2000 + two_digits


def parse_played_date(description: str, season: str = "") -> PlayedDate | None:
    """The date the description says the game was played, or None when it says none."""
    if not description:
        return None

    numeric = _NUMERIC_DATE_RE.search(description)
    if numeric is not None:
        day, month, year_text = (numeric.group(1), numeric.group(2), numeric.group(3))
        year = (int(year_text) if len(year_text) == 4
                else _year_from_two_digits(int(year_text), season))
        if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
            return PlayedDate(year=year, month=int(month), day=int(day))

    month_year = _MONTH_YEAR_RE.search(description)
    if month_year is not None:
        return PlayedDate(year=int(month_year.group(2)),
                          month=_HEBREW_MONTHS[month_year.group(1)])
    return None
