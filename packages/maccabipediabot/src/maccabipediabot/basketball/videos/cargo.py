"""Read the Basketball_Games rows the matcher works against.

Cargo Export answers with an HTML error page when it fails, so the response is checked
before it is parsed, and its string values arrive HTML-escaped (צסק&quot;א מוסקבה),
so they are unescaped on the way in.
"""
import html
import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

CARGO_EXPORT_URL = "https://www.maccabipedia.co.il/index.php"
_TABLE = "Basketball_Games"
_FIELDS = (
    "_pageName,Date,Season,Opponent,Competition,Leg,HomeAway,"
    "TotalPointsMaccabi,TotalPointsOpponent,"
    "HighlightsVideo,HighlightsVideo2,FullGameVideo,FullGameVideo2"
)
_REQUEST_TIMEOUT_SECONDS = 120
_PAGE_SIZE = 2500


@dataclass(frozen=True)
class GameRow:
    page_name: str
    date: str
    season: str
    opponent: str
    competition: str
    leg: str
    home_away: str
    maccabi_points: int
    opponent_points: int
    highlights: tuple[str, str]
    full_games: tuple[str, str]

    @property
    def is_home(self) -> bool:
        return self.home_away != "חוץ"


def _clean(value: object) -> str:
    return html.unescape(str(value)).strip() if value else ""


def _row_from_cargo(raw: dict) -> GameRow | None:
    if raw.get("TotalPointsMaccabi") in (None, "") or raw.get("TotalPointsOpponent") in (None, ""):
        return None  # a game with no score cannot be matched on one
    return GameRow(
        page_name=_clean(raw.get("_pageName")),
        date=_clean(raw.get("Date")),
        season=_clean(raw.get("Season")),
        opponent=_clean(raw.get("Opponent")),
        competition=_clean(raw.get("Competition")),
        leg=_clean(raw.get("Leg")),
        home_away=_clean(raw.get("HomeAway")),
        maccabi_points=int(raw["TotalPointsMaccabi"]),
        opponent_points=int(raw["TotalPointsOpponent"]),
        highlights=(_clean(raw.get("HighlightsVideo")), _clean(raw.get("HighlightsVideo2"))),
        full_games=(_clean(raw.get("FullGameVideo")), _clean(raw.get("FullGameVideo2"))),
    )


def _fetch_page(where: str | None, offset: int) -> list[dict]:
    params = {
        "title": "Special:CargoExport",
        "format": "json",
        "tables": _TABLE,
        "fields": _FIELDS,
        "limit": _PAGE_SIZE,
        "offset": offset,
    }
    if where:
        params["where"] = where
    response = requests.get(CARGO_EXPORT_URL, params=params, timeout=_REQUEST_TIMEOUT_SECONDS)
    if response.status_code != 200:
        raise RuntimeError(f"Cargo export failed with HTTP {response.status_code}: {response.text[:300]}")
    if "application/json" not in response.headers.get("Content-Type", ""):
        raise RuntimeError(f"Cargo export returned {response.headers.get('Content-Type')!r}, "
                           f"not JSON: {response.text[:300]}")
    return response.json()


def fetch_basketball_game_rows(seasons: list[str] | None = None) -> list[GameRow]:
    """Every scored basketball game, or only those of the given seasons."""
    where = None
    if seasons:
        quoted = ",".join(f"'{season}'" for season in seasons)
        where = f"Season IN ({quoted})"

    rows: list[GameRow] = []
    skipped_without_score = 0
    offset = 0
    while True:
        page = _fetch_page(where, offset)
        for raw in page:
            row = _row_from_cargo(raw)
            if row is None:
                skipped_without_score += 1
            else:
                rows.append(row)
        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    logger.info("Cargo: %d scored games%s (%d skipped for having no score)",
                len(rows), f" in {len(seasons)} seasons" if seasons else "", skipped_without_score)
    return rows
