"""Test that MaccabiGamesStats includes players data in pickle for offline loading."""

import pickle
from collections import defaultdict
from datetime import datetime

import pytest

from maccabistats.maccabipedia.players import MaccabiPediaPlayers, MaccabiPediaPlayerData
from maccabistats.models.game_data import GameData
from maccabistats.models.player_in_game import PlayerInGame
from maccabistats.models.team_in_game import TeamInGame
from maccabistats.stats.maccabi_games_stats import MaccabiGamesStats

_TEST_PLAYERS_DATA = {
    "שחקן א": MaccabiPediaPlayerData(name="שחקן א", birth_date=datetime(2000, 1, 1), is_home_player=True),
    "שחקן ב": MaccabiPediaPlayerData(name="שחקן ב", birth_date=datetime(1995, 6, 15), is_home_player=False),
}


@pytest.fixture(autouse=True)
def reset_players_singleton():
    yield
    MaccabiPediaPlayers._instance = None


def _make_game(date: datetime) -> GameData:
    """Create a minimal GameData for testing."""
    maccabi = TeamInGame(name="מכבי תל אביב", coach="מאמן", score=1, players=[
        PlayerInGame(name="שחקן א", number=7, game_events=[]),
    ])
    opponent = TeamInGame(name="הפועל תל אביב", coach="מאמן2", score=0, players=[
        PlayerInGame(name="יריב א", number=9, game_events=[]),
    ])
    return GameData(
        competition="ליגת העל", fixture="1", date_as_hebrew_string="",
        stadium="בלומפילד", crowd="1000", referee="שופט",
        home_team=maccabi, away_team=opponent,
        season_string="2024/25", half_parsed_events=[], date=date,
    )


def _make_players_instance():
    """Create a MaccabiPediaPlayers instance with test data (without network)."""
    instance = object.__new__(MaccabiPediaPlayers)
    instance._players_data = _TEST_PLAYERS_DATA
    instance.players_dates = defaultdict(MaccabiPediaPlayers.default_birth_day_value,
                                         {name: p.birth_date for name, p in _TEST_PLAYERS_DATA.items()})
    instance.home_players = {p.name for p in _TEST_PLAYERS_DATA.values() if p.is_home_player}
    MaccabiPediaPlayers._instance = instance
    return instance


# --- Core feature tests ---


def test_players_data_stored_as_attribute():
    """Players data should be stored as a regular attribute on MaccabiGamesStats."""
    players = _make_players_instance()
    games = [_make_game(datetime(2024, 9, 1))]
    stats = MaccabiGamesStats(games, players_data=players)

    assert stats.players_data is players
    assert stats.players_categories.maccabi_home_players_names == {"שחקן א"}


def test_pickle_roundtrip_preserves_players_data():
    """Pickling and unpickling should preserve the players data without crawling."""
    players = _make_players_instance()
    games = [_make_game(datetime(2024, 9, 1))]
    stats = MaccabiGamesStats(games, players_data=players)

    pickled = pickle.dumps(stats)
    MaccabiPediaPlayers._instance = None

    restored = pickle.loads(pickled)
    assert restored.players_data is not None
    assert restored.players_data.home_players == {"שחקן א"}
    assert restored.players_data.players_dates["שחקן ב"] == datetime(1995, 6, 15)


def test_filtered_stats_inherit_players_data(monkeypatch):
    """Filter properties (e.g. home_games) should inherit players data without crawling."""
    players = _make_players_instance()
    games = [_make_game(datetime(2024, 9, 1)), _make_game(datetime(2024, 10, 1))]
    stats = MaccabiGamesStats(games, players_data=players)

    monkeypatch.setattr(
        MaccabiPediaPlayers, '_crawl_players_data',
        staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("Should not crawl!"))),
    )
    MaccabiPediaPlayers._instance = None

    filtered = stats.maccabi_wins
    assert filtered.players_data is players
    assert filtered.players_categories.maccabi_home_players_names == {"שחקן א"}


def test_unpickle_then_filter_works_offline(monkeypatch):
    """After unpickling, creating filtered stats should work without internet."""
    players = _make_players_instance()
    games = [_make_game(datetime(2024, 9, 1)), _make_game(datetime(2024, 10, 1))]
    stats = MaccabiGamesStats(games, players_data=players)

    pickled = pickle.dumps(stats)
    MaccabiPediaPlayers._instance = None

    monkeypatch.setattr(
        MaccabiPediaPlayers, '_crawl_players_data',
        staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("Should not crawl!"))),
    )

    restored = pickle.loads(pickled)
    filtered = MaccabiGamesStats(restored.games, players_data=restored.players_data)
    assert filtered.players_categories.maccabi_home_players_names == {"שחקן א"}


def test_empty_games_works_with_players_data():
    """Creating MaccabiGamesStats with empty games and players data should work."""
    players = _make_players_instance()
    stats = MaccabiGamesStats([], players_data=players)
    assert len(stats) == 0
    assert stats.players_data is players


# --- Backward compatibility ---


def test_old_pickle_without_players_data_fails_with_clear_error():
    """Old pickles without players_data should fail with a clear RuntimeError."""
    players = _make_players_instance()
    games = [_make_game(datetime(2024, 9, 1))]
    stats = MaccabiGamesStats(games, players_data=players)

    # Simulate an old pickle by removing the attribute before pickling
    del stats.__dict__['players_data']
    pickled = pickle.dumps(stats)
    MaccabiPediaPlayers._instance = None

    with pytest.raises(RuntimeError, match="does not contain players_data"):
        pickle.loads(pickled)


# --- players_special_games ---


def test_players_special_games_uses_attribute():
    """players_special_games should get birth dates from the players_data attribute."""
    players = _make_players_instance()
    games = [_make_game(datetime(2024, 9, 1))]
    stats = MaccabiGamesStats(games, players_data=players)

    assert stats.players_special_games.players_birth_dates["שחקן א"] == datetime(2000, 1, 1)
    assert stats.players_special_games.players_birth_dates["שחקן ב"] == datetime(1995, 6, 15)


# --- Filter chain ---


def test_filter_chain_preserves_players_data(monkeypatch):
    """Multi-level filter chains should preserve players data throughout."""
    players = _make_players_instance()
    games = [_make_game(datetime(2024, 9, 1)), _make_game(datetime(2024, 10, 1))]
    stats = MaccabiGamesStats(games, players_data=players)

    monkeypatch.setattr(
        MaccabiPediaPlayers, '_crawl_players_data',
        staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("Should not crawl!"))),
    )
    MaccabiPediaPlayers._instance = None

    # Chain: home_games → maccabi_wins → players_categories
    chained = stats.home_games.maccabi_wins
    assert chained.players_data is players
    assert chained.players_categories.maccabi_home_players_names == {"שחקן א"}
    assert chained.players_special_games.players_birth_dates["שחקן א"] == datetime(2000, 1, 1)


# --- players_data is always required ---


def test_players_data_required_for_player_stats():
    """Without players_data, accessing player stats should fail."""
    games = [_make_game(datetime(2024, 9, 1))]
    with pytest.raises(TypeError):
        MaccabiGamesStats(games)


# --- goalkeepers ---


def test_goalkeepers_from_profiles_and_recent_games(monkeypatch):
    """Maccabi keepers come from their profile, others from 2+ games they kept goal in; one-word names are dropped."""
    crawled_rows = {
        "Profiles": [{"_pageName": "בוני גינצבורג", "MainPosition": 1},
                     {"_pageName": "ערן זהבי", "MainPosition": 4}],
        "Games_Events": [{"_pageName": "משחק א", "PlayerName": "דניאל טננבאום"},
                         {"_pageName": "משחק ב", "PlayerName": "דניאל טננבאום"},
                         {"_pageName": "משחק א", "PlayerName": "גינצבורג"},
                         {"_pageName": "משחק ב", "PlayerName": "גינצבורג"},
                         {"_pageName": "משחק ג", "PlayerName": "אבי נמני"}],
    }
    monkeypatch.setattr("maccabistats.maccabipedia.players.MaccabiPediaCargoChunksCrawler",
                        lambda tables_name, **kwargs: iter(crawled_rows[tables_name]))

    assert MaccabiPediaPlayers().goalkeepers == frozenset({"בוני גינצבורג", "דניאל טננבאום"})


def test_pickle_saved_before_goalkeepers_loads_with_none():
    players = _make_players_instance()

    restored = pickle.loads(pickle.dumps(players))

    assert restored.goalkeepers == frozenset()


def test_blocked_recent_goalkeepers_query_keeps_the_profiles_goalkeepers(monkeypatch):
    def crawler(tables_name, **kwargs):
        if tables_name == "Games_Events":
            raise ValueError("CargoExport returned a bare str, expected a list of rows")
        return iter([{"_pageName": "בוני גינצבורג", "MainPosition": 1}])

    monkeypatch.setattr("maccabistats.maccabipedia.players.MaccabiPediaCargoChunksCrawler", crawler)

    assert MaccabiPediaPlayers().goalkeepers == frozenset({"בוני גינצבורג"})
