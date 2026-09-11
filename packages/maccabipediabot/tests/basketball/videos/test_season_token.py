"""Tests for mapping official-channel playlist titles to wiki season labels.

Every title here is a real playlist name from the Maccabi Tel Aviv Basketball channel.
"""
import pytest

from maccabipediabot.basketball.videos.season_token import (
    PlaylistKind,
    playlist_kind,
    season_from_playlist_title,
)


@pytest.mark.parametrize("title,season", [
    ("Season 2014/2015", "2014/15"),
    ("Season 2018/19", "2018/19"),
    ("2025/26 Season", "2025/26"),
    ("season 1979/80", "1979/80"),
    ("Season 1999/00", "1999/00"),
    ("2023/24 season", "2023/24"),
    ("Games Highlights 2013-2014", "2013/14"),
    ("Full Games 2014/2015", "2014/15"),
    ("Game Highlights | 2025/26", "2025/26"),
    ("Highlights 2019/2020", "2019/20"),
    ("Game Highlights: 2024/25", "2024/25"),
    ("Players Highlights 2011/2012", None),
    ("Pre-Season 2010/2011", None),
    ("TSM Condensed Games 25-26", None),
    ("Iffe Lundberg", None),
    ("Season 2014/2016", None),  # not consecutive years: not a season label
])
def test_season_from_playlist_title(title, season):
    assert season_from_playlist_title(title) == season


@pytest.mark.parametrize("title,kind", [
    ("Season 2014/2015", PlaylistKind.SEASON),
    ("2025/26 Season", PlaylistKind.SEASON),
    ("Games Highlights 2013-2014", PlaylistKind.HIGHLIGHTS),
    ("Game Highlights | 2025/26", PlaylistKind.HIGHLIGHTS),
    ("Full Games 2014/2015", PlaylistKind.FULL_GAMES),
    ("Players Highlights 2011/2012", None),
    ("Pre-Season 2010/2011", None),
    ("Iffe Lundberg", None),
])
def test_playlist_kind(title, kind):
    assert playlist_kind(title) == kind
