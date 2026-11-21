"""Today's title rule: everyone on a game sheet in a season gets every title won in it."""
from maccabipediabot.maintenance.football.player_titles.rule import (
    RULE,
    SeasonPlayed,
    Title,
    todays_rule,
)

STATE_CUP_2001 = Title("2000/01", "גביע המדינה")
TOTO_CUP_2001 = Title("2000/01", "גביע הטוטו")


def test_everyone_in_the_season_gets_every_title_won_in_it():
    played = [
        SeasonPlayed("כפיר אדרי", "2000/01"),
        SeasonPlayed("אבי נמני", "2000/01"),
        SeasonPlayed("אבי נמני", "1999/00"),
    ]

    credits = todays_rule([STATE_CUP_2001, TOTO_CUP_2001], played)

    assert credits == {
        STATE_CUP_2001: ["אבי נמני", "כפיר אדרי"],
        TOTO_CUP_2001: ["אבי נמני", "כפיר אדרי"],
    }


def test_a_title_with_no_players_is_kept_with_an_empty_list():
    state_cup_1967 = Title("1966/67", "גביע המדינה")

    credits = todays_rule([state_cup_1967], [SeasonPlayed("גיורא שפיגל", "1966/68")])

    assert credits == {state_cup_1967: []}


def test_a_player_listed_twice_is_credited_once():
    played = [SeasonPlayed("אבי נמני", "2000/01"), SeasonPlayed("אבי נמני", "2000/01")]

    assert todays_rule([STATE_CUP_2001], played) == {STATE_CUP_2001: ["אבי נמני"]}


def test_the_rule_in_use_is_todays_rule():
    assert RULE is todays_rule
