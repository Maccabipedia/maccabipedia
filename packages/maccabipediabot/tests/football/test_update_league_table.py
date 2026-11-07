from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from maccabipediabot.football import update_league_table
from maccabipediabot.football.football_co_il_table import TeamRow

_SAVED_ROWS = """מכבי תל אביב^10^7^3^0^31^10^24,
הפועל תל אביב^9^7^1^1^20^6^22,
עירוני טבריה^10^2^4^4^10^14^4
"""


def test_games_played_on_the_wiki():
    assert update_league_table.games_played_on_the_wiki(_SAVED_ROWS) == {
        "מכבי תל אביב": 10, "הפועל תל אביב": 9, "עירוני טבריה": 10}


def test_a_table_with_fewer_games_than_the_wiki_is_not_saved():
    """football.co.il's 2025/26 archive has an all-zero regular season."""
    zeros = [TeamRow("מכבי תל אביב", 0, 0, 0, 0, 0, 0, 0)]

    with pytest.raises(ValueError, match="fewer games than the wiki"):
        update_league_table.check_against_the_wiki(zeros, {"מכבי תל אביב": 10})


def test_a_new_round_is_saved():
    update_league_table.check_against_the_wiki([TeamRow("מכבי תל אביב", 11, 8, 3, 0, 33, 10, 27)],
                                               {"מכבי תל אביב": 10})


def test_a_new_season_page_with_no_rows_is_saved():
    update_league_table.check_against_the_wiki([TeamRow("הפועל חדרה", 1, 1, 0, 0, 1, 0, 3)], {})


def test_teams_that_are_not_on_the_wiki_fail():
    """A name spelled differently would otherwise pass the games check unchecked."""
    with pytest.raises(ValueError, match="different teams"):
        update_league_table.check_against_the_wiki([TeamRow("הפועל חדרה", 11, 1, 0, 10, 1, 30, 3)],
                                                   {"מכבי תל אביב": 10})


def test_a_livescore_answer_without_games_fails():
    response = MagicMock()
    response.json.return_value = {"Stages": [{"LeagueTable": {}}]}

    with patch.object(update_league_table.requests, "get", return_value=response):
        with pytest.raises(RuntimeError, match="no games list"):
            update_league_table.a_game_is_in_play()


def test_no_table_while_a_game_is_in_play():
    """2026-10-17: a run at 21:08 saved Maccabi Haifa a win in a game that ended at 21:26."""
    response = MagicMock()
    response.json.return_value = {"Stages": [{
        "Events": [{"Eps": "80'", "Epr": 1, "Esd": int(date.today().strftime("%Y%m%d") + "193000"),
                    "T1": [{"Nm": "Maccabi Petach Tikva"}], "T2": [{"Nm": "Maccabi Haifa"}]}],
    }]}

    with patch.object(update_league_table.requests, "get", return_value=response), \
            patch.object(update_league_table, "fetch_standings") as fetch_standings:
        update_league_table.update_league_table_status()

    fetch_standings.assert_not_called()
