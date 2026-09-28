"""Which season a livescore stage payload belongs to, so a table lands in that season's template.

The table scripts once named the template by a hard-coded season. When livescore rolled over to
the new season, they kept writing it into last season's template, which wiped the final standings
shown on last season's page. The payload carries no season label, but every event in it has a
start date, and a basketball season starts in the autumn.
"""
from datetime import datetime

_SEASON_START_MONTH = 7


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
