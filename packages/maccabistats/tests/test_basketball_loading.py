"""Basketball loading runs offline here: the rows below are shaped as the Cargo crawler yields real
ones (no key for an empty value, a numeric-looking season as a number, a list column as a list).
The period points are made up for the tests."""
import datetime
import pickle

import pytest

from maccabistats.basketball import parse as basketball_parse
from maccabistats.basketball import serialized as basketball_serialized
from maccabistats.basketball.parse import (
    competition_flags_from_cargo,
    game_from_cargo,
    load_basketball_from_maccabipedia,
    player_from_cargo,
)
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
BEER_SHEVA_PAGE = BEER_SHEVA_2026["_pageName"]
# A modern line: every number recorded
HOARD_2026 = {"_ID": 160002, "_pageName": BEER_SHEVA_PAGE, "PlayerName": "ג'יילן הורד", "PlayerNumber": 5,
              "IsCaptain": 0, "IsStartingFive": 1, "IsPlayed": 1, "Team": 1, "TotalPoints": 19,
              "ThreePointsAttempts": 4, "ThreePointsScored": 1, "FieldGoalsAttempts": 9, "FieldGoalsScored": 6,
              "FreeThrowsAttempts": 5, "FreeThrowsScored": 4, "TotalRebounds": 7, "OffensiveRebounds": 2,
              "DefensiveRebounds": 5, "MinutesPlayed": 27, "TotalPersonalFouls": 2, "Assists": 3, "Blocks": 1,
              "Steals": 2, "Turnovers": 1}
BLATT_2026 = {**HOARD_2026, "_ID": 160001, "PlayerName": "תמיר בלאט", "PlayerNumber": 45, "IsCaptain": 1,
              "TotalPoints": 11, "Assists": 9}
DID_NOT_PLAY_2026 = {"_ID": 160003, "_pageName": BEER_SHEVA_PAGE, "PlayerName": "עומר מאייר", "IsCaptain": 0,
                     "IsStartingFive": 0, "IsPlayed": 0, "Team": 1, "TotalRebounds": 0}
RIVAL_2026 = {**HOARD_2026, "_ID": 160004, "PlayerName": "שחקן היריבה", "Team": 0, "TotalPoints": 30}
# An old line as the wiki stores it: the points, and 0 for everything nobody recorded
TOR_1957 = {"_ID": 14339, "_pageName": ASHDOT_YAAKOV_1957["_pageName"], "PlayerName": "חיים תור", "PlayerNumber": 9,
            "IsCaptain": 0, "IsStartingFive": 0, "IsPlayed": 1, "Team": 0, "TotalPoints": 6, "ThreePointsAttempts": 0,
            "ThreePointsScored": 0, "FieldGoalsAttempts": 0, "FieldGoalsScored": 0, "FreeThrowsAttempts": 0,
            "FreeThrowsScored": 0, "TotalRebounds": 0, "OffensiveRebounds": 0, "DefensiveRebounds": 0,
            "MinutesPlayed": 0, "TotalPersonalFouls": 0, "Assists": 0, "Blocks": 0, "Steals": 0, "Turnovers": 0}
ROW_OF_A_DELETED_GAME = {**TOR_1957, "_ID": 99, "_pageName": "כדורסל:משחק שנמחק"}
PLAYER_ROWS = [HOARD_2026, BLATT_2026, DID_NOT_PLAY_2026, RIVAL_2026, TOR_1957, ROW_OF_A_DELETED_GAME]

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


# --- the crawl and its guard --------------------------------------------------------

GAMES_TABLE, COMPETITIONS_TABLE, PLAYERS_TABLE = ("Basketball_Games", "Basketball_Competitions",
                                                  "Basketball_Player_Game_Events_Summary")
GAME_ROWS = [RYTAS_2006, ASHDOT_YAAKOV_1957, BEER_SHEVA_2026]
COMPETITION_ROWS = [EUROLEAGUE_ROW, ARTZIT_ROW]


def _patch_crawler(monkeypatch, crawls: dict | None = None, states: dict | None = None) -> list:
    """
    Stands in for the Cargo crawler. For each table, ``crawls`` is the rows each crawl of it returns
    in turn and ``states`` the (row count, last row id) each state query returns in turn; the last
    item of either repeats. A table left out behaves: one whole crawl, and a state that stands still.
    """
    whole = {GAMES_TABLE: GAME_ROWS, COMPETITIONS_TABLE: COMPETITION_ROWS, PLAYERS_TABLE: PLAYER_ROWS}
    crawls = {table: [rows] for table, rows in whole.items()} | (crawls or {})
    states = {table: [(len(rows), 500)] for table, rows in whole.items()} | (states or {})
    calls = []

    def next_of(answers: list):
        return answers.pop(0) if len(answers) > 1 else answers[0]

    def crawler(tables_name, tables_fields, **kwargs):
        is_state_query = tables_fields.startswith("COUNT(")
        calls.append((tables_name, "state" if is_state_query else "crawl", kwargs))
        if is_state_query:
            rows_count, last_row_id = next_of(states[tables_name])
            return iter([{"RowsCount": rows_count, "LastRowId": last_row_id}])
        return iter(next_of(crawls[tables_name]))

    monkeypatch.setattr(basketball_parse, "MaccabiPediaCargoChunksCrawler", crawler)
    return calls


def _crawls_of(calls: list, table: str) -> list:
    return [kwargs for called_table, kind, kwargs in calls if called_table == table and kind == "crawl"]


def test_load_returns_the_games_by_date_with_their_flags(monkeypatch):
    calls = _patch_crawler(monkeypatch)

    stats = load_basketball_from_maccabipedia()

    assert [game.date.year for game in stats] == [1957, 2006, 2026]
    assert stats[0].competition_flags.is_league
    assert len(stats) == 3
    assert _crawls_of(calls, GAMES_TABLE) == [
        {"limit": 2500, "order_by": "_pageName", "unescape_all_strings": True, "timeout": 120}]
    assert _crawls_of(calls, PLAYERS_TABLE)[0]["order_by"] == "_ID"


def test_crawl_that_misses_a_row_is_repeated(monkeypatch):
    calls = _patch_crawler(monkeypatch, crawls={GAMES_TABLE: [GAME_ROWS[:2], GAME_ROWS]})

    assert len(load_basketball_from_maccabipedia()) == 3
    # Every table is crawled again, so the games and their players come from one moment
    assert len(_crawls_of(calls, GAMES_TABLE)) == len(_crawls_of(calls, PLAYERS_TABLE)) == 2


def test_crawl_that_keeps_missing_a_row_fails(monkeypatch):
    calls = _patch_crawler(monkeypatch, crawls={GAMES_TABLE: [GAME_ROWS[:2]]})

    with pytest.raises(RuntimeError, match="not whole in 3 attempts: Basketball_Games: crawled 2 rows, the wiki counts 3"):
        load_basketball_from_maccabipedia()
    assert len(_crawls_of(calls, GAMES_TABLE)) == 3


def test_crawl_with_the_right_count_but_a_game_read_twice_is_repeated(monkeypatch):
    calls = _patch_crawler(monkeypatch, crawls={GAMES_TABLE: [[RYTAS_2006, RYTAS_2006, BEER_SHEVA_2026], GAME_ROWS]})

    stats = load_basketball_from_maccabipedia()

    assert sorted(game.date.year for game in stats) == [1957, 2006, 2026]
    assert len(_crawls_of(calls, GAMES_TABLE)) == 2


def test_page_saved_during_the_crawl_makes_it_start_over(monkeypatch):
    # A saved page gets new row ids: the players table has the same number of rows, all distinct,
    # and still is not the table the crawl started on
    moved_state = (len(PLAYER_ROWS), 512)
    calls = _patch_crawler(monkeypatch, states={PLAYERS_TABLE: [(len(PLAYER_ROWS), 500), moved_state]})

    load_basketball_from_maccabipedia()

    assert len(_crawls_of(calls, PLAYERS_TABLE)) == len(_crawls_of(calls, GAMES_TABLE)) == 2


def test_table_that_never_stands_still_fails(monkeypatch):
    ever_moving = [(3, last_row_id) for last_row_id in range(500, 520)]
    _patch_crawler(monkeypatch, states={GAMES_TABLE: ever_moving})

    with pytest.raises(RuntimeError, match="Basketball_Games changed during the crawl"):
        load_basketball_from_maccabipedia()


def test_state_query_passes_the_real_crawler(monkeypatch):
    # The real crawler refuses fields with no _pageName in them; the state query must get through it
    real_crawler = basketball_parse.MaccabiPediaCargoChunksCrawler
    monkeypatch.setattr(real_crawler, "_request_more_data", lambda self: (
        self._already_fetched_data_queue.append({"RowsCount": 3576, "LastRowId": 12727}),
        setattr(self, "_finished_to_crawl", True)))

    assert basketball_parse._table_state("Basketball_Games") == (3576, 12727)


def test_catalog_row_with_no_name_is_skipped_and_a_repeated_one_does_not_fail_the_load(monkeypatch):
    catalog = COMPETITION_ROWS + [{"_pageName": "הזנת מפעלי כדורסל", "League": 1}, ARTZIT_ROW]
    _patch_crawler(monkeypatch, crawls={COMPETITIONS_TABLE: [catalog]}, states={COMPETITIONS_TABLE: [(4, 500)]})

    stats = load_basketball_from_maccabipedia()

    assert stats[0].competition_flags.current_name == "ליגת העל"


def test_unreadable_date_keeps_the_game_with_no_date():
    game = game_from_cargo({**ASHDOT_YAAKOV_1957, "Date": 1957}, COMPETITIONS)

    assert game.date is None
    assert game.is_maccabi_win


def test_awarded_game_is_decided_by_the_technical_flag_alone():
    # The wiki's rule for basketball: the flag decides, even against the score fields
    awarded_to_maccabi_with_no_score = game_from_cargo(
        {**ASHDOT_YAAKOV_1957, "TotalPointsMaccabi": 0, "TotalPointsOpponent": 0}, COMPETITIONS)
    awarded_to_opponent_against_the_score = game_from_cargo({**ASHDOT_YAAKOV_1957, "Technical": 2}, COMPETITIONS)

    assert awarded_to_maccabi_with_no_score.has_result and awarded_to_maccabi_with_no_score.is_maccabi_win
    assert awarded_to_maccabi_with_no_score.score_diff is None
    assert awarded_to_opponent_against_the_score.is_maccabi_loss
    assert not awarded_to_opponent_against_the_score.is_maccabi_win


def test_technical_value_other_than_one_or_two_is_not_an_awarded_game():
    assert not game_from_cargo({**BEER_SHEVA_2026, "Technical": -1}, COMPETITIONS).is_technical


def test_empty_crawl_fails(monkeypatch):
    _patch_crawler(monkeypatch, crawls={GAMES_TABLE: [[]]})

    with pytest.raises(RuntimeError, match="no rows for Basketball_Games"):
        load_basketball_from_maccabipedia()


# --- players' box scores ------------------------------------------------------------

def test_player_line_is_read_from_the_row():
    player = player_from_cargo(HOARD_2026)

    assert (player.name, player.number, str(player)) == ("ג'יילן הורד", 5, "ג'יילן הורד")
    assert player.is_starting_five and player.is_played and not player.is_captain
    assert (player.points, player.minutes, player.rebounds, player.assists) == (19, 27, 7, 3)
    # The wiki's FieldGoals are the two-point shots
    assert (player.two_points_scored, player.two_points_attempts) == (6, 9)
    assert 2 * player.two_points_scored + 3 * player.three_points_scored + player.free_throws_scored == player.points
    assert player.technical_fouls is None


def test_player_who_did_not_play_keeps_empty_numbers_as_none():
    player = player_from_cargo(DID_NOT_PLAY_2026)

    assert not player.is_played
    assert player.points is None and player.minutes is None and player.number is None


def test_load_puts_each_player_on_his_side_in_the_page_order(monkeypatch):
    _patch_crawler(monkeypatch)

    stats = load_basketball_from_maccabipedia()
    beer_sheva_game = stats[-1]

    # By Cargo's row id, whatever order the crawl returned
    assert [player.name for player in beer_sheva_game.maccabi.players] == ["תמיר בלאט", "ג'יילן הורד", "עומר מאייר"]
    assert [player.name for player in beer_sheva_game.maccabi.played_players] == ["תמיר בלאט", "ג'יילן הורד"]
    assert [player.name for player in beer_sheva_game.opponent_team.players] == ["שחקן היריבה"]
    assert stats[1].maccabi.players == ()


def test_player_rows_of_no_game_are_kept_aside(monkeypatch):
    _patch_crawler(monkeypatch)

    stats = load_basketball_from_maccabipedia()

    assert [(page_name, team, player.name) for page_name, team, player in stats.player_rows_without_game] == [
        ("כדורסל:משחק שנמחק", 0, "חיים תור")]


def test_player_with_no_name_gets_an_empty_one():
    assert player_from_cargo({**DID_NOT_PLAY_2026, "PlayerName": None}).name == ""


def test_load_without_players_does_not_crawl_them(monkeypatch):
    calls = _patch_crawler(monkeypatch)

    stats = load_basketball_from_maccabipedia(with_players=False)

    assert all(table != PLAYERS_TABLE for table, _, _ in calls)
    assert stats[-1].maccabi.players == () and stats.player_rows_without_game == []


def test_old_box_score_that_stored_zeros_did_not_record_the_stat(monkeypatch):
    _patch_crawler(monkeypatch)
    stats = load_basketball_from_maccabipedia()
    old_side, modern_side = stats[0].opponent_team, stats[-1].maccabi

    assert old_side.has_recorded("points") and not old_side.has_recorded("assists")
    assert not old_side.has_recorded("minutes")
    assert modern_side.has_recorded("assists") and modern_side.has_recorded("steals")
    with pytest.raises(ValueError, match="Unknown player stat"):
        modern_side.has_recorded("goals")


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
    with pytest.raises(RuntimeError, match="No basketball-.*games"):
        get_basketball_stats()

    older = serialize_basketball_games(BasketballGamesStats([]), tmp_path)
    older.rename(tmp_path / older.name.replace(str(datetime.date.today()), "2020-01-01"))
    serialize_basketball_games(_stats(), tmp_path)

    assert len(get_basketball_stats()) == 3


def test_file_of_another_version_in_the_default_folder_is_not_picked(tmp_path, monkeypatch):
    monkeypatch.setattr(basketball_serialized, "_serialized_basketball_games_folder_path", tmp_path)
    (tmp_path / "basketball-2.60-2030-01-01.games").write_bytes(pickle.dumps(_stats()))

    with pytest.raises(RuntimeError, match="No basketball-.*games"):
        get_basketball_stats()


def test_file_that_is_not_basketball_games_is_refused(tmp_path):
    file_path = tmp_path / "maccabi-2.60-2025-01-01.games"
    file_path.write_bytes(pickle.dumps({"football": True}))

    with pytest.raises(RuntimeError, match="does not hold basketball games"):
        get_basketball_stats(file_path)


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
