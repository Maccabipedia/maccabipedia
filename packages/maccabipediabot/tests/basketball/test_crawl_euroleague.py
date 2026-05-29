"""Parser tests for crawl_euroleague."""
from datetime import datetime
from pathlib import Path

import pytest

from maccabipediabot.basketball._crawler_utils import UnknownTeamNameError
from maccabipediabot.basketball.basketball_game import BasketballGame
from maccabipediabot.basketball.crawl_euroleague import (
    MACCABI_TEAM_NAME_ENG,
    _parse_team_results_entry,
    discover_games_from_html,
    extract_next_data,
    parse_game_page,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _partial_game_anadolu_efes() -> BasketballGame:
    """The discovery-stage BasketballGame for fixture E2025 R1
    (Anadolu Efes home vs Maccabi away, 30/09/2025)."""
    return BasketballGame(
        home_team_name="אנאדולו אפס",
        away_team_name="מכבי תל אביב",
        competition="יורוליג",
        fixture="מחזור 1",
        game_date=datetime(2025, 9, 30, 20, 30),
        home_team_score=85,
        away_team_score=78,
        game_url=["https://www.euroleaguebasketball.net/en/euroleague/game-center/2025-26/anadolu-efes-istanbul-maccabi-rapyd-tel-aviv/E2025/1/"],
    )


def test_parse_game_page_against_real_fixture():
    """Round-trip the captured Euroleague game-center page against a hand-verified
    expected BasketballGame snapshot. One assert covers everything."""
    html = (FIXTURES / "euroleague_game_E2025_R1.html").read_bytes().decode("utf-8")
    expected = BasketballGame.model_validate_json(
        (FIXTURES / "euroleague_game_E2025_R1.expected.json").read_text("utf-8")
    )
    actual = parse_game_page(extract_next_data(html), _partial_game_anadolu_efes())
    assert actual.model_dump() == expected.model_dump()


def test_extract_next_data_raises_when_script_missing():
    with pytest.raises(RuntimeError, match="missing __NEXT_DATA__"):
        extract_next_data("<html><body>no script here</body></html>")


# ---------------------------------------------------------------------------
# Synthetic __NEXT_DATA__ — covers the home/away swap + overtime branches
# that the real fixture (Maccabi-away, regulation) doesn't exercise.
# ---------------------------------------------------------------------------

def _synthetic_next_data(*, home_quarters: dict, away_quarters: dict) -> dict:
    return {
        "props": {"pageProps": {"mappedData": {"rawGameInfo": {
            "venue": {"name": "MENORA MIVTACHIM ARENA"},
            "audience": 11000,
            "referees": [{"name": "JAVOR, DAMIR"}],
            "home": {
                "name": MACCABI_TEAM_NAME_ENG,
                "coach": {"name": "KATTASH, ODED"},
                "quarters": home_quarters,
                "players": [{"name": "BRODY, TAL", "dorsal": "5", "startFive": True,
                             "stats": {"timePlayed": 1800, "points": 22}}],
            },
            "away": {
                "name": "Olympiacos Piraeus",
                "coach": {"name": "BARTZOKAS, GEORGIOS"},
                "quarters": away_quarters,
                "players": [{"name": "SPIEGLER, MOTI", "dorsal": "9", "startFive": True,
                             "stats": {"timePlayed": 1700, "points": 18}}],
            },
        }}}},
    }


def _maccabi_home_partial_game() -> BasketballGame:
    return BasketballGame(
        home_team_name="מכבי תל אביב",
        away_team_name="אולימפיאקוס",
        competition="יורוליג",
        fixture="מחזור 7",
        game_date=datetime(2025, 11, 1, 20, 30),
        home_team_score=85,
        away_team_score=80,
        game_url=["https://www.euroleaguebasketball.net/test-game/"],
    )


def test_parse_game_page_swaps_home_data_to_maccabi_when_maccabi_is_home():
    next_data = _synthetic_next_data(
        home_quarters={"q1": 22, "q2": 21, "q3": 20, "q4": 22, "ot1": None, "ot2": None,
                       "ot3": None, "ot4": None, "ot5": None},
        away_quarters={"q1": 18, "q2": 19, "q3": 22, "q4": 21, "ot1": None, "ot2": None,
                       "ot3": None, "ot4": None, "ot5": None},
    )
    game = parse_game_page(next_data, _maccabi_home_partial_game())
    assert game.home_team_name == "מכבי תל אביב"
    assert game.first_quarter_maccabi_points == 22  # home values mapped to maccabi_*
    assert game.first_quarter_opponent_points == 18  # away values mapped to opponent_*
    assert any(player.number == 5 for player in game.maccabi_players)  # home player
    assert any(player.number == 9 for player in game.opponent_players)  # away player
    assert game.maccabi_coach == "עודד קטש"


def test_parse_game_page_extracts_overtime_periods():
    next_data = _synthetic_next_data(
        home_quarters={"q1": 25, "q2": 22, "q3": 18, "q4": 20, "ot1": 12, "ot2": 8,
                       "ot3": None, "ot4": None, "ot5": None},
        away_quarters={"q1": 24, "q2": 23, "q3": 19, "q4": 19, "ot1": 10, "ot2": 9,
                       "ot3": None, "ot4": None, "ot5": None},
    )
    game = parse_game_page(next_data, _maccabi_home_partial_game())
    assert (game.first_overtime_maccabi_points, game.second_overtime_maccabi_points,
            game.third_overtime_maccabi_points) == (12, 8, None)
    assert (game.first_overtime_opponent_points, game.second_overtime_opponent_points,
            game.third_overtime_opponent_points) == (10, 9, None)


# ---------------------------------------------------------------------------
# Discovery (fixture-based; no HTTP)
# ---------------------------------------------------------------------------

def test_discover_games_from_team_results_returns_finished_games_sorted_desc():
    html = (FIXTURES / "euroleague_team_results.html").read_bytes().decode("utf-8")
    discovered = discover_games_from_html(html, limit=5)
    assert 1 <= len(discovered) <= 5
    for game in discovered:
        assert game.game_url[0].startswith("https://www.euroleaguebasketball.net/")
        # Either home or away is Maccabi
        assert "מכבי תל אביב" in (game.home_team_name, game.away_team_name)
    for earlier, later in zip(discovered[1:], discovered[:-1]):
        assert later.game_date >= earlier.game_date


def test_parse_entry_raises_on_unmapped_team_name():
    """A team name missing from _TEAM_NAMES would leak English into the page title;
    discovery must raise with the affected game so CI can alert."""
    result = {
        "status": "result",
        "date": "2026-01-15T18:05:00Z",
        "url": "/en/euroleague/game-center/2025-26/maccabi-vs-new-club/E2025/20/",
        "round": {"round": 20},
        "home": {"name": MACCABI_TEAM_NAME_ENG, "score": 90},
        "away": {"name": "Totally New Club", "score": 80},
    }
    with pytest.raises(UnknownTeamNameError) as exc_info:
        _parse_team_results_entry(result)
    assert exc_info.value.affected_games[0]["teams"] == ["Totally New Club"]
