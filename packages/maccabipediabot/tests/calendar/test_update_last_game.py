from unittest.mock import patch

from maccabipediabot.calendar import main

_LAST_GAME = {
    'summary': 'מכבי תל אביב נגד הפועל באר שבע',
    'start': {'dateTime': '2026-05-25T20:00:00'},
}


def test_update_last_game_skips_when_no_calendar_event():
    """End of season: the last played game has no event at/after it in the calendar.

    fetch_games_from_calendar returns [] and update_last_game must skip gracefully
    instead of raising IndexError (the bug that failed the scheduled football
    calendar workflow every run once the season ended).
    """
    with patch.object(main, 'fetch_games_from_maccabi_tlv_site', return_value=[_LAST_GAME]), \
            patch.object(main, 'fetch_games_from_calendar', return_value=[]), \
            patch.object(main, 'update_existing_event') as update_existing_event:
        main.update_last_game('http://example.com/season', 'calendar-id')

    update_existing_event.assert_not_called()


def test_update_last_game_skips_when_no_game_on_site():
    """The site has no last game to read; update_last_game must skip, not raise."""
    with patch.object(main, 'fetch_games_from_maccabi_tlv_site', return_value=[]), \
            patch.object(main, 'fetch_games_from_calendar') as fetch_games_from_calendar, \
            patch.object(main, 'update_existing_event') as update_existing_event:
        main.update_last_game('http://example.com/season', 'calendar-id')

    fetch_games_from_calendar.assert_not_called()
    update_existing_event.assert_not_called()
