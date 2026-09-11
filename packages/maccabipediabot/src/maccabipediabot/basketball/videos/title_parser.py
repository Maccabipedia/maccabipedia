"""Parse an official-channel video title into the key that identifies its game.

A title carries the two team names and the final score, but never a date:

    תקציר המשחק: מכבי Rapyd ת"א - אליצור נתניה 92:102
    Highlights: Hapoel Jerusalem - Maccabi FOX TelAviv 74:63
    המשחק המלא: מכבי Rapyd ת"א - באיירן מינכן 106:111

The home team is written first, so the score order follows the teams, not Maccabi.
Which side is Maccabi is therefore decided by NAME (a Maccabi token together with a
Tel Aviv token), never by position — several opponents are themselves named "מכבי".

`תרכיז` is the channel's word for a condensed game: the whole game with the dead time
cut out, 14-17 minutes against about 3 for a `תקציר`. It is a kind of its own so the
matcher can rank it below a real highlight when they compete for the same slot.
"""
import re
from dataclasses import dataclass
from enum import Enum


class VideoKind(Enum):
    HIGHLIGHTS = "highlights"
    FULL_GAME = "full_game"
    CONDENSED = "condensed"


@dataclass(frozen=True)
class ParsedTitle:
    kind: VideoKind
    opponent_raw: str
    maccabi_points: int
    opponent_points: int
    language: str


# Leading keyword -> (kind, language). The channel writes each of these with an
# optional qualifier before the separator ("תקציר מחזור 8 יורוליג:", "המשחק המלא
# (חצי גמר פלייאוף משחק 1):"), and uses either ":" or "|" as that separator.
_KEYWORDS: tuple[tuple[str, VideoKind, str], ...] = (
    ("תקציר", VideoKind.HIGHLIGHTS, "he"),
    ("תרכיז", VideoKind.CONDENSED, "he"),
    ("המשחק המלא", VideoKind.FULL_GAME, "he"),
    ("Condensed Game", VideoKind.CONDENSED, "en"),
    ("Championship Game Highlights", VideoKind.HIGHLIGHTS, "en"),
    ("Game Highlights", VideoKind.HIGHLIGHTS, "en"),
    ("Match Highlights", VideoKind.HIGHLIGHTS, "en"),
    ("Highlights", VideoKind.HIGHLIGHTS, "en"),
    ("Full Game", VideoKind.FULL_GAME, "en"),
)

# "<keyword><optional qualifier><: or |><body>". The qualifier is lazy so the FIRST
# separator wins — otherwise "תקציר: הפועל אילת - מכבי 85:70" would split on the score.
_PREFIX_RES: tuple[tuple[re.Pattern[str], VideoKind, str], ...] = tuple(
    (re.compile(rf"^{re.escape(keyword)}(?P<qualifier>[^:|]{{0,60}}?)\s*[:|]\s*(?P<body>.+)$", re.IGNORECASE),
     kind, language)
    for keyword, kind, language in _KEYWORDS
)

# Some titles trail the keyword instead of leading with it:
# 'מכבי Rapyd ת"א - ריאל מדריד 91:92 המשחק המלא'
_SUFFIX_RES: tuple[tuple[re.Pattern[str], VideoKind, str], ...] = tuple(
    (re.compile(rf"^(?P<body>.+?)\s+{re.escape(keyword)}\s*$"), kind, language)
    for keyword, kind, language in _KEYWORDS
)

# Friendlies and training games have teams and a score but no Cargo row, so they must
# never reach the matcher — a match there would be a false one.
_NON_COMPETITIVE_TOKENS = (
    "משחק ההכנה", "משחק הכנה", "משחק אימון", "משחקי הכנה", "קדם עונה",
    "preseason", "pre-season", "friendly",
)

_SCORE_RE = re.compile(r"(\d{1,3})\s*:\s*(\d{1,3})")
_TEAM_SEPARATOR_RE = re.compile(r"\s+(?:-|–|vs\.?|at|נגד|מול)\s+", re.IGNORECASE)
_MACCABI_TEL_AVIV_RE = re.compile(
    r'(?:מכבי.*(?:תל אביב|ת"א|ת״א))|(?:Maccabi.*Tel[\s-]?Aviv)',
    re.IGNORECASE,
)
# Sponsor names the club has carried; they are noise inside a team name.
_SPONSOR_TOKENS = ("rapyd", "playtika", "fox", "electra", "elite", "tsm")
# EuroLeague-era titles name the club as a bare "Maccabi" / "מכבי". That is only safe
# when nothing else is left in the name: "Maccabi Haifa" is a different club.
_BARE_MACCABI_NAMES = ("maccabi", "מכבי")


def _is_maccabi_tel_aviv(team_name: str) -> bool:
    if _MACCABI_TEL_AVIV_RE.search(team_name):
        return True
    remaining = [
        word for word in team_name.lower().split()
        if word not in _SPONSOR_TOKENS
    ]
    return len(remaining) == 1 and remaining[0] in _BARE_MACCABI_NAMES


def _match_keyword(title: str) -> tuple[str, VideoKind, str] | None:
    """Split the title into (body, kind, language) on its game-video keyword."""
    for pattern, kind, language in _PREFIX_RES:
        found = pattern.match(title)
        if found:
            return found.group("body").strip(), kind, language
    for pattern, kind, language in _SUFFIX_RES:
        found = pattern.match(title)
        if found:
            return found.group("body").strip(), kind, language
    return None


def parse_game_video_title(title: str) -> ParsedTitle | None:
    """The game key carried by a channel video title, or None if it isn't a game video."""
    lowered = title.lower()
    if any(token in lowered for token in _NON_COMPETITIVE_TOKENS):
        return None

    keyword_match = _match_keyword(title)
    if keyword_match is None:
        return None
    body, kind, language = keyword_match

    # Everything after a "|" or "(" is commentary, a competition note or a translation.
    body = re.split(r"\s*[|(]", body, maxsplit=1)[0].strip()

    score = _SCORE_RE.search(body)
    if score is None:
        return None

    sides = _TEAM_SEPARATOR_RE.split(body[:score.start()].strip(), maxsplit=1)
    if len(sides) != 2:
        return None
    left_team, right_team = (side.strip() for side in sides)
    left_points, right_points = int(score.group(1)), int(score.group(2))

    left_is_maccabi = _is_maccabi_tel_aviv(left_team)
    right_is_maccabi = _is_maccabi_tel_aviv(right_team)
    if left_is_maccabi == right_is_maccabi:
        # Neither side is Maccabi Tel Aviv, or the test can't tell them apart.
        return None
    if left_is_maccabi:
        return ParsedTitle(kind, right_team, left_points, right_points, language)
    return ParsedTitle(kind, left_team, right_points, left_points, language)
