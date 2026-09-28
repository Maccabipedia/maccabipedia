"""Which season a livescore stage payload belongs to, so a table lands in that season's template.

The table scripts once named the template by a hard-coded season. When livescore rolled over to
the new season, they kept writing it into last season's template, which wiped the final standings
shown on last season's page. The payload carries no season label, but every event in it has a
start date, and a basketball season starts in the autumn.
"""
from datetime import datetime

import requests

_SEASON_START_MONTH = 7
# The template on each table page that holds the rows, e.g. {{טבלת כדורסל|טבלה=...}}.
TABLE_TEMPLATE_NAME = "טבלת כדורסל"


def fetch_stage(url: str) -> dict:
    """The first stage of a livescore stage URL; raises with the raw body on a non-JSON reply."""
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200 or "application/json" not in resp.headers.get("Content-Type", ""):
        raise RuntimeError(f"Unexpected livescore response: status={resp.status_code} "
                           f"ctype={resp.headers.get('Content-Type')}\n{resp.text[:300]}")
    return resp.json()["Stages"][0]


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
