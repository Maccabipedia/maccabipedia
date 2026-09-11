from unittest.mock import MagicMock, patch

from maccabipediabot.football import update_league_table


def _team_row(name, win, drw, ptsn):
    return {
        "Tnm": name,
        "pld": win + drw,
        "winn": str(win),
        "drwn": str(drw),
        "lstn": "0",
        "gf": 0,
        "ga": 0,
        "ptsn": str(ptsn),
        "win": win,
        "drw": drw,
    }


def _fake_response(rows):
    response = MagicMock()
    response.json.return_value = {
        "Stages": [{"LeagueTable": {"L": [{"Tables": [{"team": rows}]}]}}]
    }
    return response


def test_deducted_team_sorts_below_teams_with_more_points():
    # livescore returns teams sorted by its own (undeducted) points - Ironi
    # Tiberias sits 2nd here on its raw 3 points, ignoring the 6-point deduction.
    rows = [
        _team_row("Maccabi Haifa", win=2, drw=0, ptsn=6),
        _team_row("Ironi Tiberias", win=1, drw=0, ptsn=3),
        _team_row("Bnei Sakhnin", win=0, drw=1, ptsn=1),
        _team_row("Beitar Jerusalem", win=0, drw=0, ptsn=0),
    ]

    with patch.object(update_league_table.requests, "get", return_value=_fake_response(rows)):
        result = update_league_table.fetch_league_table_data()

    team_names_in_order = [line.split("^")[0] for line in result.split(",\n")]
    assert team_names_in_order == [
        "מכבי חיפה",
        "בני סכנין",
        "בית\"ר ירושלים",
        "עירוני טבריה",
    ]
