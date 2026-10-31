import pytest

from maccabipediabot.football.wikipedia_league_table import TeamRow, parse_league_tables

# Shapes taken from the real season pages: the regular season inside <onlyinclude> with
# team_order= (2026-27), a relegation round numbered team7.. out of order (2025-26), and a
# deduction written with a Unicode minus.
_SEASON_PAGE = """
===Regular season table===
<onlyinclude>{{#invoke:Sports table|main|style=WDL
|section=Regular season
|team_order = MNE,HPT
|win_HPT=1 |draw_HPT=0 |loss_HPT=7 |gf_HPT=2 |ga_HPT=14<!-- Hapoel Petah Tikva -->
|win_MNE=3 |draw_MNE=3 |loss_MNE=2 |gf_MNE=11|ga_MNE=7<!-- Maccabi Netanya -->
|name_HPT=[[Hapoel Petah Tikva F.C.|Hapoel Petah Tikva]]
|name_MNE=[[Maccabi Netanya F.C.|Maccabi Netanya]]
}}</onlyinclude>

===Regular season results===
{{#invoke:sports results|main
|team_order = HPT,MNE
|name_HPT=[[Hapoel Petah Tikva F.C.|Hapoel Petah Tikva]]
}}

===Relegation round===
{{#invoke:Sports table|main|style=WDL
|section=Relegations round
|team8=ITI |team7=IKS
|win_IKS=11 |draw_IKS=7 |loss_IKS=15 |gf_IKS=50 |ga_IKS=53
|win_ITI=12 |draw_ITI=8 |loss_ITI=13 |gf_ITI=45 |ga_ITI=56
|name_IKS=[[Hapoel Ironi Kiryat Shmona F.C.|Ironi Kiryat Shmona]]
|name_ITI=[[Ironi Tiberias F.C.|Ironi Tiberias]]
|adjust_points_ITI=−8 |hth_ITI=Ironi Tiberias had 8 points deducted
}}
"""


def test_regular_season_in_editors_order_with_the_technical_win():
    assert parse_league_tables(_SEASON_PAGE, [0]) == [
        TeamRow("מכבי נתניה", 3, 3, 2, 11, 7, 12),
        TeamRow("הפועל פתח תקווה", 1, 0, 7, 2, 14, 3),
    ]


def test_relegation_round_by_position_with_a_deduction():
    rows = parse_league_tables(_SEASON_PAGE, [1])

    assert [row.name for row in rows] == ["עירוני קריית שמונה", "עירוני טבריה"]
    assert rows[1].points == 12 * 3 + 8 - 8


def test_template_row_format():
    row = TeamRow("מכבי נתניה", 3, 3, 2, 11, 7, 12)

    assert row.as_template_row() == "מכבי נתניה^8^3^3^2^11^7^12"


def test_unknown_team_fails_instead_of_writing_an_english_name():
    page = _SEASON_PAGE.replace("[[Maccabi Netanya F.C.|", "[[Maccabi Netanya FC|")

    with pytest.raises(ValueError, match="Maccabi Netanya FC"):
        parse_league_tables(page, [0])


def test_missing_table_fails():
    with pytest.raises(ValueError, match="no table 2"):
        parse_league_tables(_SEASON_PAGE, [2])
