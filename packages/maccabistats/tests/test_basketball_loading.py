"""Basketball loading runs offline here: the rows below are shaped as the Cargo crawler yields real
ones (no key for an empty value, a numeric-looking season as a number, a list column as a list).
The period points are made up for the tests."""
import datetime
import pickle

import pytest

from maccabistats.basketball import parse as basketball_parse
from maccabistats.basketball import serialized as basketball_serialized
from maccabistats.basketball.parse import game_from_cargo, competition_flags_from_cargo, load_basketball_from_maccabipedia
from maccabistats.basketball.serialized import get_basketball_stats, serialize_basketball_games
from maccabistats.basketball.stats import BasketballGamesStats

EUROLEAGUE_ROW = {"_pageName": "הזנת מפעלי כדורסל", "OriginalName": "יורוליג", "CurrentName": "יורוליג",
                  "League": 0, "International": 1, "Trophy": 0, "Official": 1}
ARTZIT_ROW = {"_pageName": "הזנת מפעלי כדורסל", "OriginalName": "הליגה הארצית", "CurrentName": "ליגת העל",
              "League": 1, "International": 0, "Trophy": 0, "Official": 1}
COMPETITIONS = {row["OriginalName"]: competition_flags_from_cargo(row) for row in (EUROLEAGUE_ROW, ARTZIT_ROW)}

RYTAS_2006 = {
    "_pageName": "כדורסל:02-02-2006 ריטאס וילנה נגד מכבי תל אביב - יורוליג", "Date": "2006-02-02",
    "Season": "2005/06", "Competition": "יורוליג", "Leg": "מחזור 13", "Opponent": "ריטאס וילנה", "HomeAway": "חוץ",
    "TotalPointsMaccabi": 83, "TotalPointsOpponent": 88, "ResultOpt": 3,
    "FirstQuarterPointsMaccabi": 14, "SecondQuarterPointsMaccabi": 22, "ThirdQuarterPointsMaccabi": 19,
    "FourthQuarterPointsMaccabi": 20, "FirstOvertimePointsMaccabi": 8,
    "FirstQuarterPointsOpponent": 20, "SecondQuarterPointsOpponent": 17, "ThirdQuarterPointsOpponent": 18,
    "FourthQuarterPointsOpponent": 20, "FirstOvertimePointsOpponent": 13,
    "CoachMaccabi": "פיני גרשון", "CoachOpponent": "נבן ספאחיה", "MainReferee": "לואיג'י למוניקה",
    "AssistantReferees": [""], "HighlightsVideo": "https://www.youtube.com/watch?v=MDUsgyQ6SyM", "HasArticle": 1,
    "Date__precision": 1}
ASHDOT_YAAKOV_1957 = {
    "_pageName": "כדורסל:08-02-1957 מכבי תל אביב נגד הפועל אשדות יעקב - הליגה הארצית", "Date": "1957-02-08",
    "Hour": "20:30", "Season": 1957, "Competition": "הליגה הארצית", "Leg": "מחזור 2", "Opponent": "הפועל אשדות יעקב",
    "HomeAway": "בית", "Stadium": "מגרש עמירם", "TotalPointsMaccabi": 2, "TotalPointsOpponent": 0, "ResultOpt": 1,
    "Technical": 1, "AssistantReferees": [""], "HasArticle": 1, "Date__precision": 1}
BEER_SHEVA_2026 = {
    "_pageName": "כדורסל:01-06-2026 מכבי תל אביב נגד הפועל באר שבע - ליגת העל", "Date": "2026-06-01", "Hour": "21:10",
    "Season": "2025/26", "Competition": "ליגת העל", "Leg": "רבע גמר - משחק 1", "Opponent": "הפועל באר שבע",
    "HomeAway": "בית", "Stadium": "היכל מנורה מבטחים", "TotalPointsMaccabi": 106, "TotalPointsOpponent": 90,
    "ResultOpt": 1, "CoachMaccabi": "עודד קטש", "CoachOpponent": "יניב רבינס", "MainReferee": "עופר מנהיים",
    "AssistantReferees": ["כפיר מועלם", " ניר קרן"], "Crowd": 7939, "HasArticle": 1, "Date__precision": 1}
NO_RESULT_ENTERED = {"_pageName": "כדורסל:משחק בלי תוצאה", "TotalPointsMaccabi": 0, "TotalPointsOpponent": 0,
                     "AssistantReferees": [""]}


def test_game_fields_are_read_from_the_row():
    game = game_from_cargo(RYTAS_2006, COMPETITIONS)

    assert game.date == datetime.date(2006, 2, 2)
    assert (game.season, game.competition, game.leg, game.opponent) == ("2005/06", "יורוליג", "מחזור 13", "ריטאס וילנה")
    assert game.is_away and not game.is_home and not game.is_neutral
    assert (game.maccabi.name, game.maccabi.coach, game.maccabi.score) == ("מכבי תל אביב", "פיני גרשון", 83)
    assert (game.opponent_team.name, game.opponent_team.coach, game.opponent_team.score) == ("ריטאס וילנה", "נבן ספאחיה", 88)
    assert game.maccabi.quarters == (14, 22, 19, 20)
    assert game.opponent_team.overtimes == (13, None, None, None)
    assert game.videos.highlights == "https://www.youtube.com/watch?v=MDUsgyQ6SyM"
    assert game.videos.all == ("https://www.youtube.com/watch?v=MDUsgyQ6SyM",)
    assert str(game) == RYTAS_2006["_pageName"]


def test_an_empty_value_stays_none_and_never_becomes_zero():
    game = game_from_cargo(RYTAS_2006, COMPETITIONS)

    assert game.hour is None and game.stadium is None and game.crowd is None and game.technical is None
    assert game.maccabi.halves == (None, None)
    assert game.assistant_referees == ()
    assert game.videos.full_game is None


def test_win_loss_and_overtime_come_from_the_points():
    lost_in_overtime = game_from_cargo(RYTAS_2006, COMPETITIONS)
    won = game_from_cargo(BEER_SHEVA_2026, COMPETITIONS)

    assert lost_in_overtime.is_maccabi_loss and not lost_in_overtime.is_maccabi_win
    assert lost_in_overtime.score_diff == -5
    assert lost_in_overtime.overtimes_played == 1 and lost_in_overtime.is_overtime
    assert won.is_maccabi_win and won.score_diff == 16
    assert won.overtimes_played == 0 and not won.is_overtime


def test_zero_zero_is_a_game_with_no_result():
    game = game_from_cargo(NO_RESULT_ENTERED, COMPETITIONS)

    assert not game.has_result
    assert game.score_diff is None
    assert not game.is_maccabi_win and not game.is_maccabi_loss
    assert game.date is None and game.season is None


def test_numeric_season_is_text_and_technical_is_kept_as_stored():
    game = game_from_cargo(ASHDOT_YAAKOV_1957, COMPETITIONS)

    assert game.season == "1957"
    assert game.technical == 1 and game.is_technical
    assert game.has_result and game.is_maccabi_win


def test_assistant_referees_are_trimmed():
    assert game_from_cargo(BEER_SHEVA_2026, COMPETITIONS).assistant_referees == ("כפיר מועלם", "ניר קרן")


def test_competition_flags_come_from_the_catalog_by_the_original_name():
    old_league_game = game_from_cargo(ASHDOT_YAAKOV_1957, COMPETITIONS)
    european_game = game_from_cargo(RYTAS_2006, COMPETITIONS)

    assert old_league_game.competition_flags.is_league and not old_league_game.competition_flags.is_international
    assert old_league_game.competition_flags.current_name == "ליגת העל"
    assert european_game.competition_flags.is_international and european_game.competition_flags.is_official


def test_competition_missing_from_the_catalog_has_no_flags():
    assert game_from_cargo(BEER_SHEVA_2026, COMPETITIONS).competition_flags is None


# --- the crawl and its row-count guard ----------------------------------------------

def _fake_crawler(crawls_by_table: dict, counts_by_table: dict, calls: list):
    """Stands in for the Cargo crawler: each crawl of a table pops the next list of rows for it."""

    def crawler(tables_name, tables_fields, **kwargs):
        calls.append((tables_name, tables_fields, kwargs))
        if tables_fields.startswith("COUNT("):
            return iter([{"RowsCount": counts_by_table[tables_name].pop(0)}])
        return iter(crawls_by_table[tables_name].pop(0))

    return crawler


GAME_ROWS = [RYTAS_2006, ASHDOT_YAAKOV_1957, BEER_SHEVA_2026]
COMPETITION_ROWS = [EUROLEAGUE_ROW, ARTZIT_ROW]


def _patch_crawler(monkeypatch, game_crawls, game_counts):
    calls = []
    monkeypatch.setattr(basketball_parse, "MaccabiPediaCargoChunksCrawler", _fake_crawler(
        {"Basketball_Games": game_crawls, "Basketball_Competitions": [COMPETITION_ROWS]},
        {"Basketball_Games": game_counts, "Basketball_Competitions": [2]}, calls))
    return calls


def test_load_returns_the_games_by_date_with_their_flags(monkeypatch):
    calls = _patch_crawler(monkeypatch, [GAME_ROWS], [3])

    stats = load_basketball_from_maccabipedia()

    assert [game.date.year for game in stats] == [1957, 2006, 2026]
    assert stats[0].competition_flags.is_league
    assert len(stats) == 3

    games_crawl = next(kwargs for table, fields, kwargs in calls
                       if table == "Basketball_Games" and not fields.startswith("COUNT("))
    assert games_crawl == {"limit": 2500, "order_by": "_pageName", "unescape_all_strings": True, "timeout": 120}


def test_crawl_that_misses_a_row_is_repeated_once(monkeypatch):
    calls = _patch_crawler(monkeypatch, [GAME_ROWS[:2], GAME_ROWS], [3, 3])

    assert len(load_basketball_from_maccabipedia()) == 3
    assert sum(table == "Basketball_Games" for table, _, _ in calls) == 4


def test_crawl_that_misses_a_row_twice_fails(monkeypatch):
    _patch_crawler(monkeypatch, [GAME_ROWS[:2], GAME_ROWS[:2]], [3, 3])

    with pytest.raises(RuntimeError, match="crawled 2 rows twice, but the wiki counts 3"):
        load_basketball_from_maccabipedia()


def test_empty_crawl_fails(monkeypatch):
    _patch_crawler(monkeypatch, [[]], [3])

    with pytest.raises(RuntimeError, match="no rows for Basketball_Games"):
        load_basketball_from_maccabipedia()


# --- the pickle ---------------------------------------------------------------------

def _stats() -> BasketballGamesStats:
    return BasketballGamesStats([game_from_cargo(row, COMPETITIONS) for row in GAME_ROWS])


def test_games_with_no_date_go_last():
    stats = BasketballGamesStats([game_from_cargo(row, COMPETITIONS) for row in [NO_RESULT_ENTERED] + GAME_ROWS])

    assert stats[-1].date is None
    assert stats[0].date == datetime.date(1957, 2, 8)


def test_serialized_games_load_back_equal(tmp_path):
    file_path = serialize_basketball_games(_stats(), tmp_path / "not-there-yet")

    assert file_path.name.startswith("basketball-")
    assert get_basketball_stats(file_path).games == _stats().games


def test_newest_file_in_the_default_folder_is_loaded(tmp_path, monkeypatch):
    monkeypatch.setattr(basketball_serialized, "_serialized_basketball_games_folder_path", tmp_path)
    with pytest.raises(RuntimeError, match="No basketball-\\*.games"):
        get_basketball_stats()

    serialize_basketball_games(_stats(), tmp_path)

    assert len(get_basketball_stats()) == 3


def test_pickle_from_another_version_is_refused(tmp_path):
    old_stats = _stats()
    old_stats.version = "2.60"
    file_path = tmp_path / "basketball-2.60-2025-01-01.games"
    file_path.write_bytes(pickle.dumps(old_stats))

    with pytest.raises(RuntimeError, match="was written by maccabistats 2.60"):
        get_basketball_stats(file_path)


def test_only_basketball_stats_are_serialized(tmp_path):
    with pytest.raises(RuntimeError, match="only a BasketballGamesStats"):
        serialize_basketball_games([], tmp_path)


def test_missing_file_is_reported(tmp_path):
    with pytest.raises(RuntimeError, match="No such file"):
        get_basketball_stats(tmp_path / "nope.games")


def test_football_entry_points_are_still_exported():
    import maccabistats

    assert maccabistats.load_basketball_from_maccabipedia is load_basketball_from_maccabipedia
    assert maccabistats.get_maccabi_stats and maccabistats.ErrorsFinder
