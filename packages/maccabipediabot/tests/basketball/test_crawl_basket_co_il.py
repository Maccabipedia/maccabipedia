"""Parser tests for crawl_basket_co_il."""
import json
from datetime import datetime
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from maccabipediabot.basketball.basketball_game import BasketballGame
from maccabipediabot.basketball._crawler_utils import write_unknown_teams_report
from maccabipediabot.basketball.crawl_basket_co_il import (
    UnknownTeamNameError,
    _competition_from_game_page,
    _normalize_fixture,
    _parse_header,
    _parse_player_rows,
    discover_games_latest_season,
    parse_game_page,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _partial_game() -> BasketballGame:
    """The discovery-stage BasketballGame for fixture game 26383
    (Hapoel Holon home vs Maccabi away, 30/05/2025, semi-final game 2)."""
    return BasketballGame(
        home_team_name="הפועל חולון",
        away_team_name="מכבי תל אביב",
        competition="ליגת העל",
        fixture="",  # filled by parse_game_page
        game_date=datetime(2025, 5, 30, 20, 30),
        home_team_score=73,
        away_team_score=85,
        game_url=["https://basket.co.il/game-zone.asp?GameId=26383"],
    )


def test_parse_game_page_against_real_fixture():
    """Round-trip the captured game-zone HTML against a hand-verified expected
    BasketballGame snapshot. One assert covers everything."""
    html = (FIXTURES / "basket_co_il_game_26383.html").read_bytes().decode("utf-8")
    expected = BasketballGame.model_validate_json(
        (FIXTURES / "basket_co_il_game_26383.expected.json").read_text("utf-8")
    )
    actual = parse_game_page(html, _partial_game())
    assert actual.model_dump() == expected.model_dump()


def _player_row(cell0: str, name: str = "מיקי ברקוביץ'") -> str:
    """One <tr class='row'> with the 21 <td>s _parse_player_rows expects.
    `cell0` is whatever goes inside tds[0] (the number cell) — pass an `<a>...`
    to simulate a linked number, '&nbsp;' to simulate the team-row layout, or
    plain text to simulate a number with no surrounding link."""
    cells = [f"<td>{cell0}</td>"]                                  # 0: number
    cells += [f'<td><a href="x">{name}</a></td>']                  # 1: name
    cells += ['<td></td>']                                         # 2: starting *
    cells += ['<td>10</td>']                                       # 3: minutes
    cells += ['<td>0</td>']                                        # 4: total points
    cells += ['<td>0/3</td>', '<td>0</td>']                        # 5,6: 2pt
    cells += ['<td>0/3</td>', '<td>0</td>']                        # 7,8: 3pt
    cells += ['<td>0/0</td>', '<td>0</td>']                        # 9,10: ft
    cells += ['<td>4</td>', '<td>0</td>']                          # 11,12: rebounds
    cells += ['<td>0</td>']                                        # 13: total rebounds (unused)
    cells += ['<td>2</td>']                                        # 14: fouls
    cells += ['<td>0</td>']                                        # 15: pad
    cells += ['<td>0</td>', '<td>1</td>', '<td>0</td>', '<td>0</td>']  # 16-19: steals, to, ast, blk
    cells += ['<td>0</td>']                                        # 20: pad to reach 21
    return f'<tr class="row">{"".join(cells)}</tr>'


def _player_table_html(player_row: str) -> str:
    """Minimal table mirroring basket.co.il layout: two non-row header rows,
    a `tr.row` "קבוצתי" team row that the parser treats as the column header,
    the player row under test, and a `tr.row` "סה\"כ" totals row that the
    parser drops via `[start_index:-1]`."""
    return f"""
    <table>
      <tr class="header_row_2"><td>section header</td></tr>
      <tr class="header_row"><td>column labels</td></tr>
      {_player_row("&nbsp;", name="קבוצתי")}
      {player_row}
      {_player_row("&nbsp;", name='סה"כ')}
    </table>
    """


@pytest.mark.parametrize("cell0, expected_number", [
    ('<a href="player.asp?PlayerId=1">0</a>', 0),    # jersey #0 must stay 0, not collapse to None
    ('<a href="player.asp?PlayerId=1">23</a>', 23),
    ('<a href="player.asp?PlayerId=1">00</a>', 0),   # zero-padded — basket.co.il sometimes does this
    ('<a href="player.asp?PlayerId=1"></a>', None),  # link present but empty text → unknown
    ('&nbsp;', None),                                # no <a> at all → unknown
])
def test_parse_player_rows_preserves_jersey_number(cell0, expected_number):
    html = _player_table_html(_player_row(cell0))
    table = BeautifulSoup(html, "html.parser").select_one("table")
    players = _parse_player_rows(table)
    assert len(players) == 1
    assert players[0].number == expected_number


@pytest.mark.parametrize("raw, expected", [
    # basket.co.il playoff legs -> wiki convention "<round> - משחק N".
    # Wording varies by round: QF "רבע הגמר", SF "סדרת חצי גמר", final "סדרת הגמר";
    # number is sometimes "משחק מספר N", sometimes "משחק N".
    ("- רבע הגמר משחק מספר 1", "רבע גמר - משחק 1"),
    ("- סדרת חצי גמר משחק מספר 2", "חצי גמר - משחק 2"),
    ("- סדרת הגמר משחק מספר 3", "גמר - משחק 3"),
    ("- הגמר משחק 4", "גמר - משחק 4"),
    # regular season and anything unrecognised pass through untouched
    ("מחזור 26", "מחזור 26"),
    ("גמר", "גמר"),          # playoff round without a game number -> unchanged
    ("", ""),
])
def test_normalize_fixture(raw, expected):
    assert _normalize_fixture(raw) == expected


def _header_html(h4_inner: str) -> str:
    """Minimal #wrap_inner_3 carrying just the h4 fixture line."""
    return (f'<div id="wrap_inner_3"><h4 class="he">{h4_inner}</h4>'
            f'<h5>אולם, עיר</h5><h6></h6></div>')


@pytest.mark.parametrize("h4_inner, expected_fixture", [
    # mirrors the real basket.co.il h4: text "ליגת <logo> סל <fixture>"
    ('ליגת <img src="x"/> סל מחזור 26', "מחזור 26"),
    ('ליגת <img src="x"/> סל - רבע הגמר משחק מספר 1', "רבע גמר - משחק 1"),
    ('ליגת <img src="x"/> סל - סדרת חצי גמר משחק מספר 1', "חצי גמר - משחק 1"),
])
def test_parse_header_normalizes_playoff_fixture(h4_inner, expected_fixture):
    soup = BeautifulSoup(_header_html(h4_inner), "html.parser")
    assert _parse_header(soup)["fixture"] == expected_fixture


def test_parse_game_page_raises_when_header_missing():
    with pytest.raises(RuntimeError, match="#wrap_inner_3"):
        parse_game_page("<html><body>maintenance page</body></html>", _partial_game())


def test_parse_game_page_raises_when_box_score_tables_missing():
    minimal = """
    <div id="wrap_inner_3">
      <h4></h4>
      <h5>אולם, עיר</h5>
      <h6>שופטים: ראשי</h6>
    </div>
    <table class="stats_tbl categories">
      <tr><td></td><td>1</td><td>2</td><td>3</td><td>4</td></tr>
      <tr><td>home</td><td>20</td><td>20</td><td>20</td><td>20</td></tr>
      <tr><td>away</td><td>20</td><td>20</td><td>20</td><td>20</td></tr>
    </table>
    <table class="stats_tbl categories"><tr><td>filler</td></tr></table>
    """
    with pytest.raises(RuntimeError, match="fewer than 4 stats_tbl"):
        parse_game_page(minimal, _partial_game())


# ---------------------------------------------------------------------------
# Discovery (synthetic feed via monkeypatched requests.get)
# ---------------------------------------------------------------------------

def _stub_feed(monkeypatch, games: list[dict], game_page_html: str = "<html></html>") -> None:
    """Route requests.get: the games_all feed URL returns the JSON payload; any
    game-zone page URL returns `game_page_html` (used by the unknown-game_type
    competition fallback)."""
    feed_bytes = json.dumps([{"games": games}]).encode("utf-8")

    class _Resp:
        def __init__(self, *, content=b"", text=""):
            self.status_code = 200
            self.headers = {"Content-Type": "text/html"}
            self.content = content
            self.text = text
            self.encoding = "utf-8"

        def raise_for_status(self):
            pass

    def _fake_get(url, *args, **kwargs):
        if "games_all" in url:
            return _Resp(content=feed_bytes)
        return _Resp(text=game_page_html)

    from maccabipediabot.basketball import crawl_basket_co_il
    monkeypatch.setattr(crawl_basket_co_il.requests, "get", _fake_get)


def _maccabi_game(**overrides) -> dict:
    base = {
        "id": 1, "team_name_eng_1": "Maccabi Tel-Aviv", "team_name_eng_2": "Hapoel Tel-Aviv",
        "score_team1": 90, "score_team2": 80, "game_date_txt": "01/01/2026",
        "game_time": "20:30", "game_type": 5,
    }
    return {**base, **overrides}


def test_discover_filters_score_edge_cases(monkeypatch):
    """0-0 = unplayed placeholder (drop). 0-N = forfeit (keep)."""
    _stub_feed(monkeypatch, [
        _maccabi_game(id=1, score_team1=0, score_team2=0),    # placeholder, drop
        _maccabi_game(id=2, score_team1=0, score_team2=20),   # forfeit, keep
        _maccabi_game(id=3, score_team1=90, score_team2=80),  # normal, keep
    ])
    discovered = discover_games_latest_season()
    # Each discovered game's URL encodes its source id; check the surviving set.
    surviving_ids = {int(game.game_url[0].rsplit("=", 1)[1]) for game in discovered}
    assert surviving_ids == {2, 3}


@pytest.mark.parametrize("h4_inner, expected", [
    ("ליגת סל מחזור 26", "ליגת העל"),                 # regular season
    ("ליגת סל - סדרת חצי גמר משחק מספר 1", "ליגת העל"),  # any playoff round
    # real header has the sponsor logo as an <img> between "ליגת" and "סל"
    ('ליגת <img src="x"/> סל - רבע הגמר משחק מספר 1', "ליגת העל"),
    ("גביע ווינר סל - רבע גמר", None),                # a cup -> unrecognised, fail loud
    ("ליגת לאומית בכדורסל - מחזור 5", None),          # 2nd-tier league must NOT match top league
    ("", None),
])
def test_competition_from_game_page(h4_inner, expected):
    html = f'<div id="wrap_inner_3"><h4 class="he">{h4_inner}</h4></div>'
    assert _competition_from_game_page(html) == expected


def test_discover_does_not_fetch_page_for_stable_code(monkeypatch):
    """Regular-season games (code 5) resolve from the map and must NOT fetch the
    game page — a garbage page that would yield no competition proves the short-circuit."""
    _stub_feed(monkeypatch, [_maccabi_game(id=1, game_type=5)],
               game_page_html="<html>not a league header</html>")
    discovered = discover_games_latest_season()
    assert [g.competition for g in discovered] == ["ליגת העל"]


def test_discover_derives_competition_from_page_for_unknown_game_type(monkeypatch):
    """A playoff round has its own game_type code (not in _BASKET_GAME_TYPE); the
    competition is recovered from the game page header rather than failing."""
    league_page = '<div id="wrap_inner_3"><h4>ליגת סל - סדרת חצי גמר משחק מספר 1</h4></div>'
    _stub_feed(monkeypatch, [_maccabi_game(id=1, game_type=26)], game_page_html=league_page)
    discovered = discover_games_latest_season()
    assert [g.competition for g in discovered] == ["ליגת העל"]


def test_discover_raises_when_competition_unresolvable(monkeypatch):
    """Unknown game_type AND a page header we don't recognise (e.g. a brand-new
    competition) must raise so we don't silently lose it."""
    _stub_feed(monkeypatch, [_maccabi_game(id=1, game_type=999)],
               game_page_html="<html>maintenance</html>")
    with pytest.raises(RuntimeError, match="could not resolve competition"):
        discover_games_latest_season()


def test_discover_raises_on_untranslated_team_name(monkeypatch):
    """A team name missing from _TEAM_NAMES passes through as English; we must raise
    rather than upload a game page titled with the English opponent name. The raised
    error carries the affected games so CI can report them without scraping text."""
    _stub_feed(monkeypatch, [_maccabi_game(id=7, team_name_eng_2="Totally New Team")])
    with pytest.raises(UnknownTeamNameError) as exc_info:
        discover_games_latest_season()
    assert exc_info.value.affected_games == [
        {"id": 7, "teams": ["Totally New Team"], "date": "01/01/2026"}
    ]


def test_write_unknown_teams_report_round_trips(tmp_path):
    """The report file is the Python<->CI contract; verify it's valid JSON with the
    affected games, and a None path is a no-op (local runs don't write a report)."""
    affected = [{"id": 7, "teams": ["Totally New Team"], "date": "01/01/2026"}]
    report = tmp_path / "unknown_teams.json"
    write_unknown_teams_report(report, affected)
    assert json.loads(report.read_text(encoding="utf-8")) == affected

    write_unknown_teams_report(None, affected)  # no path → no file, no error
