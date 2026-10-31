from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from maccabipediabot.football import update_league_table
from maccabipediabot.football.wikipedia_league_table import TeamRow

# Hapoel Petah Tikva - Maccabi Netanya ended 1:1 on 10.10.2026; the IFA made it 3:0 to Netanya
# on 28.10. Wikipedia applied the ruling the same day, livescore never did.
_NETANYA_WIKIPEDIA = TeamRow("מכבי נתניה", 3, 3, 2, 11, 7, 12)
_HPT_WIKIPEDIA = TeamRow("הפועל פתח תקווה", 1, 0, 7, 2, 14, 3)
_NETANYA_LIVESCORE = TeamRow("מכבי נתניה", 2, 4, 2, 9, 8, 10)
_HPT_LIVESCORE = TeamRow("הפועל פתח תקווה", 1, 1, 6, 3, 12, 4)


def _livescore(*rows):
    return {row.name: row for row in rows}


def test_the_ruling_comes_from_wikipedia():
    merged = update_league_table.merge_tables([_NETANYA_WIKIPEDIA, _HPT_WIKIPEDIA],
                                              _livescore(_NETANYA_LIVESCORE, _HPT_LIVESCORE))

    assert merged == [_NETANYA_WIKIPEDIA, _HPT_WIKIPEDIA]


def test_goals_come_from_livescore_when_the_results_agree():
    """2025-26: Wikipedia counted Maccabi Tel Aviv's technical win but not its 3 goals."""
    wikipedia = TeamRow("מכבי תל אביב", 19, 9, 8, 72, 46, 66)
    livescore = TeamRow("מכבי תל אביב", 19, 9, 8, 75, 46, 66)

    assert update_league_table.merge_tables([wikipedia], _livescore(livescore)) == [livescore]


def test_no_table_while_wikipedia_is_a_game_behind():
    wikipedia_before_the_game = TeamRow("מכבי נתניה", 2, 3, 2, 8, 7, 9)

    assert update_league_table.merge_tables([wikipedia_before_the_game, _HPT_WIKIPEDIA],
                                            _livescore(_NETANYA_LIVESCORE, _HPT_LIVESCORE)) is None


def test_wikipedia_two_games_behind_fails_the_run():
    wikipedia_abandoned = TeamRow("מכבי נתניה", 2, 2, 2, 8, 7, 8)

    with pytest.raises(RuntimeError, match="behind"):
        update_league_table.merge_tables([wikipedia_abandoned, _HPT_WIKIPEDIA],
                                         _livescore(_NETANYA_LIVESCORE, _HPT_LIVESCORE))


def test_different_teams_fail_the_run():
    with pytest.raises(ValueError, match="different teams"):
        update_league_table.merge_tables([_NETANYA_WIKIPEDIA], _livescore(_HPT_LIVESCORE))


def test_no_table_while_a_game_is_in_play():
    """2026-10-17: a run at 21:08 saved Maccabi Haifa a win in a game that ended at 21:26."""
    response = MagicMock()
    response.json.return_value = {"Stages": [{
        "LeagueTable": {"L": [{"Tables": [{"team": []}]}]},
        "Events": [{"Eps": "80'", "Epr": 1, "Esd": int(date.today().strftime("%Y%m%d") + "193000"),
                    "T1": [{"Nm": "Maccabi Petach Tikva"}], "T2": [{"Nm": "Maccabi Haifa"}]}],
    }]}

    with patch.object(update_league_table.requests, "get", return_value=response):
        assert update_league_table.fetch_league_table_data() is None
