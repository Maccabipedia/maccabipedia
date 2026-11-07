import pytest

from maccabipediabot.football.football_co_il_table import TEAM_ID_TO_HEBREW, TeamRow, league_table

# Round 10 of 2026/27 as football.co.il has it. Hapoel Petah Tikva - Maccabi Netanya ended 1:1
# on 10.10.2026; the IFA made it 3:0 to Netanya, and the site counts it. Ironi Tiberias' 6
# points taken off are in its points (penaltyPoints stays 0).
_ROUND_10 = [
    (4536, "Maccabi Tel Aviv FC", 10, 7, 3, 0, 31, 10, 24),
    (4530, "Hapoel Tel Aviv FC", 9, 7, 1, 1, 20, 6, 22),
    (4554, "Hapoel Be'er Sheva FC", 9, 7, 1, 1, 22, 12, 22),
    (4524, "Beitar Jerusalem FC", 10, 5, 3, 2, 14, 11, 18),
    (4539, "Maccabi Haifa FC", 10, 6, 0, 4, 21, 20, 18),
    (4545, "Maccabi Netanya FC", 10, 4, 4, 2, 16, 8, 16),
    (15960, "Ihoud Bnei Sakhnin FC", 10, 3, 4, 3, 8, 8, 13),
    (14316, "Hapoel Haifa FC", 10, 3, 3, 4, 13, 18, 12),
    (15006, "Maccabi Petah Tikva FC", 10, 3, 1, 6, 16, 23, 10),
    (7020, "Hapoel Jerusalem FC", 10, 2, 3, 5, 16, 23, 9),
    (4563, "Hapoel Ironi Kiryat Shmona FC", 10, 2, 1, 7, 9, 17, 7),
    (4542, "Hapoel Petah Tikva FC", 10, 2, 0, 8, 5, 17, 6),
    (4551, "Hapoel Ramat Gan Giv'atayim FC", 10, 2, 0, 8, 8, 22, 6),
    (12039, "Ironi Tiberias FC", 10, 2, 4, 4, 10, 14, 4),
]


def _row(team_id, name, played, win, draw, loss, goals_for, goals_against, points):
    return {"id": team_id, "name": name, "hebrewName": "", "gamesCount": played, "wins": win, "draws": draw,
            "losses": loss, "goalsScored": goals_for, "goalsReceived": goals_against, "points": points,
            "penaltyPoints": 0}


def _regular_season(rows=_ROUND_10):
    return {"RegularSeason": [_row(*row) for row in rows]}


def test_the_ruling_and_the_deduction_come_with_the_table():
    table = league_table(_regular_season())

    assert table[5] == TeamRow("מכבי נתניה", 10, 4, 4, 2, 16, 8, 16)
    assert table[11] == TeamRow("הפועל פתח תקווה", 10, 2, 0, 8, 5, 17, 6)
    assert table[13].as_template_row() == "עירוני טבריה^10^2^4^4^10^14^4"


def test_the_playoff_rounds_replace_the_regular_season_once_they_started():
    """2024/25: the championship round (6) and relegation round (8), full-season totals."""
    standings = _regular_season()
    standings["RelegationRound"] = [_row(*row[:2], 33, 11, 11, 11, 0, 0, 44) for row in _ROUND_10[6:]]
    standings["ChampionshipRound"] = [_row(*row[:2], 36, 24, 8, 4, 0, 0, 80) for row in _ROUND_10[:6]]

    table = league_table(standings)

    assert [row.name for row in table] == [TEAM_ID_TO_HEBREW[row[0]] for row in _ROUND_10]
    assert {row.played for row in table[:6]} == {36}


def test_playoff_rounds_without_games_are_ignored():
    standings = _regular_season()
    standings["ChampionshipRound"] = [_row(*row[:2], 0, 0, 0, 0, 0, 0, 0) for row in _ROUND_10[:6]]

    assert league_table(standings)[0].played == 10


def test_a_row_that_does_not_add_up_fails():
    """2025/26's archive: Maccabi Netanya with 98 games, in both playoff rounds."""
    rows = list(_ROUND_10)
    rows[5] = (4545, "מכבי נתניה", 98, 37, 16, 45, 0, 0, 127)

    with pytest.raises(ValueError, match="does not add up"):
        league_table(_regular_season(rows))


def test_a_team_twice_fails():
    with pytest.raises(ValueError, match="14 different teams"):
        league_table(_regular_season(_ROUND_10[:13] + [_ROUND_10[0]]))


def test_an_unknown_team_fails_by_name():
    rows = list(_ROUND_10)
    rows[13] = (99999, "Sektzia Nes Tziona FC", 10, 2, 4, 4, 10, 14, 10)

    with pytest.raises(ValueError, match="Sektzia Nes Tziona"):
        league_table(_regular_season(rows))
