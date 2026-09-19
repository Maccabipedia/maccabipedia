from datetime import timedelta

import pytest

from maccabipediabot.common.maccabistats_player_event import PlayerEvent


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_parse_basic_goal():
    event = PlayerEvent.from_maccabipedia_format("יוסי כהן::10::גול::45::מכבי")
    assert event.name == "יוסי כהן"
    assert event.number == "10"
    assert event.event_type == "גול"
    assert event.sub_event_type is None
    assert event.minute_occur == 45
    assert event.maccabi_player is True
    assert event.team == "מכבי"
    assert event.game_part is None


def test_parse_event_with_sub_event():
    event = PlayerEvent.from_maccabipedia_format("יוסי כהן::10::גול-פנדל::45::מכבי")
    assert event.event_type == "גול"
    assert event.sub_event_type == "פנדל"


def test_parse_event_with_game_part():
    event = PlayerEvent.from_maccabipedia_format("יוסי כהן::10::גול::45::מכבי::מחצית שניה")
    assert event.game_part == "מחצית שניה"


def test_parse_no_number_uses_sentinel():
    event = PlayerEvent.from_maccabipedia_format("יוסי כהן::אין-מספר::הרכב::0::מכבי")
    assert event.number == "אין-מספר"


def test_parse_invalid_format_raises():
    with pytest.raises(TypeError):
        PlayerEvent.from_maccabipedia_format("שם בלבד")


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

def test_roundtrip_simple():
    original = "יוסי כהן::10::גול::45::מכבי"
    assert PlayerEvent.from_maccabipedia_format(original).__maccabipedia__().strip("\n") == original


def test_roundtrip_with_sub_event():
    original = "יוסי כהן::10::גול-פנדל::45::מכבי"
    assert PlayerEvent.from_maccabipedia_format(original).__maccabipedia__().strip("\n") == original


def test_roundtrip_with_game_part():
    original = "יוסי כהן::10::גול::45::מכבי::מחצית שניה"
    assert PlayerEvent.from_maccabipedia_format(original).__maccabipedia__().strip("\n") == original


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

def test_maccabi_squad_before_opponent_squad():
    maccabi = PlayerEvent("מכבי", "1", timedelta(0), "הרכב", None, True)
    opponent = PlayerEvent("יריב", "1", timedelta(0), "הרכב", None, False)
    assert maccabi < opponent


def test_cards_sorted_by_minute():
    earlier = PlayerEvent("שחקן א", "5", timedelta(minutes=30), "כרטיס צהוב", None, True)
    later = PlayerEvent("שחקן ב", "8", timedelta(minutes=60), "כרטיס צהוב", None, True)
    assert earlier < later


# ---------------------------------------------------------------------------
# maccabistats translation
# ---------------------------------------------------------------------------

def test_headed_assist_produces_bishul_negisha():
    """Verify that GOAL_ASSIST + GoalTypes.HEADER → בישול-נגיחה output.

    This is a regression test: the wiki template was updated to accept
    בישול-נגיחה (subtype 47) and the bot must keep producing it.
    """
    from maccabistats.models.player_game_events import GameEventTypes, GoalTypes

    event = PlayerEvent.from_maccabistats_event_type(
        name="ניר בלקין",
        number=3,
        time_occur=timedelta(minutes=55),
        event_type=GameEventTypes.GOAL_ASSIST,
        sub_event_type=GoalTypes.HEADER,
        maccabi_player=True,
    )

    assert event.event_type == "בישול"
    assert event.sub_event_type == "נגיחה"
    assert "בישול-נגיחה" in event.__maccabipedia__()


def test_first_and_second_yellow_are_yellow_card_sub_types():
    from maccabistats.models.player_game_events import GameEventTypes

    first_yellow = PlayerEvent.from_maccabistats_event_type(
        "ערן זהבי", 7, timedelta(minutes=39), GameEventTypes.FIRST_YELLOW_CARD, None, maccabi_player=True)
    second_yellow = PlayerEvent.from_maccabistats_event_type(
        "ערן זהבי", 7, timedelta(minutes=45), GameEventTypes.SECOND_YELLOW_CARD, None, maccabi_player=True)

    assert first_yellow.__maccabipedia__().strip() == "ערן זהבי::7::כרטיס צהוב-ראשון::39::מכבי"
    assert second_yellow.__maccabipedia__().strip() == "ערן זהבי::7::כרטיס צהוב-שני::45::מכבי"
