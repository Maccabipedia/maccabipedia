from datetime import timedelta

from maccabipediabot.common.maccabistats_player_event import PlayerEvent
from maccabipediabot.football.game_page_fixes import (mark_goalkeepers, mark_second_yellow_cards,
                                                      to_maccabipedia_name, to_maccabipedia_stadium)


def _event(name: str, number: str, event_type: str, minute: int, maccabi_player: bool) -> PlayerEvent:
    return PlayerEvent(name, number, timedelta(minutes=minute), event_type, None, maccabi_player)


def _as_wiki_lines(events: list[PlayerEvent]) -> list[str]:
    return [event.__maccabipedia__().strip() for event in events]


def test_geresh_becomes_apostrophe():
    assert to_maccabipedia_name("ג׳יימס טברנייר") == "ג'יימס טברנייר"


def test_bloomfield_gets_its_wiki_page_name():
    assert to_maccabipedia_stadium("בלומפילד") == "אצטדיון בלומפילד"


def test_unknown_stadium_is_kept():
    assert to_maccabipedia_stadium("אצטדיון טדי") == "אצטדיון טדי"


def test_two_yellows_become_first_and_second_and_the_implied_red_is_dropped():
    """The 14-09-2026 derby, as the club site reported the sending-off."""
    events = [
        _event("סתיו טוריאל", "11", "כרטיס צהוב", 39, False),
        _event("פרנאן מאיימבו", "5", "כרטיס צהוב", 45, False),
        _event("סתיו טוריאל", "11", "כרטיס אדום", 45, False),
        _event("סתיו טוריאל", "11", "כרטיס צהוב", 45, False),
    ]

    assert _as_wiki_lines(mark_second_yellow_cards(events)) == [
        "סתיו טוריאל::11::כרטיס צהוב-ראשון::39::יריבה",
        "פרנאן מאיימבו::5::כרטיס צהוב::45::יריבה",
        "סתיו טוריאל::11::כרטיס צהוב-שני::45::יריבה",
    ]


def test_straight_red_is_kept():
    events = [
        _event("סתיו טוריאל", "11", "כרטיס צהוב", 20, False),
        _event("סתיו טוריאל", "11", "כרטיס אדום", 70, False),
    ]

    assert _as_wiki_lines(mark_second_yellow_cards(events)) == [
        "סתיו טוריאל::11::כרטיס צהוב::20::יריבה",
        "סתיו טוריאל::11::כרטיס אדום::70::יריבה",
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
