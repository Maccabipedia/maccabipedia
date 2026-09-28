"""Tests for crawl_euroleague, which reads api-live.euroleague.net."""
import copy
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from maccabipediabot.basketball import crawl_euroleague
from maccabipediabot.basketball._crawler_utils import UnknownTeamNameError
from maccabipediabot.basketball.basketball_game import BasketballGame
from maccabipediabot.basketball.crawl_euroleague import (
    build_game,
    fetch_json,
    finished_maccabi_games,
    season_code_for,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _efes_game() -> dict:
    """API games-list entry for E2025 game 1: Anadolu Efes 85-78 Maccabi, 30/09/2025."""
    return _load("euroleague_api_game_E2025_1.json")


def _efes_boxscore() -> dict:
    return _load("euroleague_api_boxscore_E2025_1.json")


def test_build_game_matches_what_the_site_crawler_produced():
    """Parity with the old euroleaguebasketball.net crawler on the same game: every field and
    all 24 players' stats agree, except two fields where the API is the better source. The
    tip-off is 20:45 (the wiki page says 20:45; the site's data said 20:30), and the link has no
    "/en", like most stored game pages."""
    expected = BasketballGame.model_validate_json(
        (FIXTURES / "euroleague_game_E2025_R1.expected.json").read_text("utf-8")
    ).model_copy(update=dict(
        game_date=datetime(2025, 9, 30, 20, 45),
        game_url=["https://www.euroleaguebasketball.net/euroleague/game-center/2025-26/"
                  "anadolu-efes-istanbul-maccabi-rapyd-tel-aviv/E2025/1/"],
    ))
    assert build_game(_efes_game(), _efes_boxscore()).model_dump() == expected.model_dump()


def _as_maccabi_home(game: dict, boxscore: dict) -> tuple[dict, dict]:
    """The same game with the sides swapped, so Maccabi is the home (local) team."""
    game, boxscore = copy.deepcopy(game), copy.deepcopy(boxscore)
    game["local"], game["road"] = game["road"], game["local"]
    boxscore["local"], boxscore["road"] = boxscore["road"], boxscore["local"]
    return game, boxscore


def test_build_game_takes_maccabi_data_from_the_home_side_when_maccabi_hosts():
    away = build_game(_efes_game(), _efes_boxscore())
    home = build_game(*_as_maccabi_home(_efes_game(), _efes_boxscore()))
    assert home.home_team_name == "מכבי תל אביב"
    assert home.maccabi_players == away.maccabi_players
    assert home.maccabi_coach == away.maccabi_coach == "עודד קטש"
    assert home.first_quarter_maccabi_points == away.first_quarter_maccabi_points
    assert home.first_quarter_opponent_points == away.first_quarter_opponent_points


def test_build_game_reads_overtime_periods():
    game = _efes_game()
    game["road"]["partials"]["extraPeriods"] = {"1": 10, "2": 7}
    game["local"]["partials"]["extraPeriods"] = {"1": 10, "2": 5}
    built = build_game(game, _efes_boxscore())
    assert (built.first_overtime_maccabi_points, built.second_overtime_maccabi_points) == (10, 7)
    assert (built.first_overtime_opponent_points, built.second_overtime_opponent_points) == (10, 5)
    assert built.third_overtime_maccabi_points is None


def test_build_game_raises_on_unmapped_team_name():
    """An unmapped club would title the page in English; the error carries the game for CI."""
    game = _efes_game()
    game["local"]["club"]["name"] = "Totally New Club"
    with pytest.raises(UnknownTeamNameError) as exc_info:
        build_game(game, _efes_boxscore())
    assert exc_info.value.affected_games[0]["teams"] == ["Totally New Club"]
    assert exc_info.value.affected_games[0]["game"].endswith("/totally-new-club-maccabi-rapyd-tel-aviv/E2025/1/")


def test_build_game_raises_on_zero_zero_score():
    game = _efes_game()
    game["local"]["score"], game["road"]["score"] = 0, 0
    with pytest.raises(RuntimeError, match="0-0"):
        build_game(game, _efes_boxscore())


def _entry(game_code: int, utc: str, *, played: bool = True, local: str = "TEL", road: str = "ASV") -> dict:
    return {"gameCode": game_code, "utcDate": utc, "played": played,
            "local": {"club": {"code": local}}, "road": {"club": {"code": road}}}


_NOW = datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)


def test_finished_maccabi_games_keeps_played_maccabi_games_newest_first():
    games = [
        _entry(1, "2026-09-24T18:45:00Z", local="ASV", road="TEL"),   # played, away: keep
        _entry(2, "2026-10-02T18:00:00Z", played=False),              # not played yet: drop
        _entry(3, "2026-09-30T18:00:00Z", local="PAN", road="OLY"),   # not Maccabi: drop
        _entry(4, "2026-09-26T18:00:00Z"),                            # played, home: keep
    ]
    assert [g["gameCode"] for g in finished_maccabi_games(games, now=_NOW)] == [4, 1]
    assert [g["gameCode"] for g in finished_maccabi_games(games, limit=1, now=_NOW)] == [4]


def test_finished_maccabi_games_waits_out_a_game_in_progress():
    """`played` may flip on at tip-off; a page saved mid-game would never be corrected
    (the uploader skips existing pages), so wait until the game is surely over."""
    live = _entry(5, "2026-10-01T18:30:00Z")           # 1.5 h after tip-off
    over = _entry(6, "2026-10-01T16:59:00Z")           # just over 3 h
    assert [g["gameCode"] for g in finished_maccabi_games([live, over], now=_NOW)] == [6]


@pytest.mark.parametrize("today, expected", [
    (date(2026, 9, 28), "E2026"),
    (date(2027, 5, 20), "E2026"),   # Final Four time is still the season that began in 2026
    (date(2026, 6, 30), "E2025"),
    (date(2026, 7, 1), "E2026"),    # the API starts each season on July 1st
])
def test_season_code_for(today, expected):
    assert season_code_for(today) == expected


def test_fetch_json_raises_on_non_json_reply(monkeypatch):
    class _HtmlResp:
        status_code = 503
        headers = {"Content-Type": "text/html"}
        text = "<html>Service Unavailable</html>"

    monkeypatch.setattr(crawl_euroleague.requests, "get", lambda *args, **kwargs: _HtmlResp())
    with pytest.raises(RuntimeError, match="status=503"):
        fetch_json("https://api-live.euroleague.net/v2/competitions/E/seasons/E2026/games")
