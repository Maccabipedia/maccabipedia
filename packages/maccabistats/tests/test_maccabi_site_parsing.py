"""Club-site parsing, on HTML trimmed from the 14-09-2026 derby (maccabi-tlv.co.il)."""
from datetime import timedelta

from bs4 import BeautifulSoup

from maccabistats.models.player_game_events import GameEventTypes
from maccabistats.models.team_in_game import TeamInGame
from maccabistats.parse.maccabi_tlv_site.game_events_parser import MaccabiSiteGameEventsParser
from maccabistats.parse.maccabi_tlv_site.team_parser import MaccabiSiteTeamParser
from maccabistats.parse.name_normalization import normalize_name

_CARD_ICONS = "https://cdn.maccabi-tlv.co.il/wp-content/themes/maccabitlv/images/"

_OPPONENT_SQUADS_HTML = f"""
<div><ul>
<li class="name"><b>1</b>הפועל תל אביב</li>
<li><b>11</b>סתיו טוריאל <div class="icons team-players goals" id="p1-goal">33'</div>
<div class="icons team-players" id="p1-exchange"></div>
<div class="icons team-players" id="p1-red">45' <img src="{_CARD_ICONS}yellow-red.png"/></div></li>
<li><b>5</b>פרנאן מאיימבו <div class="icons team-players goals" id="p2-goal"></div>
<div class="icons team-players" id="p2-exchange"></div>
<div class="icons team-players" id="p2-red">45' <img src="{_CARD_ICONS}yellow.png"/></div></li>
</ul></div>
<div><ul></ul></div>
<div><ul><li>אליניב ברדה</li></ul></div>
"""

# The events page lists events newest first
_EVENTS_HTML = """
<article><div class="play-by-play-homepage"><ul class="play-by-play">
<li class="yellow"><div class="min">45</div><p>כרטיס צהוב לפרנאן מאיימבו</p></li>
<li class="secondyellow"><div class="min">45</div><p>כרטיס צהוב שני לסתיו טוריאל</p></li>
<li class="yellow"><div class="min">39</div><p>כרטיס צהוב לסתיו טוריאל</p></li>
</ul></div></article>
"""


def _parse_opponent_team() -> TeamInGame:
    squad_divs = BeautifulSoup(_OPPONENT_SQUADS_HTML, "html.parser").find_all("div", recursive=False)
    return MaccabiSiteTeamParser.parse_team(squad_divs, "הפועל תל אביב", 1)


def _card_events(team: TeamInGame, player_name: str) -> list[tuple[GameEventTypes, timedelta]]:
    player = next(player for player in team.players if player.name == player_name)
    card_events = [event for event in player.events if "Card" in event.event_type.value]
    return [(event.event_type, event.time_occur) for event in sorted(card_events, key=lambda event: (event.time_occur, event.event_type.value))]


def test_geresh_becomes_apostrophe():
    assert normalize_name("ג׳יימס  טברנייר") == "ג'יימס טברנייר"


def test_yellow_red_icon_is_a_second_yellow_not_a_red():
    opponent = _parse_opponent_team()

    assert _card_events(opponent, "סתיו טוריאל") == [(GameEventTypes.SECOND_YELLOW_CARD, timedelta(minutes=45))]
    assert _card_events(opponent, "פרנאן מאיימבו") == [(GameEventTypes.YELLOW_CARD, timedelta(minutes=45))]


def test_sent_off_players_earlier_yellow_becomes_the_first_yellow():
    maccabi = TeamInGame("מכבי תל אביב", "קני מילר", 4, [])
    events_page = BeautifulSoup(_EVENTS_HTML, "html.parser")

    _, opponent = MaccabiSiteGameEventsParser(maccabi, _parse_opponent_team(), events_page, "derby").enrich_teams_with_events()

    assert _card_events(opponent, "סתיו טוריאל") == [(GameEventTypes.FIRST_YELLOW_CARD, timedelta(minutes=39)),
                                                     (GameEventTypes.SECOND_YELLOW_CARD, timedelta(minutes=45))]
    assert _card_events(opponent, "פרנאן מאיימבו") == [(GameEventTypes.YELLOW_CARD, timedelta(minutes=45))]


def _enrich_with_events(events_html: str) -> TeamInGame:
    maccabi = TeamInGame("מכבי תל אביב", "קני מילר", 4, [])
    events_page = BeautifulSoup(f'<article><div class="play-by-play-homepage"><ul class="play-by-play">'
                                f'{events_html}</ul></div></article>', "html.parser")
    _, opponent = MaccabiSiteGameEventsParser(maccabi, _parse_opponent_team(), events_page, "derby").enrich_teams_with_events()
    return opponent


def test_first_yellow_in_the_same_stoppage_time_minute_is_the_first_yellow():
    opponent = _enrich_with_events(
        '<li class="secondyellow"><div class="min">45</div><p>כרטיס צהוב שני לסתיו טוריאל</p></li>'
        '<li class="yellow"><div class="min">45</div><p>כרטיס צהוב לסתיו טוריאל</p></li>')

    assert _card_events(opponent, "סתיו טוריאל") == [(GameEventTypes.FIRST_YELLOW_CARD, timedelta(minutes=45)),
                                                     (GameEventTypes.SECOND_YELLOW_CARD, timedelta(minutes=45))]


def test_red_event_at_the_second_yellow_minute_is_not_a_second_sending_off():
    opponent = _enrich_with_events(
        '<li class="red"><div class="min">45</div><p>כרטיס אדום לסתיו טוריאל</p></li>')

    assert _card_events(opponent, "סתיו טוריאל") == [(GameEventTypes.SECOND_YELLOW_CARD, timedelta(minutes=45))]
