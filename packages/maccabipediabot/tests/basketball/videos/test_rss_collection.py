"""Tests for collecting videos from RSS, which is how the scheduled run sees them.

The channel feed says nothing about which season a video belongs to. Getting that wrong
is invisible in the logs: the video is either dropped as unmatched or, worse, matched
against a game from the wrong season that happens to share a score and opponent.
"""
import pytest

from maccabipediabot.basketball.videos import rss
from maccabipediabot.basketball.videos.inventory import VideoEntry


def feed_entry(video_id, published, title="title"):
    return VideoEntry(video_id=video_id, title=title, duration_seconds=None,
                      season="", playlist="channel", published=published)


@pytest.mark.parametrize("published,expected", [
    ("2026-09-11T10:52:14+00:00", "2026/27"),   # after the August rollover
    ("2026-08-01T00:00:00+00:00", "2026/27"),   # the day of it
    ("2026-07-31T23:59:59+00:00", "2025/26"),   # the day before
    ("2026-02-03T12:00:00+00:00", "2025/26"),   # mid-season
    ("2000-09-01T12:00:00+00:00", "2000/01"),   # across the century
    ("1999-12-31T12:00:00+00:00", "1999/00"),
    ("20260911", "2026/27"),                     # compact spelling
    (None, ""),
    ("nonsense", ""),
])
def test_season_of_publish(published, expected):
    assert rss.season_of_publish(published) == expected


def test_channel_feed_videos_take_their_season_from_their_own_publish_date(monkeypatch):
    """Not from whichever season the caller happened to ask about. Asking for two
    seasons used to stamp every channel-feed video with the first one iterated, so a
    brand-new video was labelled with the PREVIOUS season."""
    monkeypatch.setattr(rss, "fetch_feed",
                        lambda url, season, playlist: [
                            feed_entry("new", "2026-09-11T10:52:14+00:00"),
                            feed_entry("old", "2026-02-03T10:52:14+00:00"),
                        ])
    entries = rss.collect_from_feeds("UC123", {})
    seasons = {entry.video_id: entry.season for entry in entries}
    assert seasons == {"new": "2026/27", "old": "2025/26"}


def test_a_playlist_feed_states_the_season_and_wins(monkeypatch):
    """A playlist says its season outright, so it beats the date-derived guess."""
    def fake_fetch(url, season, playlist):
        if playlist == "channel":
            return [feed_entry("v", "2026-09-11T10:52:14+00:00")]
        return [VideoEntry("v", "title", None, season, playlist, "2026-09-11T10:52:14+00:00")]

    monkeypatch.setattr(rss, "fetch_feed", fake_fetch)
    entries = rss.collect_from_feeds("UC123", {"2025/26": ["PL1"]})
    assert [entry.season for entry in entries] == ["2025/26"]


def test_the_channel_feed_is_read_once_however_many_seasons_are_wanted(monkeypatch):
    calls = []

    def fake_fetch(url, season, playlist):
        calls.append(playlist)
        return []

    monkeypatch.setattr(rss, "fetch_feed", fake_fetch)
    rss.collect_from_feeds("UC123", {"2025/26": ["PL1"], "2026/27": ["PL2"]})
    assert calls.count("channel") == 1
