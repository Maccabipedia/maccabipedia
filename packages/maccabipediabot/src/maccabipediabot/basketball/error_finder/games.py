"""Every Basketball_Games row, as the error finder reads it.

Cargo Export answers with an HTML error page when it fails, so the response is checked
before it is parsed (``parse_cargo_rows``), and its string values arrive HTML-escaped
(בית&quot;ר ירושלים), so they are unescaped on the way in. Unlike the video matcher's
reader, games without a score are kept: a missing score is one of the errors.
"""
import html
import logging
from dataclasses import dataclass
from datetime import date

from maccabipediabot.common.maccabipedia_http import build_maccabipedia_session, parse_cargo_rows

logger = logging.getLogger(__name__)

CARGO_EXPORT_URL = "https://www.maccabipedia.co.il/index.php"
_TABLE = "Basketball_Games"
_PERIODS = ("First", "Second", "Third", "Fourth")
_SIDES = ("Maccabi", "Opponent")
# IsOvertime is not read: `משחק כדורסל/שמירת משחק לקארגו` never stores the page's |הארכה=,
# so the column is empty on every row. Overtime is judged from the overtime points instead.
_FIELDS = ",".join(
    ["_pageName", "Date", "Season", "Competition", "Leg", "Opponent", "HomeAway", "Technical",
     "TotalPointsMaccabi", "TotalPointsOpponent"]
    + [f"{period}QuarterPoints{side}" for period in _PERIODS for side in _SIDES]
    + [f"{period}HalfPoints{side}" for period in _PERIODS[:2] for side in _SIDES]
    + [f"{period}OvertimePoints{side}" for period in _PERIODS for side in _SIDES]
)
_REQUEST_TIMEOUT_SECONDS = 120
_PAGE_SIZE = 2500


@dataclass(frozen=True)
class SidePoints:
    """One team's points in one game. A period nobody filled in is ``None``, not 0."""
    total: int | None
    quarters: tuple[int | None, int | None, int | None, int | None]
    halves: tuple[int | None, int | None]
    overtimes: tuple[int | None, int | None, int | None, int | None]

    @property
    def overtime_points(self) -> int:
        return sum(points or 0 for points in self.overtimes)


@dataclass(frozen=True)
class BasketballGameRecord:
    page_name: str
    date: date | None
    season: str
    competition: str
    leg: str
    opponent: str
    home_away: str
    technical: bool
    maccabi: SidePoints
    opponent_points: SidePoints

    def __str__(self) -> str:
        return self.page_name


def _clean(value: object) -> str:
    return html.unescape(str(value)).strip() if value not in (None, "") else ""


def _number(value: object) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _flag(value: object) -> bool:
    return value not in (None, "", 0, "0", False)


def _side_from_cargo(raw: dict, side: str) -> SidePoints:
    return SidePoints(
        total=_number(raw.get(f"TotalPoints{side}")),
        quarters=tuple(_number(raw.get(f"{period}QuarterPoints{side}")) for period in _PERIODS),
        halves=tuple(_number(raw.get(f"{period}HalfPoints{side}")) for period in _PERIODS[:2]),
        overtimes=tuple(_number(raw.get(f"{period}OvertimePoints{side}")) for period in _PERIODS),
    )


def record_from_cargo(raw: dict) -> BasketballGameRecord:
    raw_date = _clean(raw.get("Date"))
    return BasketballGameRecord(
        page_name=_clean(raw.get("_pageName")),
        date=date.fromisoformat(raw_date[:10]) if raw_date else None,
        season=_clean(raw.get("Season")),
        competition=_clean(raw.get("Competition")),
        leg=_clean(raw.get("Leg")),
        opponent=_clean(raw.get("Opponent")),
        home_away=_clean(raw.get("HomeAway")),
        technical=_flag(raw.get("Technical")),
        maccabi=_side_from_cargo(raw, "Maccabi"),
        opponent_points=_side_from_cargo(raw, "Opponent"),
    )


def fetch_basketball_games() -> list[BasketballGameRecord]:
    """Every Basketball_Games row on prod, ordered by date."""
    session = build_maccabipedia_session()
    records: list[BasketballGameRecord] = []
    offset = 0
    while True:
        response = session.get(CARGO_EXPORT_URL, timeout=_REQUEST_TIMEOUT_SECONDS, params={
            "title": "Special:CargoExport", "format": "json", "tables": _TABLE, "fields": _FIELDS,
            "order by": "Date,_pageName", "limit": _PAGE_SIZE, "offset": offset,
        })
        if response.status_code != 200:
            raise RuntimeError(f"Cargo export failed with HTTP {response.status_code}: {response.text[:300]}")
        page = parse_cargo_rows(response)
        records += [record_from_cargo(raw) for raw in page]
        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    logger.info("Cargo: %d basketball games", len(records))
    return records
