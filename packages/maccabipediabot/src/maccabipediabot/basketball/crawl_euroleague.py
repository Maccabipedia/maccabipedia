"""Crawler for EuroLeague games, from EuroLeague's public data API (api-live.euroleague.net).

The consumer site (euroleaguebasketball.net) sits behind a Vercel bot challenge that has blocked
even the residential proxy since 2026-06; the API host has no such gate. A season takes one call
for its games list (scores, quarters, venue, crowd, referees) and one per game for the box score
(players, coaches).
"""
import argparse
import logging
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from maccabipediabot.basketball._crawler_utils import (
    UnknownTeamNameError,
    season_from_date,
    to_int,
    to_int_or_none,
    write_unknown_teams_report,
)
from maccabipediabot.basketball.basketball_game import BasketballGame, PlayerSummary
from maccabipediabot.basketball.translations import (
    is_known_team_name,
    person_name_to_hebrew,
    stadium_name_to_hebrew,
    team_name_to_hebrew,
)
from maccabipediabot.common.json_io import write_pydantic_list_as_json

logger = logging.getLogger(__name__)

API_BASE = "https://api-live.euroleague.net"
GAMES_URL = API_BASE + "/v2/competitions/E/seasons/{season_code}/games"
BOXSCORE_URL = API_BASE + "/v3/competitions/E/seasons/{season_code}/games/{game_code}/stats"
# The link the game page carries. Built from API fields; all 38 Maccabi games of 2025/26 match
# the path of the URL the old site crawler stored.
GAME_CENTER_URL = ("https://www.euroleaguebasketball.net/euroleague/game-center/"
                   "{alias}/{home_slug}-{away_slug}/{season_code}/{game_code}/")
MACCABI_CLUB_CODE = "TEL"  # the club code; the tvCode is "MTA"
COMPETITION_NAME_HE = "יורוליג"
ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")
# The API dates each season from July 1st ("startDate": "2026-07-01T00:00:00").
_SEASON_START_MONTH = 7


def season_code_for(today: date) -> str:
    """The API code of the season running on `today`, e.g. "E2026" for 2026/27."""
    start_year = today.year if today.month >= _SEASON_START_MONTH else today.year - 1
    return f"E{start_year}"


def fetch_json(url: str) -> Any:
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200 or "application/json" not in resp.headers.get("Content-Type", ""):
        raise RuntimeError(f"Unexpected EuroLeague API response for {url}: status={resp.status_code} "
                           f"ctype={resp.headers.get('Content-Type')}\n{resp.text[:300]}")
    return resp.json()


def _slug(name: str) -> str:
    """"LDLC ASVEL Villeurbanne" -> "ldlc-asvel-villeurbanne", as the site's game-center paths."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


def _flip_name(name: str) -> str:
    """Convert "LASTNAME, FIRSTNAME" → "Firstname Lastname"; titlecase as a courtesy."""
    if not name:
        return ""
    if "," in name:
        last, first = [part.strip() for part in name.split(",", 1)]
        return f"{first.title()} {last.title()}"
    return name.title()


def finished_maccabi_games(games: list[dict], limit: int | None = None) -> list[dict]:
    """Maccabi's played games from a season's games list, newest first, optionally the latest N."""
    finished = [game for game in games
                if game.get("played")
                and MACCABI_CLUB_CODE in (game["local"]["club"]["code"], game["road"]["club"]["code"])]
    finished.sort(key=lambda game: game["utcDate"], reverse=True)
    return finished[:limit] if limit else finished


def build_game(game: dict, boxscore: dict) -> BasketballGame:
    """A full BasketballGame from one games-list entry and that game's box score.

    RAISES on schema-drift signals (missing or 0-0 scores, missing team names) and on a club
    missing from translations._TEAM_NAMES — an unmapped name would title the page in English.
    """
    home, away = game["local"], game["road"]
    home_score, away_score = to_int_or_none(home.get("score")), to_int_or_none(away.get("score"))
    if home_score is None or away_score is None:
        raise RuntimeError(f"Finished EuroLeague game missing scores: {game.get('identifier')}")
    if home_score + away_score == 0:
        raise RuntimeError(f"Finished EuroLeague game has 0-0 score: {game.get('identifier')}")

    home_name = (home["club"].get("name") or "").strip()
    away_name = (away["club"].get("name") or "").strip()
    if not home_name or not away_name:
        raise RuntimeError(f"Finished EuroLeague game missing team name(s): {game.get('identifier')}")
    game_url = GAME_CENTER_URL.format(
        alias=game["season"]["alias"], home_slug=_slug(home_name), away_slug=_slug(away_name),
        season_code=game["season"]["code"], game_code=game["gameCode"])
    unmapped = [name for name in (home_name, away_name) if not is_known_team_name(name)]
    if unmapped:
        raise UnknownTeamNameError([{"game": game_url, "teams": unmapped, "date": game.get("utcDate")}])

    # The API's utcDate is UTC; the wiki keeps Israel local time, without tzinfo.
    game_dt = (datetime.fromisoformat(game["utcDate"].replace("Z", "+00:00"))
               .astimezone(ISRAEL_TZ).replace(tzinfo=None))
    fixture_round = to_int_or_none(game.get("round"))

    is_maccabi_home = home["club"]["code"] == MACCABI_CLUB_CODE
    home_box, away_box = boxscore["local"], boxscore["road"]
    maccabi, opponent = (home, away) if is_maccabi_home else (away, home)
    maccabi_box, opponent_box = (home_box, away_box) if is_maccabi_home else (away_box, home_box)
    maccabi_q, opponent_q = _quarters(maccabi.get("partials")), _quarters(opponent.get("partials"))
    main_referee, assistant_referees = _parse_referees(
        [game.get(f"referee{number}") for number in range(1, 5)])

    return BasketballGame(
        home_team_name=team_name_to_hebrew(home_name),
        away_team_name=team_name_to_hebrew(away_name),
        competition=COMPETITION_NAME_HE,
        fixture=f"מחזור {fixture_round}" if fixture_round is not None else "",
        game_date=game_dt,
        home_team_score=home_score,
        away_team_score=away_score,
        game_url=[game_url],
        arena=stadium_name_to_hebrew((game.get("venue") or {}).get("name") or ""),
        # 0 means "not published" (behind closed doors, or before the count is in): leave it empty.
        crowd=game.get("audience") or None,
        referee=main_referee,
        referee_assistants=assistant_referees,
        maccabi_coach=_coach(maccabi_box),
        opponent_coach=_coach(opponent_box),
        maccabi_players=_players(maccabi_box),
        opponent_players=_players(opponent_box),
        first_quarter_maccabi_points=maccabi_q.get("q1"),
        second_quarter_maccabi_points=maccabi_q.get("q2"),
        third_quarter_maccabi_points=maccabi_q.get("q3"),
        fourth_quarter_maccabi_points=maccabi_q.get("q4"),
        first_overtime_maccabi_points=maccabi_q.get("ot1"),
        second_overtime_maccabi_points=maccabi_q.get("ot2"),
        third_overtime_maccabi_points=maccabi_q.get("ot3"),
        fourth_overtime_maccabi_points=maccabi_q.get("ot4"),
        first_quarter_opponent_points=opponent_q.get("q1"),
        second_quarter_opponent_points=opponent_q.get("q2"),
        third_quarter_opponent_points=opponent_q.get("q3"),
        fourth_quarter_opponent_points=opponent_q.get("q4"),
        first_overtime_opponent_points=opponent_q.get("ot1"),
        second_overtime_opponent_points=opponent_q.get("ot2"),
        third_overtime_opponent_points=opponent_q.get("ot3"),
        fourth_overtime_opponent_points=opponent_q.get("ot4"),
        season=season_from_date(game_dt),
    )


def _quarters(partials: dict | None) -> dict[str, int | None]:
    """{"partials1": 19, ..., "extraPeriods": {"1": 10}} -> {"q1": 19, ..., "ot1": 10}."""
    partials = partials or {}
    quarters = {f"q{number}": to_int_or_none(partials.get(f"partials{number}")) for number in range(1, 5)}
    for period, points in (partials.get("extraPeriods") or {}).items():
        quarters[f"ot{period}"] = to_int_or_none(points)
    return quarters


def _coach(team_box: dict) -> str:
    return person_name_to_hebrew(_flip_name((team_box.get("coach") or {}).get("name") or ""))


def _parse_referees(referees: list[dict | None]) -> tuple[str, list[str]]:
    names_he = [person_name_to_hebrew(_flip_name(ref["name"])) for ref in referees if ref and ref.get("name")]
    if not names_he:
        return "", []
    return names_he[0], names_he[1:]


def _players(team_box: dict) -> list[PlayerSummary]:
    """The team's players by shirt number, as the site listed them (unnumbered last)."""
    players = [_to_player(entry) for entry in team_box.get("players") or []]
    return sorted(players, key=lambda player: (player.number is None, player.number or 0))


def _to_player(entry: dict) -> PlayerSummary:
    player, stats = entry.get("player") or {}, entry.get("stats") or {}
    return PlayerSummary(
        name=person_name_to_hebrew(_flip_name((player.get("person") or {}).get("name") or "")),
        number=to_int_or_none(player.get("dorsal")),
        is_starting_five=bool(stats.get("startFive")),
        minutes_played=_seconds_to_minutes(stats.get("timePlayed")),
        total_points=to_int(stats.get("points")),
        field_goals_attempts=to_int(stats.get("fieldGoalsAttempted2")),
        field_goals_scored=to_int(stats.get("fieldGoalsMade2")),
        three_scores_attempts=to_int(stats.get("fieldGoalsAttempted3")),
        three_scores_scored=to_int(stats.get("fieldGoalsMade3")),
        free_throws_attempts=to_int(stats.get("freeThrowsAttempted")),
        free_throws_scored=to_int(stats.get("freeThrowsMade")),
        defensive_rebounds=to_int(stats.get("defensiveRebounds")),
        offensive_rebounds=to_int(stats.get("offensiveRebounds")),
        total_rebounds=to_int(stats.get("totalRebounds")),
        assists=to_int(stats.get("assistances")),
        steals=to_int(stats.get("steals")),
        turnovers=to_int(stats.get("turnovers")),
        blocks=to_int(stats.get("blocksFavour")),
        # The API spells it "foulsCommited"; tolerate the correct spelling too.
        personal_total_fouls=to_int(stats.get("foulsCommited") or stats.get("foulsCommitted")),
    )


def _seconds_to_minutes(seconds) -> int | None:
    """Convert timePlayed (seconds) → whole minutes (round up if any seconds played)."""
    if seconds is None:
        return None
    try:
        s = int(seconds)
    except (TypeError, ValueError):
        return None
    if s <= 0:
        return 0
    return s // 60 + (1 if s % 60 else 0)


def _run_latest_season(limit: int | None) -> list[BasketballGame]:
    season_code = season_code_for(date.today())
    games = finished_maccabi_games(fetch_json(GAMES_URL.format(season_code=season_code))["data"], limit)
    logger.info("Discovered %d EuroLeague games in %s", len(games), season_code)
    return [build_game(game, fetch_json(BOXSCORE_URL.format(season_code=season_code,
                                                            game_code=game["gameCode"])))
            for game in games]


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl the EuroLeague data API for Maccabi games.")
    parser.add_argument("--season", choices=("latest",), default="latest")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--unknown-teams-report", type=Path, default=None,
                        help="On unmapped team names, write the affected games as JSON here "
                             "(consumed by CI to alert the error channel).")
    args = parser.parse_args()

    try:
        games = _run_latest_season(args.limit)
    except UnknownTeamNameError as error:
        write_unknown_teams_report(args.unknown_teams_report, error.affected_games)
        raise

    write_pydantic_list_as_json(games, args.output)


if __name__ == "__main__":
    logging.basicConfig(format="%(asctime)s : %(levelname)s : %(message)s", level=logging.INFO)
    main()
