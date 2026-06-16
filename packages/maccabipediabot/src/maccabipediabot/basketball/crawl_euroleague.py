"""Crawler for euroleaguebasketball.net.

Parses the server-injected __NEXT_DATA__ JSON on each page; no DOM scraping
or headless browser.
"""
import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

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


class EuroleagueBlockedError(Exception):
    """The Euroleague site is unreachable or gating us behind a bot challenge.

    Raised for transient, environmental conditions — the Vercel WAF serving its JS
    "Security Checkpoint" to a flagged (residential) IP, or the proxy/network path
    being down — as opposed to a real parsing bug or an unmapped team name. The
    scheduled CI job soft-fails on this (see ``--soft-fail-on-block``) so a challenged
    IP doesn't turn the run red, most notably during the Euroleague off-season when
    there are no games to miss anyway.
    """

TEAM_RESULTS_URL = (
    "https://www.euroleaguebasketball.net/en/euroleague/teams/maccabi-rapyd-tel-aviv/games/tel/"
)
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
COMPETITION_NAME_HE = "יורוליג"
MACCABI_TEAM_NAME_ENG = "Maccabi Rapyd Tel Aviv"
GAME_URL_PREFIX = "https://www.euroleaguebasketball.net"
ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")


def extract_next_data(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.select_one("script#__NEXT_DATA__")
    if not script:
        raise RuntimeError("page is missing __NEXT_DATA__ script")
    return json.loads(script.text)


def fetch_html(url: str) -> str:
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=30)
    except requests.exceptions.RequestException as error:
        # Proxy unreachable / connection reset / timeout — the residential proxy or the
        # network path to Euroleague is down. Environmental, not a bug.
        raise EuroleagueBlockedError(f"Could not reach Euroleague ({url}): {error}") from error
    if resp.status_code == 429 and resp.headers.get("x-vercel-mitigated") == "challenge":
        # Vercel's WAF is serving its JS "Security Checkpoint" instead of the page; a
        # headless client can't solve it. IP-reputation based, not a header/UA issue.
        raise EuroleagueBlockedError(
            f"Euroleague returned a Vercel bot challenge (HTTP 429) for {url}"
        )
    resp.raise_for_status()
    return resp.text


def _flip_name(name: str) -> str:
    """Convert "LASTNAME, FIRSTNAME" → "Firstname Lastname"; titlecase as a courtesy."""
    if not name:
        return ""
    if "," in name:
        last, first = [part.strip() for part in name.split(",", 1)]
        return f"{first.title()} {last.title()}"
    return name.title()


def parse_game_page(next_data: dict, partial_game: BasketballGame) -> BasketballGame:
    """Enrich a partially-built BasketballGame (from discovery) with per-game data
    from the Euroleague game-center page's __NEXT_DATA__ JSON.

    Returns a new BasketballGame; does not mutate the input.
    """
    raw = next_data["props"]["pageProps"]["mappedData"]["rawGameInfo"]
    home, away = raw["home"], raw["away"]
    is_maccabi_home = partial_game.home_team_name == "מכבי תל אביב"

    home_coach = person_name_to_hebrew(_flip_name((home.get("coach") or {}).get("name") or ""))
    away_coach = person_name_to_hebrew(_flip_name((away.get("coach") or {}).get("name") or ""))
    home_players = [_to_player(player_data) for player_data in home.get("players") or []]
    away_players = [_to_player(player_data) for player_data in away.get("players") or []]

    if is_maccabi_home:
        maccabi_players, opponent_players = home_players, away_players
        maccabi_coach, opponent_coach = home_coach, away_coach
        maccabi_q, opponent_q = home.get("quarters") or {}, away.get("quarters") or {}
    else:
        maccabi_players, opponent_players = away_players, home_players
        maccabi_coach, opponent_coach = away_coach, home_coach
        maccabi_q, opponent_q = away.get("quarters") or {}, home.get("quarters") or {}

    main_referee, assistant_referees = _parse_referees(raw.get("referees") or [])
    venue_name = stadium_name_to_hebrew((raw.get("venue") or {}).get("name") or "")

    return partial_game.model_copy(update=dict(
        arena=venue_name,
        # Euroleague reports audience=0 when attendance is unavailable (e.g. behind-closed-doors
        # games, or preliminary data before a venue count is published). Treat 0 as "unknown" so
        # the wiki field renders empty instead of a misleading literal zero.
        crowd=raw.get("audience") or None,
        referee=main_referee,
        referee_assistants=assistant_referees,
        maccabi_coach=maccabi_coach,
        opponent_coach=opponent_coach,
        maccabi_players=maccabi_players,
        opponent_players=opponent_players,
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
        season=season_from_date(partial_game.game_date),
    ))


def _parse_referees(referees: list[dict]) -> tuple[str, list[str]]:
    names_he = [person_name_to_hebrew(_flip_name(ref.get("name") or "")) for ref in referees if ref.get("name")]
    if not names_he:
        return "", []
    return names_he[0], names_he[1:]


def _to_player(p: dict) -> PlayerSummary:
    stats = p.get("stats") or {}
    raw_name = p.get("name") or ""
    name = person_name_to_hebrew(_flip_name(raw_name))
    return PlayerSummary(
        name=name,
        number=to_int_or_none(p.get("dorsal")),
        is_starting_five=bool(p.get("startFive")),
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
        assists=to_int(stats.get("assists")),
        steals=to_int(stats.get("steals")),
        turnovers=to_int(stats.get("turnovers")),
        blocks=to_int(stats.get("blocksFavour")),
        # Euroleague stat key has a typo; tolerate either spelling.
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


def discover_games_from_html(html: str, limit: int | None = None) -> list[BasketballGame]:
    """Parse the team-results page HTML and return finished Maccabi games.

    The page is a Next.js render with the team-results data embedded as JSON
    in <script id="__NEXT_DATA__">. We navigate:

        props.pageProps.results.results: list[result]

    Each `result` looks like:
        {
          "status": "result",            # we keep "result" / "finished"; everything else is unplayed
          "date": "2026-04-16T18:05:00Z", # ISO UTC; converted to Israel local time
          "url":  "/en/euroleague/game-center/...",
          "round": {"round": 38, ...},
          "home":  {"name": "Maccabi Rapyd Tel Aviv", "score": 85},
          "away":  {"name": "Virtus Bologna",         "score": 89},
        }

    Returns games sorted by date descending; optionally capped at the most-recent N.
    """
    data = extract_next_data(html)
    results = data["props"]["pageProps"]["results"]["results"]

    discovered = [
        game for result in results
        if (game := _parse_team_results_entry(result)) is not None
    ]
    discovered.sort(key=lambda game: game.game_date, reverse=True)
    if limit:
        discovered = discovered[:limit]
    return discovered


def _parse_team_results_entry(result: dict) -> BasketballGame | None:
    """Parse one team-results entry into a partial BasketballGame.

    Returns None for legitimately-skipped entries (games that haven't been
    played yet). RAISES on schema-drift signals (missing scores / team names /
    URL on what otherwise looks like a finished game) — those are bugs upstream,
    not games to silently drop.
    """
    status = (result.get("status") or "").lower()
    if status not in {"result", "finished"} and not result.get("isPreviousGame"):
        return None  # not a finished game — silent drop

    date_str = result.get("date") or ""
    # Euroleague feed timestamps are in UTC. Convert to Israel local time
    # (matches the wiki convention) and drop tzinfo for the BasketballGame model.
    game_dt = (
        datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        .astimezone(ISRAEL_TZ)
        .replace(tzinfo=None)
    )

    home, away = result.get("home") or {}, result.get("away") or {}
    home_score = to_int_or_none(home.get("score"))
    away_score = to_int_or_none(away.get("score"))
    if home_score is None or away_score is None:
        raise RuntimeError(f"Finished Euroleague game missing scores: {result!r}")
    if home_score + away_score == 0:
        # Defense in depth: a real basketball game can't end 0-0. status="result"
        # *should* gate this, but raise loudly if Euroleague ever ships a
        # placeholder row that satisfies the status filter.
        raise RuntimeError(f"Finished Euroleague game has 0-0 score: {result!r}")

    home_name = (home.get("name") or "").strip()
    away_name = (away.get("name") or "").strip()
    if not home_name or not away_name:
        raise RuntimeError(f"Finished Euroleague game missing team name(s): {result!r}")

    unmapped = [name for name in (home_name, away_name) if not is_known_team_name(name)]
    if unmapped:
        # Same leak as basket.co.il: an unmapped name would pass through
        # team_name_to_hebrew() and title the page in English. Fail loudly with the
        # affected game so CI can alert; foreign Euroleague clubs churn yearly.
        raise UnknownTeamNameError(
            [{"game": result.get("url"), "teams": unmapped, "date": date_str}]
        )

    url_path = result.get("url") or ""
    if not url_path:
        raise RuntimeError(f"Finished Euroleague game missing URL: {result!r}")
    scrape_url = url_path if url_path.startswith("http") else f"{GAME_URL_PREFIX}{url_path}"

    fixture_round = to_int_or_none((result.get("round") or {}).get("round"))

    return BasketballGame(
        home_team_name=team_name_to_hebrew(home_name),
        away_team_name=team_name_to_hebrew(away_name),
        competition=COMPETITION_NAME_HE,
        fixture=f"מחזור {fixture_round}" if fixture_round is not None else "",
        game_date=game_dt,
        home_team_score=home_score,
        away_team_score=away_score,
        game_url=[scrape_url],
    )


def _run_latest_season(limit: int | None) -> list[BasketballGame]:
    discovered = discover_games_from_html(fetch_html(TEAM_RESULTS_URL), limit=limit)
    logger.info("Discovered %d Euroleague games", len(discovered))
    return [parse_game_page(extract_next_data(fetch_html(partial_game.game_url[0])), partial_game)
            for partial_game in discovered]


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl euroleaguebasketball.net for Maccabi games.")
    parser.add_argument("--season", choices=("latest",), default="latest")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--unknown-teams-report", type=Path, default=None,
                        help="On unmapped team names, write the affected games as JSON here "
                             "(consumed by CI to alert the error channel).")
    parser.add_argument("--soft-fail-on-block", action="store_true",
                        help="If Euroleague is unreachable or behind a Vercel bot challenge, "
                             "write an empty result and exit 0 instead of failing. Used by the "
                             "scheduled CI job so a challenged residential IP — common in the "
                             "off-season — doesn't turn the run red.")
    args = parser.parse_args()

    try:
        games = _run_latest_season(args.limit)
    except UnknownTeamNameError as error:
        write_unknown_teams_report(args.unknown_teams_report, error.affected_games)
        raise
    except EuroleagueBlockedError as error:
        if not args.soft_fail_on_block:
            raise
        logger.warning("Euroleague crawl skipped — site blocked: %s", error)
        games = []

    write_pydantic_list_as_json(games, args.output)


if __name__ == "__main__":
    logging.basicConfig(format="%(asctime)s : %(levelname)s : %(message)s", level=logging.INFO)
    main()
