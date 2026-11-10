"""Tests for listing videos through the YouTube Data API, which is how the scheduled run sees them.

The uploads playlist says nothing about which season a video belongs to. Getting that
wrong is invisible in the logs: the video is either dropped as unmatched or, worse,
matched against a game from the wrong season that shares a score and opponent.
"""
import json
import logging
from pathlib import Path

import pytest
import requests

from maccabipediabot.basketball.videos import youtube_api
from maccabipediabot.basketball.videos.inventory import VideoEntry

PAGE = json.loads((Path(__file__).parent / "fixtures" / "playlist_items_page.json")
                  .read_text(encoding="utf-8"))
SECRET_KEY = "AIzaSy-test-key-must-never-be-logged"


def entry(video_id, published, season="", playlist="channel"):
    return VideoEntry(video_id=video_id, title="title", duration_seconds=None,
                      season=season, playlist=playlist, published=published, description="")


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def api_error(status, reason):
    return FakeResponse(status, {"error": {"code": status, "errors": [{"reason": reason}]}})


@pytest.mark.parametrize("published,expected", [
    ("2026-09-11T10:52:14Z", "2026/27"),        # the API's spelling
    ("2026-08-01T00:00:00+00:00", "2026/27"),   # the day of the rollover
    ("2026-07-31T23:59:59+00:00", "2025/26"),   # the day before
    ("2000-09-01T12:00:00Z", "2000/01"),        # across the century
    ("1999-12-31T12:00:00Z", "1999/00"),
    ("20260911", "2026/27"),                     # compact spelling
    (None, ""),
    ("nonsense", ""),
])
def test_season_of_publish(published, expected):
    assert youtube_api.season_of_publish(published) == expected


def test_uploads_playlist_id():
    assert youtube_api.uploads_playlist_id("UCqxNoI856R_vgs7aQolQhlg") == "UUqxNoI856R_vgs7aQolQhlg"
    with pytest.raises(ValueError):
        youtube_api.uploads_playlist_id("PLCWRG1vLyuBJUaQ1PPFjaZxPkliR-Rxrx")


def test_parse_reads_the_video_publish_time_and_description_not_the_playlist_add_time():
    entries = youtube_api.parse_playlist_items(PAGE, season="2024/25", playlist="PL1")
    game = next(e for e in entries if e.video_id == "dRsHKQtTRBM")
    assert game.title == 'תקציר המשחק: מכבי Rapyd ת"א - מילאנו 102:88'
    assert game.published == "2025-02-27T22:10:00Z"
    assert game.description == "המשחק נערך ב-27.02.2025"
    assert game.season == "2024/25" and game.playlist == "PL1"
    assert game.duration_seconds is None


def test_parse_skips_private_and_deleted_videos():
    ids = [e.video_id for e in youtube_api.parse_playlist_items(PAGE, "2024/25", "PL1")]
    assert ids == ["tHNmlqoPQEs", "dRsHKQtTRBM"]


def test_an_empty_description_stays_an_empty_string():
    """None means "never asked" and sends the entry to the watch page; "" means asked."""
    entries = youtube_api.parse_playlist_items(PAGE, "2026/27", "PL1")
    assert next(e for e in entries if e.video_id == "tHNmlqoPQEs").description == ""


def test_fetch_playlist_follows_page_tokens(monkeypatch):
    tokens_seen = []
    last_page = {**PAGE, "nextPageToken": None}

    def fake_get(url, params, timeout):
        tokens_seen.append(params.get("pageToken"))
        return FakeResponse(200, PAGE if len(tokens_seen) == 1 else last_page)

    monkeypatch.setattr(youtube_api.requests, "get", fake_get)
    entries = youtube_api.fetch_playlist("PL1", SECRET_KEY, "2024/25", "PL1")
    assert tokens_seen == [None, "EAAaBlBUOkNESQ"]
    assert len(entries) == 4


def test_fetch_playlist_stops_at_max_pages(monkeypatch):
    calls = []
    monkeypatch.setattr(youtube_api.requests, "get",
                        lambda url, params, timeout: calls.append(1) or FakeResponse(200, PAGE))
    youtube_api.fetch_playlist("UU1", SECRET_KEY, "", "channel", max_pages=1)
    assert len(calls) == 1


def fake_fetch_by_playlist(responses):
    """A fetch_playlist stand-in: `responses` maps the playlist label to entries or an error."""
    calls = []

    def fake_fetch(playlist_id, api_key, season, playlist, max_pages):
        calls.append((playlist, max_pages))
        result = responses[playlist]
        if isinstance(result, Exception):
            raise result
        return [VideoEntry(e.video_id, e.title, None, season or e.season, playlist,
                           e.published, e.description) for e in result]

    return fake_fetch, calls


def test_uploads_take_their_season_from_their_own_publish_date(monkeypatch):
    """Not from whichever season the caller asked about: asking for two seasons once
    stamped every channel video with the first, labelling a new video with the PREVIOUS
    season."""
    fake, _ = fake_fetch_by_playlist({"channel": [entry("new", "2026-09-11T10:52:14Z"),
                                                  entry("old", "2026-02-03T10:52:14Z")]})
    monkeypatch.setattr(youtube_api, "fetch_playlist", fake)
    entries = youtube_api.collect_from_api("UC123", {}, SECRET_KEY)
    assert {e.video_id: e.season for e in entries} == {"new": "2026/27", "old": "2025/26"}


def test_a_season_playlist_states_the_season_and_wins(monkeypatch):
    fake, _ = fake_fetch_by_playlist({"channel": [entry("v", "2026-09-11T10:52:14Z")],
                                      "PL1": [entry("v", "2026-09-11T10:52:14Z")]})
    monkeypatch.setattr(youtube_api, "fetch_playlist", fake)
    entries = youtube_api.collect_from_api("UC123", {"2025/26": ["PL1"]}, SECRET_KEY)
    assert [(e.season, e.playlist) for e in entries] == [("2025/26", "PL1")]


def test_only_the_newest_page_of_uploads_but_every_page_of_a_season_playlist(monkeypatch):
    """The uploads playlist is the whole channel, thousands of videos; a season playlist
    is bounded by its season and not necessarily newest-first."""
    fake, calls = fake_fetch_by_playlist({"channel": [], "PL1": [], "PL2": []})
    monkeypatch.setattr(youtube_api, "fetch_playlist", fake)
    youtube_api.collect_from_api("UC123", {"2025/26": ["PL1"], "2026/27": ["PL2"]}, SECRET_KEY)
    assert calls == [("channel", 1), ("PL1", youtube_api._MAX_PAGES_PER_PLAYLIST),
                     ("PL2", youtube_api._MAX_PAGES_PER_PLAYLIST)]


def test_one_missing_playlist_does_not_lose_the_others(monkeypatch):
    fake, _ = fake_fetch_by_playlist({"channel": requests.HTTPError("HTTP 404 playlistNotFound"),
                                      "PL1": [entry("v", "2026-09-11T10:52:14Z")]})
    monkeypatch.setattr(youtube_api, "fetch_playlist", fake)
    entries = youtube_api.collect_from_api("UC123", {"2025/26": ["PL1"]}, SECRET_KEY)
    assert [e.video_id for e in entries] == ["v"]


def test_every_playlist_failing_is_an_error_not_an_empty_run(monkeypatch):
    """A run that could read nothing has not established that there is nothing new, and
    must not pass quietly as a no-op — that is how the RSS feeds failed for weeks."""
    fake, _ = fake_fetch_by_playlist({"channel": requests.HTTPError("HTTP 500 backendError"),
                                      "PL1": requests.ConnectionError("reset")})
    monkeypatch.setattr(youtube_api, "fetch_playlist", fake)
    with pytest.raises(youtube_api.NoVideosAvailable):
        youtube_api.collect_from_api("UC123", {"2025/26": ["PL1"]}, SECRET_KEY)


@pytest.mark.parametrize("status,reason", [
    (400, "keyInvalid"), (403, "accessNotConfigured"), (403, "quotaExceeded")])
def test_a_refused_key_stops_the_run_at_the_first_call(monkeypatch, status, reason):
    """A bad key, the API off on the project, or the quota spent fail every call the same
    way. Logging four warnings and then "no videos" would hide which one it was."""
    calls = []
    monkeypatch.setattr(youtube_api.requests, "get",
                        lambda url, params, timeout: calls.append(1) or api_error(status, reason))
    with pytest.raises(youtube_api.ApiKeyRejected, match=reason):
        youtube_api.collect_from_api("UC123", {"2025/26": ["PL1"]}, SECRET_KEY)
    assert len(calls) == 1


def test_a_missing_key_fails_before_any_call(monkeypatch):
    monkeypatch.setattr(youtube_api.requests, "get", lambda *a, **k: pytest.fail("called"))
    with pytest.raises(youtube_api.ApiKeyRejected, match="YOUTUBE_API_KEY"):
        youtube_api.collect_from_api("UC123", {}, "")


def test_the_key_never_reaches_the_log(monkeypatch, caplog):
    """requests puts the full URL, key included, in its error messages — and the CI log
    and its Telegram error tail are where those messages end up."""
    def fails(url, params, timeout):
        if params["playlistId"].startswith("UU"):
            raise requests.ConnectionError(f"Max retries exceeded with url: {url}?key={params['key']}")
        return api_error(404, "playlistNotFound")

    monkeypatch.setattr(youtube_api.requests, "get", fails)
    caplog.set_level(logging.WARNING)
    with pytest.raises(youtube_api.NoVideosAvailable) as raised:
        youtube_api.collect_from_api("UC123", {"2025/26": ["PL1"]}, SECRET_KEY)
    assert "playlistNotFound" in caplog.text
    assert SECRET_KEY not in caplog.text
    assert SECRET_KEY not in str(raised.value)
