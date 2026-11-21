"""A new European qualifier game: the title suffix and |מפעל= are the same plain competition.

The raw values are what the club site gave for the 2026/27 Sheriff Tiraspol first leg, which the bot
saved as מפעל=מוקדמות הליגה האירופית, שלב=סיבוב 2 before Oren fixed it by hand.
"""
import datetime

from maccabistats.models.game_data import GameData
from maccabistats.models.team_in_game import TeamInGame
from maccabistats.parse import general_fixes
from maccabistats.parse.maccabi_tlv_site.european_stages import fix_european_stages

from maccabipediabot.common.maccabistats_player_event import MACCABI_TEAM, OPPONENT_TEAM
from maccabipediabot.football import gamesbot

fix_competitions_names = getattr(general_fixes, "__fix_competitions_names")
template_arguments_of = getattr(gamesbot, "__get_football_game_template_with_maccabistats_game_value")


class _Games:
    def __init__(self, games):
        self.games = games


def _sheriff_first_leg_as_the_site_gives_it() -> GameData:
    return GameData(
        competition="מוקדמות הליגה האירופית", fixture="סיבוב 2", date_as_hebrew_string="", stadium="שריף",
        crowd="", referee="Cant found referee",
        home_team=TeamInGame("שריף טירספול", "Cant found coach", 0, []),
        away_team=TeamInGame("מכבי תל אביב", "Cant found coach", 1, []),
        season_string="2026/27", half_parsed_events=[], date=datetime.datetime(2026, 7, 23, 19, 0),
    )


def test_title_suffix_and_competition_field_are_the_same_plain_name():
    game = _sheriff_first_leg_as_the_site_gives_it()
    fix_competitions_names(game)
    fix_european_stages(_Games([game]))

    page_name = gamesbot.generate_page_name_from_game(game)
    arguments = template_arguments_of(game, {MACCABI_TEAM: set(), OPPONENT_TEAM: set()})

    assert page_name.rsplit(" - ", 1)[-1] == arguments[gamesbot.COMPETITION] == "הליגה האירופית"
    assert arguments[gamesbot.ROUND_IN_COMPETITION] == "סיבוב שני - משחק 1"
