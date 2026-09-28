from datetime import date

from maccabipediabot.common.page_names import (
    build_football_game_page_name,
    build_basketball_game_page_name,
    build_volleyball_game_page_name,
)


def test_build_football_game_page_name():
    result = build_football_game_page_name(
        game_date=date(1977, 5, 14),
        home_team='מכבי תל אביב',
        away_team='הפועל תל אביב',
        competition='ליגת העל',
    )
    assert result == 'משחק:14-05-1977 מכבי תל אביב נגד הפועל תל אביב - ליגת העל'


def test_build_basketball_game_page_name():
    result = build_basketball_game_page_name(
        game_date=date(2004, 4, 29),
        home_team='מכבי תל אביב',
        away_team='סקאליני בולוניה',
        competition='יורוליג',
    )
    assert result == 'כדורסל:29-04-2004 מכבי תל אביב נגד סקאליני בולוניה - יורוליג'


def test_build_basketball_game_page_name_shortens_winner_cup():
    """Existing Winner Cup pages are titled "גביע ווינר", not the stored "גביע ווינר סל"."""
    result = build_basketball_game_page_name(
        game_date=date(2025, 9, 26),
        home_team='מכבי תל אביב',
        away_team='הפועל ירושלים',
        competition='גביע ווינר סל',
    )
    assert result == 'כדורסל:26-09-2025 מכבי תל אביב נגד הפועל ירושלים - גביע ווינר'


def test_build_volleyball_game_page_name():
    result = build_volleyball_game_page_name(
        game_date=date(1999, 11, 20),
        home_team='מכבי תל אביב',
        away_team='הפועל תל אביב',
        competition='ליגת העל בכדורעף',
    )
    assert result == 'כדורעף:20-11-1999 מכבי תל אביב נגד הפועל תל אביב - ליגת העל בכדורעף'
