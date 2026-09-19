from datetime import timedelta

from maccabipediabot.common.maccabistats_player_event import PlayerEvent
from maccabistats.models.player_game_events import GameEventTypes

from maccabipediabot.football.game_page_fixes import mark_goalkeepers


def _event(name: str, number: str, event_type: str, minute: int, maccabi_player: bool) -> PlayerEvent:
    return PlayerEvent(name, number, timedelta(minutes=minute), event_type, None, maccabi_player)


def _as_wiki_lines(events: list[PlayerEvent]) -> list[str]:
    return [event.__maccabipedia__().strip() for event in events]


def test_first_and_second_yellow_are_written_as_yellow_card_sub_types():
    first_yellow = PlayerEvent.from_maccabistats_event_type(
        "סתיו טוריאל", 11, timedelta(minutes=39), GameEventTypes.FIRST_YELLOW_CARD, None, maccabi_player=False)
    second_yellow = PlayerEvent.from_maccabistats_event_type(
        "סתיו טוריאל", 11, timedelta(minutes=45), GameEventTypes.SECOND_YELLOW_CARD, None, maccabi_player=False)

    assert _as_wiki_lines([first_yellow, second_yellow]) == [
        "סתיו טוריאל::11::כרטיס צהוב-ראשון::39::יריבה",
        "סתיו טוריאל::11::כרטיס צהוב-שני::45::יריבה",
    ]


def test_known_goalkeepers_are_marked_in_line_up_and_bench():
    events = [
        _event("אופק מליקה", "1", "הרכב", 0, True),
        _event("רז שלמה", "13", "הרכב", 0, True),
        _event("רועי משפתי", "90", "ספסל", 0, True),
        _event("אסף צור", "22", "הרכב", 0, False),
    ]

    mark_goalkeepers(events, {"אופק מליקה", "רועי משפתי", "אסף צור"})

    assert _as_wiki_lines(events) == [
        "אופק מליקה::1::הרכב-שוער::0::מכבי",
        "רז שלמה::13::הרכב::0::מכבי",
        "רועי משפתי::90::ספסל-שוער::0::מכבי",
        "אסף צור::22::הרכב-שוער::0::יריבה",
    ]


def test_goalkeeper_events_outside_the_squad_are_untouched():
    events = [_event("אופק מליקה", "1", "כרטיס צהוב", 30, True)]

    mark_goalkeepers(events, {"אופק מליקה"})

    assert _as_wiki_lines(events) == ["אופק מליקה::1::כרטיס צהוב::30::מכבי"]
