from maccabipediabot.football.opponent_goalkeepers import fetch_opponent_goalkeepers, trusted_goalkeeper_names


def _event(player_name: str, page_name: str) -> dict:
    return {"PlayerName": player_name, "_pageName": page_name}


def test_goalkeeper_of_two_games_is_trusted():
    events = [_event("בוני גינצבורג", "משחק א"), _event("בוני גינצבורג", "משחק ב")]

    assert trusted_goalkeeper_names(events) == frozenset({"בוני גינצבורג"})


def test_goalkeeper_of_a_single_game_is_dropped():
    """A single mark may be a mistake: an outfield player once got a bench keeper's mark."""
    events = [_event("בוני גינצבורג", "משחק א"), _event("דניאל טננבאום", "משחק א")]

    assert trusted_goalkeeper_names(events) == frozenset()


def test_two_events_in_the_same_game_are_one_game():
    events = [_event("בוני גינצבורג", "משחק א"), _event("בוני גינצבורג", "משחק א")]

    assert trusted_goalkeeper_names(events) == frozenset()


def test_one_word_names_are_dropped():
    """Old games list many players by one name (לוי, מזרחי), which matches outfield players today."""
    events = [_event("גינצבורג", "משחק א"), _event("גינצבורג", "משחק ב")]

    assert trusted_goalkeeper_names(events) == frozenset()


def test_the_query_asks_for_the_opponents_goalkeeper_events(monkeypatch):
    asked = {}

    def crawler(**kwargs):
        asked.update(kwargs)
        return iter([_event("בוני גינצבורג", "משחק א"), _event("בוני גינצבורג", "משחק ב")])

    monkeypatch.setattr("maccabipediabot.football.opponent_goalkeepers.MaccabiPediaCargoChunksCrawler", crawler)

    assert fetch_opponent_goalkeepers() == frozenset({"בוני גינצבורג"})
    assert asked["tables_name"] == "Games_Events"
    assert "SubType IN (111,211)" in asked["where_condition"]
    assert "Team=0" in asked["where_condition"]


def test_a_failed_query_returns_no_goalkeepers(monkeypatch):
    def crawler(**kwargs):
        raise ValueError("CargoExport returned a bare str, expected a list of rows")

    monkeypatch.setattr("maccabipediabot.football.opponent_goalkeepers.MaccabiPediaCargoChunksCrawler", crawler)

    assert fetch_opponent_goalkeepers() == frozenset()
