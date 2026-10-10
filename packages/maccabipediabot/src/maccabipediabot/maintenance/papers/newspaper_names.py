"""What a newspaper clip is on the wiki: its file name and file-page text, built from strict params.

Pure functions, no network. The conventions follow the main uploaders' files (9,605 files
checked 2026-10, see `.claude/skills/upload-newspaper/rules.md`):

* name: ``<paper> <DD-MM-YYYY> <סיווג> <sport> <opponent> (<DD.MM.YYYY>)[ <description>].jpg``
  e.g. ``ידיעות אחרונות 30-10-1998 סיקור משחק כדורסל הכוכב האדום בלגרד (29.10.1998).jpg``
* a second piece from the same paper and day gets a short Hebrew description after the
  game-date brackets, never a number: ``... (29.10.1998) תגובות קטש וג'אקוביץ'.jpg``
* page: ``{{תיוג עיתונים}}`` / ``{{תיוג עיתוני כדורסל}}`` / ``{{תיוג עיתוני כדורעף}}`` with
  שם עיתון, תאריך פרסום (DD-MM-YYYY), סיווג and שיוך משחק (the exact game page title).
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date

from maccabipediabot.maintenance.tickets.ticket_names import Sport

# Papers the main uploaders use, by file count. A new paper is added here on purpose,
# so a typo ("ידיעות אחרונת") cannot create a new spelling on the wiki.
KNOWN_PAPERS = (
    "מעריב", "דבר", "ידיעות אחרונות", "חדשות הספורט", "על המשמר", "הארץ", "הבקר", "חרות",
    "למרחב", "פנדל", "זמנים", "ספורט ישראל", "חדשות", "ישראל היום", "קול העם", "עולם הספורט",
    "הדור", "ספורט הבקר", "אספקלריה של הספורט", "הצופה", "חדשות הערב", "שערים", "המשקיף",
)

# The values the tagging templates accept.
CLASSIFICATIONS = (
    "סיקור משחק", "לקראת משחק", "רגע ממשחק", "טבלת ליגה", "טבלת גביע",
    "סיקור מחזור", "הגרלת גביע", "אחר",
)

TEMPLATES = {
    Sport.FOOTBALL: "תיוג עיתונים",
    Sport.BASKETBALL: "תיוג עיתוני כדורסל",
    Sport.VOLLEYBALL: "תיוג עיתוני כדורעף",
}
GAME_PAGE_PREFIXES = {Sport.FOOTBALL: "משחק:", Sport.BASKETBALL: "כדורסל:", Sport.VOLLEYBALL: "כדורעף:"}

# Per-game cap on newspaper files, counting every file already linked to the game.
REGULAR_GAME_CAP = 2
SPECIAL_GAME_CAP = 5

# How far the publication can be from the game, in days.
MAX_DAYS_BEFORE_GAME = 7
MAX_DAYS_AFTER_GAME = 14

MAX_FILE_NAME_BYTES = 240  # MediaWiki's title limit is 255 bytes, minus "File:" and slack

_FORBIDDEN_IN_NAME = re.compile(r'["/\\:#<>\[\]|{}*?~\t\n\r\u00a0\u200e\u200f\u202a-\u202e]')
_HEBREW = re.compile(r"[א-ת]")


class NewspaperClipError(ValueError):
    """A param breaks the conventions; the message says which and how to fix it."""


@dataclass(frozen=True)
class NewspaperClip:
    paper: str
    publish_date: date
    classification: str
    sport: Sport
    opponent: str
    game_date: date
    game_page: str
    description: str = ""

    def __post_init__(self) -> None:
        validate(self)

    @property
    def file_name(self) -> str:
        name = (f"{self.paper} {self.publish_date:%d-%m-%Y} {self.classification} {self.sport.value} "
                f"{self.opponent} ({self.game_date:%d.%m.%Y})")
        if self.description:
            name += f" {self.description}"
        return f"{name}.jpg"

    @property
    def page_text(self) -> str:
        return (f"{{{{{TEMPLATES[self.sport]}\n"
                f"|שם עיתון={self.paper}\n"
                f"|תאריך פרסום={self.publish_date:%d-%m-%Y}\n"
                f"|סיווג={self.classification}\n"
                f"|שיוך משחק={self.game_page}\n"
                f"}}}}")


def validate(clip: NewspaperClip) -> None:
    if clip.paper not in KNOWN_PAPERS:
        raise NewspaperClipError(f"unknown paper {clip.paper!r}; known: {', '.join(KNOWN_PAPERS)} "
                                 f"(a genuinely new paper is added to KNOWN_PAPERS on purpose)")
    if clip.classification not in CLASSIFICATIONS:
        raise NewspaperClipError(f"סיווג {clip.classification!r} is not a template value; "
                                 f"use one of: {', '.join(CLASSIFICATIONS)}")
    if clip.classification in ("טבלת ליגה", "טבלת גביע"):
        raise NewspaperClipError(f"{clip.classification} files use their own names "
                                 f"('טבלת ליגה לאחר מחזור N עונת YYYY-YY.jpg', 294 files); this tool "
                                 f"does game clips only")
    _check_text("opponent", clip.opponent)
    if clip.description:
        _check_text("description", clip.description)
        if re.fullmatch(r"\(?\d+\)?|עיתון\s*\d+|עמוד\s*\d+", clip.description.strip()):
            raise NewspaperClipError(f"description {clip.description!r} is a number; say what the "
                                     f"piece is in Hebrew (e.g. 'תגובות המאמן')")
        if not _HEBREW.search(clip.description):
            raise NewspaperClipError("description must be Hebrew words saying what the piece is")
    _check_dates(clip)
    _check_game_page(clip)
    if len(clip.file_name.encode("utf-8")) > MAX_FILE_NAME_BYTES:
        raise NewspaperClipError(f"file name is {len(clip.file_name.encode('utf-8'))} bytes; the wiki "
                                 f"takes {MAX_FILE_NAME_BYTES}. Shorten the description")


def _check_text(field: str, value: str) -> None:
    if not value or value != value.strip() or "  " in value:
        raise NewspaperClipError(f"{field} {value!r}: empty, or has stray spaces")
    if _FORBIDDEN_IN_NAME.search(value):
        raise NewspaperClipError(f"{field} {value!r} has a character a file name can't hold "
                                 f"(no quote marks, slashes, tildes, tabs or invisible direction marks: צסקא מוסקבה)")


def _check_dates(clip: NewspaperClip) -> None:
    days = (clip.publish_date - clip.game_date).days
    if clip.classification == "לקראת משחק" and not -MAX_DAYS_BEFORE_GAME <= days <= 0:
        raise NewspaperClipError(f"a preview must be published on the game day or up to "
                                 f"{MAX_DAYS_BEFORE_GAME} days before it, not {days:+d} days")
    if clip.classification in ("סיקור משחק", "רגע ממשחק") and not 0 <= days <= MAX_DAYS_AFTER_GAME:
        raise NewspaperClipError(f"a report must be published on the game day or up to "
                                 f"{MAX_DAYS_AFTER_GAME} days after it, not {days:+d} days")


def _check_game_page(clip: NewspaperClip) -> None:
    prefix = GAME_PAGE_PREFIXES[clip.sport]
    if not clip.game_page.startswith(prefix):
        raise NewspaperClipError(f"{clip.sport.value} game page must start with {prefix!r}: {clip.game_page!r}")
    if "&quot;" in clip.game_page or "&#" in clip.game_page:
        raise NewspaperClipError(f"game page {clip.game_page!r} is HTML-escaped; pass the real title "
                                 f"(game_page_title() unescapes Cargo's)")
    rest = clip.game_page[len(prefix):]
    match = re.match(r"\s*(\d\d)-(\d\d)-(\d{4}) ", rest)
    try:
        on_date = match and date(int(match[3]), int(match[2]), int(match[1]))
    except ValueError:
        on_date = None
    if on_date != clip.game_date:
        raise NewspaperClipError(f"game page {clip.game_page!r} is not on {clip.game_date:%d-%m-%Y}")
    if clip.opponent not in game_opponents(clip.game_page):
        raise NewspaperClipError(f"opponent {clip.opponent!r} must be spelled as in the game page title, "
                                 f"without quote marks, a slash written as -: {' / '.join(game_opponents(clip.game_page)) or clip.game_page!r}")


# "<date> <home> נגד <away>[ - <competition>]"; volleyball titles also write "<away>- CEV CUP"
# or leave the competition out.
_TEAMS = re.compile(r"\s*\d\d-\d\d-\d{4} (.+?) נגד (.+?)(?:\s*-\s+.*)?$")


def game_opponents(game_page: str) -> set[str]:
    """The non-Maccabi side(s) of a game title, written the way a file name holds them (no quotes)."""
    _, _, rest = game_page.partition(":")
    teams = _TEAMS.match(rest)
    if not teams:
        return set()
    # A file name holds no quote mark and no slash: בית"ר -> ביתר, "הפועל מטה אשר/עכו" -> "...אשר-עכו".
    sides = {t.strip().replace('"', "").replace("/", "-") for t in teams.groups()}
    return {t for t in sides if t.replace("-", " ") != "מכבי תל אביב"}


def game_page_title(cargo_page_name: str) -> str:
    """Cargo returns titles HTML-escaped (בית&quot;ר); the wiki title has the real quote."""
    return html.unescape(cargo_page_name)


def game_cap(special: bool) -> int:
    return SPECIAL_GAME_CAP if special else REGULAR_GAME_CAP


def check_cap(existing_files: list[str], new_files: int, special: bool) -> None:
    cap = game_cap(special)
    if len(existing_files) + new_files > cap:
        kind = "special" if special else "regular"
        raise NewspaperClipError(
            f"a {kind} game takes up to {cap} newspaper files; it has {len(existing_files)} "
            f"({', '.join(existing_files) or 'none'}) and this adds {new_files}. Pick the most "
            f"informative ones, or pass --special for a title/cup-final/milestone game")
