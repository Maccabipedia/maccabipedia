"""Wiki conventions the football uploader applies before writing a game page.

The club site's data differs from how MaccabiPedia writes a game, so an editor used to
fix every uploaded page by hand (see the history of the 14-09-2026 derby page).
"""
import logging
from collections import defaultdict

from maccabipediabot.common.maccabipedia_http import build_maccabipedia_session, parse_cargo_rows
from maccabipediabot.common.maccabistats_player_event import PlayerEvent

_logger = logging.getLogger(__name__)

_CARGO_EXPORT_URL = "https://www.maccabipedia.co.il/index.php?title=Special:CargoExport&format=json"

# Games_Sub_Events_Mapping: "שוער פתח בהרכב" and "שוער פתח בספסל"
_GOALKEEPER_SUB_EVENT_CODES = (111, 211)

# The club site writes names with a Hebrew geresh (ג׳יימס), the wiki with an apostrophe (ג'יימס)
_HEBREW_GERESH = "׳"

# Club site stadium name -> the stadium's page title on the wiki
_STADIUM_WIKI_NAMES = {
    "בלומפילד": "אצטדיון בלומפילד",
}

_YELLOW_CARD = "כרטיס צהוב"
_RED_CARD = "כרטיס אדום"
_SQUAD_EVENTS = ("הרכב", "ספסל")
_GOALKEEPER_SUB_EVENT = "שוער"


def to_maccabipedia_name(name: str) -> str:
    return name.replace(_HEBREW_GERESH, "'")


def to_maccabipedia_stadium(stadium: str) -> str:
    return _STADIUM_WIKI_NAMES.get(stadium, stadium)


def mark_second_yellow_cards(events: list[PlayerEvent]) -> list[PlayerEvent]:
    """Write a two-yellows sending-off the way the wiki does: צהוב-ראשון, then צהוב-שני.

    The club site lists it as two plain yellows plus a red at the second yellow's minute;
    the wiki has no separate red for it, so that red is dropped.
    """
    yellows_by_player = defaultdict(list)
    for event in events:
        if event.event_type == _YELLOW_CARD:
            yellows_by_player[(event.name, event.team)].append(event)

    implied_reds = set()
    for (player_name, team), yellows in yellows_by_player.items():
        if len(yellows) < 2:
            continue
        first_yellow, second_yellow = sorted(yellows, key=lambda yellow: yellow.minute_occur)[:2]
        first_yellow.sub_event_type = "ראשון"
        second_yellow.sub_event_type = "שני"
        implied_reds.add((player_name, team, second_yellow.minute_occur))

    return [event for event in events
            if not (event.event_type == _RED_CARD and (event.name, event.team, event.minute_occur) in implied_reds)]


def mark_goalkeepers(events: list[PlayerEvent], goalkeeper_names: set[str]) -> None:
    """Mark the squad events of known goalkeepers as הרכב-שוער / ספסל-שוער."""
    for event in events:
        if event.event_type in _SQUAD_EVENTS and event.sub_event_type is None and event.name in goalkeeper_names:
            event.sub_event_type = _GOALKEEPER_SUB_EVENT

    for team in ("מכבי", "יריבה"):
        has_starting_goalkeeper = any(
            event.team == team and event.event_type == "הרכב" and event.sub_event_type == _GOALKEEPER_SUB_EVENT
            for event in events)
        if not has_starting_goalkeeper:
            _logger.warning(f"No known goalkeeper in the {team} line-up, mark it by hand")


def fetch_known_goalkeepers() -> set[str]:
    """Every player who was ever marked as a goalkeeper on a MaccabiPedia game page.

    A goalkeeper with no earlier game on the wiki is not in it, and stays unmarked.
    """
    codes = ",".join(str(code) for code in _GOALKEEPER_SUB_EVENT_CODES)
    response = build_maccabipedia_session().get(_CARGO_EXPORT_URL, params={
        "tables": "Games_Events",
        "fields": "PlayerName",
        "where": f"SubType IN ({codes})",
        "group_by": "PlayerName",
        "limit": 10000,
    }, timeout=60)
    response.raise_for_status()
    return {row["PlayerName"] for row in parse_cargo_rows(response)}
