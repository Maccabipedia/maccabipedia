"""The season of a livescore stage decides which season's table template the scripts write,
and a game in play keeps them from writing at all."""
from datetime import date

import pytest

from maccabipediabot.basketball import livescore_table
from maccabipediabot.basketball.livescore_table import games_in_play, season_of_stage


def _stage(*starts: int) -> dict:
    return {"Events": [{"Esd": start} for start in starts]}


@pytest.mark.parametrize("starts, expected", [
    # Real first and last Esd of the 2026/27 payloads, fetched 2026-09-28.
    ((20270502180000, 20261010191500), "2026/27"),   # Israeli league, out of order
    ((20260924180000, 20270416203000), "2026/27"),   # EuroLeague
    # A stage whose first event falls before July started the previous autumn.
    ((20260310190000,), "2025/26"),
    ((19991015180000,), "1999/00"),                  # two-digit end year keeps its zero
    ((20260701000000,), "2026/27"),                  # July is the first month of a season
    ((20260630235959,), "2025/26"),                  # June is still the season before
    (("20261010191500",), "2026/27"),                # Esd as a string
])
def test_season_of_stage(starts, expected):
    assert season_of_stage(_stage(*starts)) == expected


def test_fetch_stage_raises_on_non_json_reply(monkeypatch):
    """A CDN error page must fail with its body, not a KeyError deep in the parsing."""
    class _HtmlResp:
        status_code = 503
        headers = {"Content-Type": "text/html"}
        text = "<html>Service Unavailable</html>"

    monkeypatch.setattr(livescore_table.requests, "get", lambda *args, **kwargs: _HtmlResp())
    with pytest.raises(RuntimeError, match="status=503"):
        livescore_table.fetch_stage("https://example.invalid/stage")


def test_season_of_stage_without_events_raises():
    """No dates means no season, and no template can be picked safely: fail, don't guess."""
    with pytest.raises(ValueError, match="no dated events"):
        season_of_stage({"Events": []})


_GAME_DAY = date(2026, 10, 17)


def _event(status: str, progress: int, start: int = 20261017191500, home: str = "Hapoel Jerusalem",
           away: str = "Hapoel Beer Sheva") -> dict:
    return {"Eps": status, "Epr": progress, "Esd": start, "T1": [{"Nm": home}], "T2": [{"Nm": away}]}


# The (Eps, Epr) pairs of every event in the real payloads, fetched 2026-10-17.
@pytest.mark.parametrize("status, progress", [("NS", 0), ("FT", 2), ("OT", 2)])
def test_games_not_started_or_over_are_not_in_play(status, progress):
    """"OT" is a EuroLeague game finished after overtime, not one still in it."""
    assert games_in_play({"Events": [_event(status, progress)]}, today=_GAME_DAY) == []


def test_a_game_in_progress_is_in_play():
    """2026-10-17: the table saved at 21:08 had Jerusalem - Beer Sheva at its second quarter."""
    stage = {"Events": [_event("FT", 2, 20261010191500), _event("Q2", 1), _event("NS", 0, 20261024191500)]}
    assert games_in_play(stage, today=_GAME_DAY) == ["Hapoel Jerusalem - Hapoel Beer Sheva (Q2)"]


@pytest.mark.parametrize("start", [20261016235959, 20261018000000])
def test_a_game_a_day_from_today_still_counts(start):
    """Esd is livescore's local time and the runner's day is UTC; a day either way covers it."""
    assert games_in_play({"Events": [_event("Q2", 1, start)]}, today=_GAME_DAY) != []


def test_a_game_stuck_in_play_stops_counting_after_a_day():
    """An old game left on an odd progress value must not keep the table frozen."""
    assert games_in_play({"Events": [_event("Int.", 1, 20261015191500)]}, today=_GAME_DAY) == []
