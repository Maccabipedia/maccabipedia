"""Parse a EuroLeague-channel title into the key that identifies its game.

Their titles never carry the score:

    Down to the FINAL SHOT | Maccabi - Panathinaikos | R24 BASKETBALL HIGHLIGHTS 2025-26
    Final Seconds COLLAPSE | Crvena Zvezda - Maccabi | R27 BASKETBALL HIGHLIGHTS 2025-26

but they do carry the season and the round, and Basketball_Games stores the round in
its Leg column as "מחזור 24". Season plus round plus opponent is therefore the key,
with no date and no score needed.

Classic Games replays name a season but no round; those match on the opponent within
the season, and land in the review bucket whenever that is not unique.
"""
import re
from dataclasses import dataclass

from maccabipediabot.basketball.videos.title_parser import VideoKind

# "2025-26" or "2013-14" — the season as their titles spell it.
_SEASON_RE = re.compile(r"(?<!\d)(20\d{2})-(\d{2})(?!\d)")
_ROUND_RE = re.compile(r"\bR(\d{1,2})\b")
_TEAM_SEPARATOR_RE = re.compile(r"\s+(?:-|–|vs\.?)\s+", re.IGNORECASE)
_MACCABI_RE = re.compile(r"\bMaccabi\b", re.IGNORECASE)
_FULL_GAME_TOKENS = ("classic game", "full game")


@dataclass(frozen=True)
class ParsedEuroleagueTitle:
    season: str
    round_number: int | None
    opponent_raw: str
    kind: VideoKind


def _season_from(title: str) -> str | None:
    found = _SEASON_RE.search(title)
    if not found:
        return None
    start_year, end_token = int(found.group(1)), found.group(2)
    if int(end_token) != (start_year + 1) % 100:
        return None
    return f"{start_year}/{end_token}"


# Boilerplate that trails a team name when the title has no "|" before it, as in
# "... Maccabi Tel Aviv - Panathinaikos 2013-14".
_TRAILING_NOISE_RE = re.compile(
    r"\s*(?:\b20\d{2}-\d{2}\b|\bR\d{1,2}\b|basketball|highlights|euroleague|game\s*\d+)\s*",
    re.IGNORECASE,
)


def _clean_team_name(name: str) -> str:
    return _TRAILING_NOISE_RE.sub(" ", name).strip(" -–:|").strip()


def _opponent_from(title: str) -> str | None:
    """The non-Maccabi side of whichever '|'-delimited segment names both teams."""
    for segment in title.split("|"):
        sides = _TEAM_SEPARATOR_RE.split(segment.strip(), maxsplit=1)
        if len(sides) != 2:
            continue
        left, right = (_clean_team_name(side) for side in sides)
        left_is_maccabi = _MACCABI_RE.search(left) is not None
        right_is_maccabi = _MACCABI_RE.search(right) is not None
        if left_is_maccabi == right_is_maccabi:
            continue  # both or neither: not a Maccabi game segment
        opponent = right if left_is_maccabi else left
        return opponent or None
    return None


def parse_euroleague_title(title: str) -> ParsedEuroleagueTitle | None:
    season = _season_from(title)
    if season is None:
        return None
    opponent = _opponent_from(title)
    if opponent is None:
        return None
    round_match = _ROUND_RE.search(title)
    kind = (VideoKind.FULL_GAME if any(token in title.lower() for token in _FULL_GAME_TOKENS)
            else VideoKind.HIGHLIGHTS)
    return ParsedEuroleagueTitle(
        season=season,
        round_number=int(round_match.group(1)) if round_match else None,
        opponent_raw=opponent,
        kind=kind,
    )
