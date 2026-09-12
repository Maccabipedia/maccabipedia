"""Map an official-channel playlist title to the wiki's season label.

The channel names its playlists inconsistently across the decades — "Season 2014/2015",
"2025/26 Season", "season 1979/80", "Games Highlights 2013-2014", "Game Highlights |
2025/26" — so the season token is extracted rather than pattern-matched as a whole.
Playlists that merely mention a season but hold no game videos (player compilations,
pre-season friendlies, condensed-game collections) are rejected outright.
"""
import re
from enum import Enum

# Two years, separated by / or -, the second given as 2 or 4 digits.
_SEASON_RE = re.compile(r"(?<!\d)(\d{4})\s*[/-]\s*(\d{2,4})(?!\d)")

# Playlists whose videos are not whole-game videos, however they name their season.
_EXCLUDED_TOKENS = ("players highlights", "pre-season", "preseason", "condensed")


class PlaylistKind(Enum):
    SEASON = "season"
    HIGHLIGHTS = "highlights"
    FULL_GAMES = "full_games"


def playlist_kind(title: str) -> PlaylistKind | None:
    """What kind of game-video playlist this is, or None if it isn't one."""
    lowered = title.lower()
    if any(token in lowered for token in _EXCLUDED_TOKENS):
        return None
    if "full game" in lowered:
        return PlaylistKind.FULL_GAMES
    if "highlight" in lowered:
        return PlaylistKind.HIGHLIGHTS
    if "season" in lowered:
        return PlaylistKind.SEASON
    # A title that is NOTHING but a season — the channel named the 2026/27 playlist
    # just "2026-27". Requiring the word "season" would have skipped that whole season
    # the moment it started, silently.
    if _SEASON_RE.fullmatch(title.strip()):
        return PlaylistKind.SEASON
    return None


def season_from_playlist_title(title: str) -> str | None:
    """The wiki season label ("2014/15") for a game-video playlist, else None."""
    if playlist_kind(title) is None:
        return None
    found = _SEASON_RE.search(title)
    if not found:
        return None
    start_year = int(found.group(1))
    end_token = found.group(2)[-2:]
    # Guard against ranges that aren't a single season ("Season 2014/2016").
    if int(end_token) != (start_year + 1) % 100:
        return None
    return f"{start_year}/{end_token}"
