"""Shared helpers used by crawl_basket_co_il and crawl_euroleague."""
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class UnknownTeamNameError(RuntimeError):
    """A discovered team name was missing from translations._TEAM_NAMES.

    Carries the affected games so the CLI can emit a machine-readable report
    (consumed by CI to alert the error channel) instead of callers scraping the
    English name back out of the error message text.
    """

    def __init__(self, affected_games: list[dict]):
        self.affected_games = affected_games
        super().__init__(
            "Discovery encountered team names missing from translations._TEAM_NAMES; "
            "add the EN->HE mapping before re-running, otherwise the game page would be "
            f"titled with the English opponent name. Affected games: {affected_games}"
        )


def write_unknown_teams_report(report_path: Path | None, affected_games: list[dict]) -> None:
    """Write `affected_games` to `report_path` as JSON; no-op when path is None.

    The file's presence is the signal CI keys off to alert; its contents are the
    games to fix. Keeps the Python<->workflow contract explicit rather than having
    the workflow grep the error text out of the crawl logs."""
    if report_path is not None:
        report_path.write_text(
            json.dumps(affected_games, ensure_ascii=False, indent=2), encoding="utf-8"
        )


# Box-score scrapers treat absent / None / "" / "-" as "0" deliberately —
# a player who didn't take any free throws genuinely has 0 attempts.
_NUMERIC_ABSENT = {None, "", "-"}


def to_int(value) -> int:
    """Coerce a stat value to int. Absent (None / "" / "-") → 0; anything
    else just goes through int() and propagates its own TypeError/ValueError
    on truly malformed input — so a schema-drift bug fails loudly instead of
    silently zeroing a column for every player."""
    if value in _NUMERIC_ABSENT:
        return 0
    return int(value)


def to_int_or_none(value) -> int | None:
    """Like to_int but returns None for absent values."""
    if value in _NUMERIC_ABSENT:
        return None
    return int(value)


def season_from_date(d: datetime) -> str:
    """Return season string like '2024/25'. Israeli basketball season runs Sep–Jun."""
    year = d.year
    if d.month >= 9:
        return f"{year}/{(year + 1) % 100:02d}"
    return f"{year - 1}/{year % 100:02d}"
