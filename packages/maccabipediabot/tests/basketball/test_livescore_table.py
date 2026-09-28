"""The season of a livescore stage decides which season's table template the scripts write."""
import pytest

from maccabipediabot.basketball import livescore_table
from maccabipediabot.basketball.livescore_table import season_of_stage


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
