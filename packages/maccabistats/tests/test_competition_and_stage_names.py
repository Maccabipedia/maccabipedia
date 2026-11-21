"""The competition is the plain name and the stage is written the way the wiki's editors write it.

Values are the ones the bot wrote on real pages and the ones Oren then fixed them to, read from the
page histories (e.g. the 2026/27 Sheriff Tiraspol and 2025/26 Dinamo Kyiv qualifier pages).
"""
import datetime
from types import SimpleNamespace

import pytest

from maccabistats.models.team_in_game import TeamInGame
from maccabistats.parse import general_fixes
from maccabistats.parse.maccabi_tlv_site.european_stages import fix_european_stages
from game_fixtures import _game

fix_competitions_names = getattr(general_fixes, "__fix_competitions_names")


def _european_game(competition: str, fixture: str, date: datetime.datetime, opponent: str, season: str = "2026/27"):
    return _game(
        competition=competition, fixture=fixture, date=date, stadium="בלומפילד", referee="ref",
        home_team=TeamInGame("מכבי תל אביב", "מאמן", 1, []),
        away_team=TeamInGame(opponent, "מאמן", 0, []),
        season=season,
    )


def _games(*games):
    return SimpleNamespace(games=list(games))


@pytest.mark.parametrize("raw_competition, plain_competition", [
    ("מוקדמות הליגה האירופית", "הליגה האירופית"),
    ("מוקדמות ליגה אירופית", "הליגה האירופית"),
    ("פלייאוף הליגה האירופית", "הליגה האירופית"),
    ("פלייאוף אירופה ליג", "הליגה האירופית"),
    ("מוקדמות ליגת האלופות", "ליגת האלופות"),
    ("מוקדמות קונפרנס ליג", "הליגה האזורית"),
    ("קונפרנס ליג", "הליגה האזורית"),
])
def test_stage_words_leave_the_competition_name(raw_competition, plain_competition):
    game = _european_game(raw_competition, "סיבוב 2", datetime.datetime(2026, 7, 23), "שריף טירספול")
    fix_competitions_names(game)
    assert game.competition == plain_competition
    assert game.fixture == "סיבוב 2"


def test_playoff_competition_without_a_round_keeps_the_playoff_stage():
    game = _european_game("פלייאוף הליגה האירופית", "No round found", datetime.datetime(2018, 8, 23),
                          "סרפסבורג 08", season="2018/19")
    fix_competitions_names(game)
    assert (game.competition, game.fixture) == ("הליגה האירופית", "פלייאוף")


def test_no_best_name_carries_a_stage_word():
    for best_name, _ in general_fixes._competitions_name_fixes:
        assert not best_name.startswith(("מוקדמות", "פלייאוף")), best_name


def test_qualifier_round_becomes_a_word_with_the_leg():
    first_leg = _european_game("הליגה האירופית", "סיבוב 2", datetime.datetime(2026, 7, 23), "שריף טירספול")
    second_leg = _european_game("הליגה האירופית", "סיבוב 2", datetime.datetime(2026, 7, 30), "שריף טירספול")
    third_round = _european_game("הליגה האירופית", "סיבוב 3", datetime.datetime(2026, 8, 6), 'צסק"א סופיה')
    fix_european_stages(_games(second_leg, third_round, first_leg))
    assert first_leg.fixture == "סיבוב שני - משחק 1"
    assert second_leg.fixture == "סיבוב שני - משחק 2"
    assert third_round.fixture == "סיבוב שלישי - משחק 1"


def test_playoff_and_knockout_rounds_get_the_leg():
    playoff = _european_game("הליגה האירופית", "פלייאוף", datetime.datetime(2025, 8, 21), "דינמו קייב", "2025/26")
    last_16 = _european_game("הליגה האזורית", "שמינית גמר", datetime.datetime(2024, 3, 7), "אולימפיאקוס", "2023/24")
    fix_european_stages(_games(playoff, last_16))
    assert playoff.fixture == "פלייאוף - משחק 1"
    assert last_16.fixture == "שמינית גמר - משחק 1"


@pytest.mark.parametrize("fixture", ["מחזור 1", "גמר", "", "No round found", "סיבוב שני - משחק 1"])
def test_stages_without_legs_stay_as_given(fixture):
    game = _european_game("הליגה האירופית", fixture, datetime.datetime(2025, 9, 24), "פאוק סלוניקי", "2025/26")
    fix_european_stages(_games(game))
    assert game.fixture == fixture


def test_same_round_in_another_season_or_competition_is_a_separate_tie():
    this_season = _european_game("ליגת האלופות", "סיבוב 2", datetime.datetime(2025, 7, 22), "פאפוס", "2025/26")
    next_season = _european_game("ליגת האלופות", "סיבוב 2", datetime.datetime(2026, 7, 21), "פאפוס", "2026/27")
    other_competition = _european_game("הליגה האירופית", "סיבוב 2", datetime.datetime(2025, 7, 30), "פאפוס",
                                       "2025/26")
    fix_european_stages(_games(this_season, next_season, other_competition))
    assert this_season.fixture == "סיבוב שני - משחק 1"
    assert next_season.fixture == "סיבוב שני - משחק 1"
    assert other_competition.fixture == "סיבוב שני - משחק 1"


def test_domestic_games_are_untouched():
    cup_game = _european_game("גביע המדינה", "סיבוב 2", datetime.datetime(2026, 1, 1), "הפועל עכו")
    fix_european_stages(_games(cup_game))
    assert cup_game.fixture == "סיבוב 2"
