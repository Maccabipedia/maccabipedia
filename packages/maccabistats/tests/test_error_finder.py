import datetime

from maccabistats.error_finder.error_finder import ErrorsFinder
from maccabistats.stats.maccabi_games_stats import MaccabiGamesStats

from game_fixtures import _game, _lineup, _player
from players_data_fixtures import create_stub_players_data

from maccabistats.models.team_in_game import TeamInGame


def _league_game(fixture: str, date: datetime.datetime, season: str):
    maccabi = TeamInGame("מכבי תל אביב", "אגון פולק", 1, [_player("יוסף מרימוביץ'", 4, [_lineup()])])
    opponent = TeamInGame("הפועל תל אביב", "", 0, [])
    return _game(competition="הליגה הארצית", fixture=fixture, date=date, stadium="", referee="",
                 home_team=maccabi, away_team=opponent, season=season)


def _stats(games) -> MaccabiGamesStats:
    return MaccabiGamesStats(games, players_data=create_stub_players_data())


class TestDoubleLeagueFixtures:
    def test_games_without_a_fixture_number_are_not_doubles(self):
        games = [_league_game("", datetime.datetime(1932, 10, 29), "1932/33"),
                 _league_game("", datetime.datetime(1932, 11, 5), "1932/33"),
                 _league_game("גמר", datetime.datetime(1933, 3, 4), "1932/33")]

        assert ErrorsFinder(_stats(games)).get_double_league_games_fixtures() == []

    def test_same_fixture_number_twice_is_a_double(self):
        games = [_league_game("מחזור 4", datetime.datetime(1945, 1, 6), "1944/45"),
                 _league_game("מחזור 4", datetime.datetime(1945, 1, 27), "1944/45"),
                 _league_game("מחזור 8", datetime.datetime(1945, 6, 2), "1944/45")]

        doubles = ErrorsFinder(_stats(games)).get_double_league_games_fixtures()

        assert [key for key, _ in doubles] == ["Season 1944/45 Fixture 4"]
        assert len(doubles[0][1]) == 2


class TestLeagueGamesWithoutFixture:
    def test_only_league_games_with_no_fixture_number_are_reported(self):
        cup_game = _league_game("", datetime.datetime(1938, 1, 28), "1938")
        cup_game.competition = "הגביע הארץ ישראלי"
        games = [_league_game("", datetime.datetime(1932, 10, 29), "1932/33"),
                 _league_game("ליגת תל אביב", datetime.datetime(1939, 1, 14), "1938"),
                 _league_game("מחזור 4", datetime.datetime(1945, 1, 6), "1944/45"),
                 cup_game]

        flagged = ErrorsFinder(_stats(games)).get_league_games_without_fixture()

        assert [str(game.date.date()) for game in flagged] == ["1932-10-29", "1939-01-14"]


class TestIncorrectSeason:
    def test_game_outside_its_season_is_flagged(self):
        games = [_league_game("מחזור 1", datetime.datetime(1948, 1, 3), "1946/47")]

        flagged = ErrorsFinder(_stats(games)).get_games_with_incorrect_season()

        assert [(season, date) for season, date, _ in flagged] == [("1946/47", "1948-01-03")]

    def test_single_year_season_accepts_that_year_only(self):
        games = [_league_game("", datetime.datetime(1939, 10, 7), "1939"),
                 _league_game("", datetime.datetime(1940, 4, 23), "1939")]

        flagged = ErrorsFinder(_stats(games)).get_games_with_incorrect_season()

        assert [date for _, date, _ in flagged] == ["1940-04-23"]

    def test_known_prolonged_seasons_are_not_flagged(self):
        games = [_league_game("ליגת תל אביב", datetime.datetime(1939, 1, 14), "1938"),
                 _league_game("פלייאוף אליפות - משחק 4", datetime.datetime(1943, 9, 18), "1941/42"),
                 _league_game("", datetime.datetime(1944, 1, 1), "1941/42")]

        flagged = ErrorsFinder(_stats(games)).get_games_with_incorrect_season()

        assert [date for _, date, _ in flagged] == ["1944-01-01"]
