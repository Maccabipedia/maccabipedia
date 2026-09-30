"""What a ticket file is: which sport, which date, and what it is called on the wiki.

Pure functions, no network. The wiki's conventions (2,360 ticket files, checked 2026-09-30):

* football:   ``כרטיס משחק 23 באוגוסט 2026.jpg``      + ``{{תיוג כרטיס משחק}}``
* basketball: ``כרטיס משחק כדורסל 24-09-2020.jpg``    + ``{{תיוג כרטיס משחק כדורסל|משחק=<page>}}``
* volleyball: ``כרטיס משחק כדורעף 08-02-2026.jpg``    + ``{{תיוג כרטיס משחק כדורעף|משחק=<page>}}``

The football template takes no game parameter: it reads the date out of the file's own
name (strips ``כרטיס משחק`` and the extension), so a football ticket must be named in
exactly that format or it lands in ``כרטיסי משחק כדורגל עם תאריך ללא משחק``. That is why
every ticket is uploaded under its canonical name, whatever it was called when it arrived.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum


class Sport(Enum):
    FOOTBALL = "כדורגל"
    BASKETBALL = "כדורסל"
    VOLLEYBALL = "כדורעף"


CARGO_TABLES = {
    Sport.FOOTBALL: "Football_Games",
    Sport.BASKETBALL: "Basketball_Games",
    Sport.VOLLEYBALL: "Volleyball_Games",
}

HEBREW_MONTHS = (
    "ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
    "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר",
)

# The football template only strips .jpg/.jpeg/.png from the name, so no PDFs.
SUPPORTED_EXTENSIONS = (".jpg", ".jpeg", ".png")

# A date must carry separators: a bare digit run such as "132321" or "24092020" is a
# camera counter as often as a date, and guessing wrong uploads to the wrong game.
# Any of - . / may separate the parts, mixed too ("24-09/2020"): people type captions fast.
_NUMERIC_DATE = re.compile(
    r"(?<!\d)(?:(?P<d>\d{1,2})[-./](?P<m>\d{1,2})[-./](?P<y>\d{4})"
    r"|(?P<y2>\d{4})[-./](?P<m2>\d{1,2})[-./](?P<d2>\d{1,2}))(?!\d)"
)
_HEBREW_DATE = re.compile(
    r"(?<!\d)(?P<d>\d{1,2})\s+ב(?P<month>" + "|".join(HEBREW_MONTHS) + r")\s+(?P<y>\d{4})(?!\d)"
)


@dataclass(frozen=True)
class FoundDate:
    value: date
    hebrew_month_format: bool


def _spaced(text: str) -> str:
    """Underscores read as spaces, the way MediaWiki reads them in a title:
    ``כרטיס_משחק_03_בדצמבר_1994.jpg`` is ``כרטיס משחק 03 בדצמבר 1994.jpg``."""
    return text.replace("_", " ")


def find_date(text: str) -> FoundDate | None:
    """The first valid calendar date written in ``text``, or ``None``."""
    text = _spaced(text)
    for match in _HEBREW_DATE.finditer(text):
        found = _safe_date(match["y"], HEBREW_MONTHS.index(match["month"]) + 1, match["d"])
        if found:
            return FoundDate(found, hebrew_month_format=True)
    for match in _NUMERIC_DATE.finditer(text):
        if match["y"]:
            found = _safe_date(match["y"], match["m"], match["d"])
        else:
            found = _safe_date(match["y2"], match["m2"], match["d2"])
        if found:
            return FoundDate(found, hebrew_month_format=False)
    return None


def _safe_date(year: str | int, month: str | int, day: str | int) -> date | None:
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def find_sport(text: str) -> Sport | None:
    """The sport named in ``text``. ``כדורגל`` is accepted for football even though
    football file names never say it — people write it in captions and replies."""
    text = _spaced(text)
    for sport in Sport:
        if sport.value in text:
            return sport
    return None


@dataclass(frozen=True)
class TicketIdentity:
    sport: Sport
    game_date: date


def identify(texts: list[str]) -> TicketIdentity | None:
    """Sport and date from ``texts``, most trusted first (a reply or caption, then the
    file name). Each is taken from the first text that has it, so a caption of just
    ``24-09-2020`` can fix the date of ``כרטיס משחק כדורסל 132321.jpg``.

    A Hebrew-month date with no sport word is football, because that is the football
    naming convention; a numeric date with no sport word is ambiguous and returns ``None``.
    """
    sport = next((s for s in map(find_sport, texts) if s), None)
    found = next((d for d in map(find_date, texts) if d), None)
    if found is None:
        return None
    if sport is None and found.hebrew_month_format:
        sport = Sport.FOOTBALL
    if sport is None:
        return None
    return TicketIdentity(sport, found.value)


# Names that phones and apps give files. The date in them is when the photo was taken or
# sent ("WhatsApp Image 2026-09-27 at 20.31.24.jpg"), not when the game was played.
_DEVICE_NAME = re.compile(r"^(whatsapp|img|pxl|screenshot|signal|photo|image|telegram)[\s_-]", re.IGNORECASE)


def is_device_name(file_name: str) -> bool:
    return bool(_DEVICE_NAME.match(file_name))


def normalized_extension(file_name: str) -> str | None:
    """Lower-case extension of ``file_name`` if it is a supported image, else ``None``."""
    match = re.search(r"\.[A-Za-z]+$", file_name)
    if not match or match.group().lower() not in SUPPORTED_EXTENSIONS:
        return None
    return match.group().lower()


def canonical_file_name(identity: TicketIdentity, extension: str) -> str:
    day = identity.game_date
    if identity.sport is Sport.FOOTBALL:
        return f"כרטיס משחק {day.day:02d} ב{HEBREW_MONTHS[day.month - 1]} {day.year}{extension}"
    return f"כרטיס משחק {identity.sport.value} {day:%d-%m-%Y}{extension}"


def tagging_template(sport: Sport, game_page: str) -> str:
    if sport is Sport.FOOTBALL:
        return "{{תיוג כרטיס משחק}}"
    return f"{{{{תיוג כרטיס משחק {sport.value}|משחק={game_page}}}}}"
