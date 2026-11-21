"""Basketball stats on a small made-up run of games: six games over two seasons, with box scores."""
import datetime

import pytest

from maccabistats.basketball.parse import competition_flags_from_cargo, game_from_cargo, player_from_cargo
from maccabistats.basketball.stats import BasketballGamesStats

CATALOG = {
    "ליגת העל": competition_flags_from_cargo({"CurrentName": "ליגת העל", "League": 1, "Official": 1}),
    "יורוליג": competition_flags_from_cargo({"CurrentName": "יורוליג", "International": 1, "Official": 1}),
    "גביע המדינה": competition_flags_from_cargo({"CurrentName": "גביע המדינה", "Trophy": 1, "Official": 1}),
}


def _player(name: str, points=None, **fields) -> dict:
    return {"PlayerName": name, "IsPlayed": 1, "IsStartingFive": 0, "IsCaptain": 0, "TotalPoints": points, **fields}


def _game(day: str, opponent: str, score: tuple, *, competition="ליגת העל", home_away="בית", season="2025/26",
          coach="עודד קטש", players=(), **fields):
    page = f"כדורסל:{day} {opponent}"
    raw = {"_pageName": page, "Date": day, "Season": season, "Competition": competition, "Opponent": opponent,
           "HomeAway": home_away, "TotalPointsMaccabi": score[0], "TotalPointsOpponent": score[1],
           "CoachMaccabi": coach, **fields}
    return game_from_cargo(raw, CATALOG, {(page, 1): [player_from_cargo(row) for row in players]})


WIN_1 = _game("2025-10-01", "הפועל תל אביב", (90, 80), players=[
    _player("תמיר בלאט", 20, Assists=9, IsStartingFive=1, IsCaptain=1), _player("רומן סורקין", 30, Assists=1)])
WIN_2 = _game("2025-10-05", "ריאל מדריד", (100, 70), competition="יורוליג", home_away="חוץ", players=[
    _player("תמיר בלאט", 25, Assists=11, IsStartingFive=1), _player("רומן סורקין", IsPlayed=0)])
LOSS_1 = _game("2025-10-09", "הפועל תל אביב", (70, 75), home_away="חוץ", FirstOvertimePointsMaccabi=5,
               FirstOvertimePointsOpponent=10, players=[_player("תמיר בלאט", 10), _player("רומן סורקין", 12)])
NO_RESULT = _game("2025-10-12", "הפועל ירושלים", (0, 0))
WIN_3 = _game("2025-10-15", "הפועל ירושלים", (88, 60), competition="גביע המדינה", home_away="נייטרלי")
AWARDED_WIN = _game("2026-10-20", "הפועל חולון", (20, 0), season="2026/27", coach="דייוויד בלאט", Technical=1)
# An old box score: points only, everything else stored as 0
OLD_GAME = _game("1972-10-06", "מכבי חיפה", (95, 60), season="1972/73", coach="יהושע רוזין", players=[
    _player("טל ברודי", 30, Assists=0, IsCaptain=1), _player("תמיר בלאט", 5, Assists=0)])

ALL_GAMES = [WIN_1, WIN_2, LOSS_1, NO_RESULT, WIN_3, AWARDED_WIN, OLD_GAME]


@pytest.fixture
def stats() -> BasketballGamesStats:
    return BasketballGamesStats(ALL_GAMES)


def _days(games) -> list[str]:
    return [str(game.date) for game in games]


def test_filters_by_place_and_competition_flags(stats):
    assert _days(stats.away_games) == ["2025-10-05", "2025-10-09"]
    assert _days(stats.neutral_games) == ["2025-10-15"]
    assert len(stats.home_games) == 4
    assert _days(stats.international_games) == ["2025-10-05"]
    assert _days(stats.trophy_games) == ["2025-10-15"]
    assert len(stats.league_games) == 5 and len(stats.official_games) == 7


def test_game_of_a_competition_with_no_catalog_row_is_in_no_flag_filter():
    stats = BasketballGamesStats([_game("2025-10-01", "הפועל תל אביב", (90, 80), competition="גביע הפלא")])

    assert len(stats.league_games) == len(stats.official_games) == len(stats.international_games) == 0


def test_filters_by_result(stats):
    assert _days(stats.maccabi_losses) == ["2025-10-09"]
    assert len(stats.maccabi_wins) == 5
    assert len(stats.games_with_result) == 6
    assert _days(stats.technical_result_games) == ["2026-10-20"]
    assert _days(stats.overtime_games) == ["2025-10-09"]


def test_filters_chain_and_describe_themselves(stats):
    chained = stats.league_games.away_games.maccabi_losses

    assert _days(chained) == ["2025-10-09"]
    assert chained.description == "League games -> Away games -> Maccabi losses"
    assert repr(stats.get_games_by_season("1900")) == "Season: 1900 | 0 basketball games"
    assert repr(chained) == ("League games -> Away games -> Maccabi losses | 1 basketball games "
                             "| (from 09-10-2025 to 09-10-2025)")


def test_date_filters_include_the_day_itself_and_accept_text_like_football(stats):
    assert _days(stats.played_before("2025-10-05")) == ["1972-10-06", "2025-10-01", "2025-10-05"]
    assert _days(stats.played_after(datetime.date(2025, 10, 15))) == ["2025-10-15", "2026-10-20"]
    assert _days(stats.played_after(datetime.datetime(2026, 10, 20, 21, 5))) == ["2026-10-20"]
    assert _days(stats.played_at("2025-10-05")) == ["2025-10-05"]
    assert len(stats.played_before("2000")) == 1
    assert (stats.first_game_date, stats.last_game_date) == ("06-10-1972", "20-10-2026")


def test_game_with_no_date_is_last_and_in_no_date_filter_or_streak():
    no_date_loss = game_from_cargo({"_pageName": "כדורסל:משחק בלי תאריך", "TotalPointsMaccabi": 60,
                                    "TotalPointsOpponent": 70}, CATALOG)
    stats = BasketballGamesStats([no_date_loss, WIN_1, WIN_2])

    assert stats[-1] is no_date_loss
    assert len(stats.played_before("2030-01-01")) == 2
    assert (stats.first_game_date, stats.last_game_date) == ("01-10-2025", "05-10-2025")
    # It has no place in the order, so it does not end the current run of wins
    assert len(stats.streaks.get_current_wins_streak()) == 2
    assert len(stats.streaks.get_longest_losses_streak_games()) == 0
    assert BasketballGamesStats([no_date_loss]).first_game_date is None


def test_free_style_filters(stats):
    assert len(stats.get_games_against_team("הפועל תל אביב")) == 2
    assert len(stats.get_games_by_competition(["יורוליג", "גביע המדינה"])) == 2
    assert _days(stats.get_games_by_coach("דייוויד בלאט")) == ["2026-10-20"]
    assert len(stats.get_games_by_season("2025/26")) == 5
    # Listed in the box score against Real, but did not play
    assert len(stats.get_games_by_player_name("רומן סורקין")) == 3
    assert len(stats.get_games_by_played_player_name("רומן סורקין")) == 2


def test_available_values(stats):
    assert stats.available_seasons == ["1972/73", "2025/26", "2026/27"]
    assert stats.available_coaches == ["דייוויד בלאט", "יהושע רוזין", "עודד קטש"]
    assert stats.available_players_names == ["טל ברודי", "רומן סורקין", "תמיר בלאט"]


def test_results_count_an_awarded_game_as_a_win_and_skip_the_game_with_no_result(stats):
    results = stats.results

    assert (results.total_games_count, results.wins_count, results.losses_count) == (7, 5, 1)
    # A fraction like football's, out of the six games that have a winner
    assert results.wins_percentage == 0.833 and results.losses_percentage == 0.167
    # The awarded game's official 20:0 is not points from the court
    assert results.total_points_for_maccabi == 90 + 100 + 70 + 88 + 95
    assert results.total_points_diff_for_maccabi == results.total_points_for_maccabi - (80 + 70 + 75 + 60 + 60)


def test_biggest_games_leave_out_awarded_scores(stats):
    assert _days(stats.results.biggest_wins(2)) == ["1972-10-06", "2025-10-05"]
    assert _days(stats.results.biggest_losses()) == ["2025-10-09"]
    assert _days(stats.results.highest_scoring_games(1)) == ["2025-10-01"]
    assert _days(stats.results.most_points_for_maccabi_games(1)) == ["2025-10-05"]


def test_empty_collection_has_zero_percentages():
    results = BasketballGamesStats([]).results

    assert results.wins_percentage == 0.0 and results.total_points_for_maccabi == 0


def test_streak_skips_the_game_with_no_result(stats):
    after_the_loss = stats.played_after("2025-10-09")

    # No result on 12.10, then two wins: the game with no result neither breaks nor counts
    assert _days(after_the_loss.streaks.get_longest_wins_streak_games()) == ["2025-10-15", "2026-10-20"]
    assert _days(after_the_loss.streaks.get_current_wins_streak()) == ["2025-10-15", "2026-10-20"]


def test_longest_and_current_streaks(stats):
    streaks = stats.streaks

    assert _days(streaks.get_longest_wins_streak_games()) == ["1972-10-06", "2025-10-01", "2025-10-05"]
    assert _days(streaks.get_longest_losses_streak_games()) == ["2025-10-09"]
    assert len(streaks.get_current_wins_streak()) == 2
    assert len(streaks.get_current_losses_streak()) == 0


def test_streak_follows_the_filter(stats):
    # In the league alone the Euroleague win is not there, so the loss follows two league wins
    assert _days(stats.league_games.streaks.get_longest_wins_streak_games()) == ["1972-10-06", "2025-10-01"]


def test_most_played_counts_only_games_played(stats):
    assert stats.players.most_played == [("תמיר בלאט", 4), ("רומן סורקין", 2), ("טל ברודי", 1)]
    assert stats.players.most_starting_five == [("תמיר בלאט", 2)]
    assert dict(stats.players.most_captains) == {"תמיר בלאט": 1, "טל ברודי": 1}


def test_points_total_says_how_many_games_had_data(stats):
    scorers = stats.players.best_scorers

    assert [(total.name, total.value, total.games_with_data) for total in scorers] == [
        ("תמיר בלאט", 60, 4), ("רומן סורקין", 42, 2), ("טל ברודי", 30, 1)]


def test_stat_the_old_box_score_did_not_record_is_not_counted_as_zero(stats):
    assisters = stats.players.best_assisters

    # The 1972 game stored 0 assists for everyone: it is not a game with assists data,
    # and neither is the loss, where nobody has any
    assert [(total.name, total.value, total.games_with_data) for total in assisters] == [
        ("תמיר בלאט", 20, 2), ("רומן סורקין", 1, 1)]
    assert stats.players.best_rebounders == []


def test_played_player_with_no_points_typed_in_is_not_counted_as_a_game_with_points():
    game = _game("1975-01-01", "הפועל רמת גן", (80, 70), players=[_player("טל ברודי", 30), _player("מיקי ברקוביץ'")])
    totals = BasketballGamesStats([game]).players.best_scorers

    assert totals == [("טל ברודי", 30, 1)]


def test_player_total_unpacks_like_a_tuple(stats):
    name, value, games_with_data = stats.players.best_scorers[0]

    assert (name, value, games_with_data) == ("תמיר בלאט", 60, 4)


def test_filtered_games_keep_the_player_rows_of_no_game():
    orphan = ("כדורסל:משחק שנמחק", 0, player_from_cargo(_player("חיים תור", 6)))
    stats = BasketballGamesStats(ALL_GAMES, [orphan])

    assert stats.league_games.home_games.player_rows_without_game == [orphan]
    assert stats.streaks.get_longest_wins_streak_games().player_rows_without_game == [orphan]


def test_referees_and_non_official_games():
    friendly_flags = competition_flags_from_cargo({"CurrentName": "משחק ידידות"})
    refereed = game_from_cargo({"_pageName": "כדורסל:משחק ידידות", "Date": "2025-09-01", "Competition": "ידידות",
                                "MainReferee": "עופר מנהיים", "AssistantReferees": ["כפיר מועלם"],
                                "TotalPointsMaccabi": 80, "TotalPointsOpponent": 70}, {"ידידות": friendly_flags})
    stats = BasketballGamesStats([refereed, WIN_1])

    assert stats.available_referees == ["כפיר מועלם", "עופר מנהיים"]
    assert len(stats.get_games_by_referee("כפיר מועלם")) == 1
    assert _days(stats.non_official_games) == ["2025-09-01"]
    assert _days(stats.official_games) == ["2025-10-01"]


def test_best_single_games(stats):
    best = stats.players.get_best_single_games("points", limit=2)

    assert [(name, value, str(game.date)) for name, value, game in best] == [
        ("טל ברודי", 30, "1972-10-06"), ("רומן סורקין", 30, "2025-10-01")]


def test_unknown_stat_is_refused(stats):
    with pytest.raises(ValueError, match="Unknown player stat"):
        stats.players.get_players_total("goals")
    with pytest.raises(ValueError, match="Unknown player stat"):
        stats.players.get_best_single_games("goals")


def test_player_listed_twice_in_a_game_counts_the_game_once_and_both_lines():
    game = _game("2000-04-03", "גליל עליון", (90, 80), players=[_player("איציק כהן", 4), _player("איציק כהן", 6)])
    players = BasketballGamesStats([game]).players

    assert players.most_played == [("איציק כהן", 1)]
    assert [(total.value, total.games_with_data) for total in players.best_scorers] == [(10, 1)]


def test_records_by_opponent_coach_and_season(stats):
    hapoel = stats.opponents[0]
    assert (hapoel.name, hapoel.games_count, hapoel.wins_count, hapoel.losses_count) == ("הפועל תל אביב", 2, 1, 1)
    assert (hapoel.points_for_maccabi, hapoel.points_against_maccabi, hapoel.wins_percentage) == (160, 155, 0.5)

    katash = stats.coaches[0]
    assert (katash.name, katash.games_count, katash.wins_count, katash.losses_count) == ("עודד קטש", 5, 3, 1)
    assert katash.wins_percentage == 0.75

    blatt = stats.coaches[-1]
    # His only game was awarded: a win, and no points from the court
    assert (blatt.name, blatt.wins_count, blatt.points_for_maccabi) == ("דייוויד בלאט", 1, 0)

    assert [(record.name, record.games_count) for record in stats.seasons] == [
        ("1972/73", 1), ("2025/26", 5), ("2026/27", 1)]
