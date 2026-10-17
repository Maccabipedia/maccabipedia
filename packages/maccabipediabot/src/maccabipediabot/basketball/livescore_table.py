"""Reading a livescore stage payload: which season it belongs to, and whether a game is in play.

The football, basketball and EuroLeague table scripts all read livescore stages.

Which season, so a table lands in that season's template:

The table scripts once named the template by a hard-coded season. When livescore rolled over to
the new season, they kept writing it into last season's template, which wiped the final standings
shown on last season's page. The payload carries no season label, but every event in it has a
start date, and a basketball season starts in the autumn.
"""
from datetime import date, datetime

import requests

_SEASON_START_MONTH = 7
# livescore's `Epr` (match progress): 0 not started, 2 over, whatever `Eps` says ("FT", or "OT"
# after overtime). Checked on every event of the football, basketball and EuroLeague payloads,
# 2026-10-17. Anything else is a game in play.
_NOT_IN_PLAY_PROGRESS = {0, 2}
# The template on each table page that holds the rows, e.g. {{טבלת כדורסל|טבלה=...}}.
TABLE_TEMPLATE_NAME = "טבלת כדורסל"


def fetch_stage(url: str) -> dict:
    """The first stage of a livescore stage URL; raises with the raw body on a non-JSON reply."""
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200 or "application/json" not in resp.headers.get("Content-Type", ""):
        raise RuntimeError(f"Unexpected livescore response: status={resp.status_code} "
                           f"ctype={resp.headers.get('Content-Type')}\n{resp.text[:300]}")
    return resp.json()["Stages"][0]


def games_in_play(stage: dict, today: date | None = None) -> list[str]:
    """The games of a livescore stage still being played, as "home - away (status)".

    livescore's table is live: a game in progress already counts in it, with its score at that
    moment, so a table saved during one shows a result that has not happened yet. Any progress
    that is not "not started" or "over" counts as in play. Only games dated within a day of today
    count, so a game stuck on an odd value cannot hold the table back for good.
    """
    today = today or datetime.now().date()
    in_play = []
    for event in stage.get("Events", []):
        if event.get("Epr") in _NOT_IN_PLAY_PROGRESS or not event.get("Esd"):
            continue
        start_day = datetime.strptime(str(event["Esd"])[:8], "%Y%m%d").date()
        if abs((start_day - today).days) > 1:
            continue
        in_play.append(f'{event["T1"][0]["Nm"]} - {event["T2"][0]["Nm"]} ({event.get("Eps")})')
    return in_play


def season_of_stage(stage: dict) -> str:
    """The season of a livescore stage as the wiki writes it, e.g. "2026/27".

    Taken from the earliest event's start date (`Esd`, "YYYYMMDDhhmmss"). A season whose first
    game falls from July on starts that year; an earlier one started the year before.
    """
    starts = [str(event["Esd"]) for event in stage.get("Events", []) if event.get("Esd")]
    if not starts:
        raise ValueError("livescore stage has no dated events; cannot tell its season")
    first = datetime.strptime(min(starts)[:8], "%Y%m%d")
    start_year = first.year if first.month >= _SEASON_START_MONTH else first.year - 1
    return f"{start_year}/{(start_year + 1) % 100:02d}"
