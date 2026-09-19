"""Mark goalkeepers on an uploaded football game page.

The club site doesn't say who the goalkeepers are, so an editor marked them by hand after
every upload. The wiki's own history does know: anyone it recorded as a goalkeeper before.
"""
import logging
from datetime import date, timedelta
from functools import lru_cache

import requests

from maccabipediabot.common.maccabipedia_http import build_maccabipedia_session, parse_cargo_rows
from maccabipediabot.common.maccabistats_player_event import PlayerEvent

_logger = logging.getLogger(__name__)

_CARGO_EXPORT_URL = "https://www.maccabipedia.co.il/index.php?title=Special:CargoExport&format=json"

# Games_Sub_Events_Mapping: "שוער פתח בהרכב" and "שוער פתח בספסל"
_GOALKEEPER_SUB_EVENT_CODES = (111, 211)

# Old games list many players by one name (לוי, מזרחי), which would match outfield players today
_RECENT_GOALKEEPERS_YEARS = 10

_SQUAD_EVENTS = ("הרכב", "ספסל")
_GOALKEEPER_SUB_EVENT = "שוער"


def mark_goalkeepers(events: list[PlayerEvent], goalkeeper_names: frozenset[str]) -> None:
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


@lru_cache(maxsize=1)
def fetch_known_goalkeepers() -> frozenset[str]:
    """Players marked as a goalkeeper on a MaccabiPedia game page in recent years.

    A goalkeeper with no earlier game on the wiki is not in it, and stays unmarked.
    Marking goalkeepers is optional, so a failed query uploads the game without it.
    """
    codes = ",".join(str(code) for code in _GOALKEEPER_SUB_EVENT_CODES)
    since = date.today() - timedelta(days=365 * _RECENT_GOALKEEPERS_YEARS)
    try:
        response = build_maccabipedia_session().get(_CARGO_EXPORT_URL, params={
            "tables": "Games_Events",
            "fields": "PlayerName",
            "where": f"SubType IN ({codes}) AND Date >= '{since.isoformat()}'",
            "group_by": "PlayerName",
            "limit": 5000,
        }, timeout=60)
        response.raise_for_status()
        rows = parse_cargo_rows(response)
    except (requests.RequestException, ValueError):
        _logger.exception("Could not fetch the known goalkeepers, uploading without marking them")
        return frozenset()

    return frozenset(row["PlayerName"] for row in rows if " " in row["PlayerName"].strip())
