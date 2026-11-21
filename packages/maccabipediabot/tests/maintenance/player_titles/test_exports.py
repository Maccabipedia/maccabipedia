"""Cargo exports that refuse to come back short, repeated or HTML-encoded."""
import pytest

from maccabipediabot.maintenance.football.player_titles.exports import (
    ExportError,
    cargo_rows,
    competition_kinds,
    seasons_played,
    won_titles,
)
from maccabipediabot.maintenance.football.player_titles.rule import SeasonPlayed, Title

from .fakes import FakeCargoApi

SEASONS_TABLES = "Football_Games=g, Games_Events=e, Competitions=c"


def export(api: FakeCargoApi) -> list[dict]:
    return cargo_rows(
        api, key=("Season", "Competition"), count_field="COUNT(*)=n",
        tables="Achievements", fields="Season, Competition", order_by="Season, Competition",
    )


def test_pages_until_a_short_page():
    rows = [{"Season": f"{1900 + index}", "Competition": "ליגת העל"} for index in range(501)]
    api = FakeCargoApi({"Achievements": rows})

    assert export(api) == rows
    assert [(call["offset"], call["limit"]) for call in api.data_calls()] == [(0, 500), (500, 500)]


def test_values_are_unescaped():
    api = FakeCargoApi({"Achievements": [{"Season": "1941/42", "Competition": "גביע &quot;המלחמה&quot; &amp; עוד"}]})

    assert export(api) == [{"Season": "1941/42", "Competition": 'גביע "המלחמה" & עוד'}]


def test_a_short_export_raises():
    rows = [{"Season": "2000/01", "Competition": "גביע המדינה"}, {"Season": "2002/03", "Competition": "ליגת העל"}]
    api = FakeCargoApi({"Achievements": rows}, counts={"Achievements": 3})

    with pytest.raises(ExportError, match="2 rows.*3"):
        export(api)


def test_a_repeated_key_raises():
    row = {"Season": "2000/01", "Competition": "גביע המדינה"}
    api = FakeCargoApi({"Achievements": [row, dict(row)]})

    with pytest.raises(ExportError, match="2000/01"):
        export(api)


def test_the_count_query_drops_grouping_and_ordering():
    api = FakeCargoApi({"Achievements": []})

    cargo_rows(api, key=("Season",), count_field="COUNT(*)=n", tables="Achievements",
               fields="Season", group_by="Season", order_by="Season", where="1=1")

    count_call = next(call for call in api.calls if call["fields"] == "COUNT(*)=n")
    assert "group_by" not in count_call and "order_by" not in count_call
    assert count_call["where"] == "1=1"


def test_won_titles_asks_for_wins_only():
    api = FakeCargoApi({"Achievements": [{"Season": "2000/01", "Competition": "גביע המדינה"}]})

    assert won_titles(api) == [Title("2000/01", "גביע המדינה")]
    assert api.data_calls()[0]["where"] == 'Achievement IN ("זכיה", "מקום 1")'


def test_seasons_played_reads_maccabi_game_sheets_through_the_competitions_join():
    api = FakeCargoApi({SEASONS_TABLES: [{"Player": "אמנון חרל&quot;פ", "Season": "1955/56"}]})

    assert seasons_played(api) == [SeasonPlayed('אמנון חרל"פ', "1955/56")]
    query = api.data_calls()[0]
    assert query["where"] == "e.Team=1"
    assert query["join_on"] == "g._pageID=e._pageID, g.Competition=c.OriginalName"
    assert query["group_by"] == "e.PlayerName, g.Season"


def test_competition_kinds():
    api = FakeCargoApi({"Competitions": [
        {"OriginalName": "ליגת העל", "CurrentName": "ליגת העל", "League": "1", "Trophy": "0"},
        {"OriginalName": "גביע המדינה", "CurrentName": "גביע המדינה", "League": "0", "Trophy": "1"},
        {"OriginalName": "גביע הטוטו לליגת העל", "CurrentName": "גביע הטוטו", "League": "0", "Trophy": "0"},
        {"OriginalName": "אלוף האלופים", "CurrentName": "", "League": "0", "Trophy": "0"},
    ]})

    kinds = competition_kinds(api)

    assert kinds["ליגה"] == {"ליגת העל"}
    assert kinds["גביע"] == {"גביע המדינה"}
    assert kinds["גביע הטוטו"] == {"גביע הטוטו לליגת העל"}
    assert kinds["אלוף האלופים"] == {"אלוף האלופים"}
    assert kinds["גביע ליליאן"] == set() and kinds["גביע אסיה לאלופות"] == set()
