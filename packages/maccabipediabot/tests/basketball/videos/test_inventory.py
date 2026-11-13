"""Tests for building the video inventory from yt-dlp output."""
from pathlib import Path

import pytest

from maccabipediabot.basketball.videos.inventory import (
    VideoEntry,
    load_inventory,
    parse_yt_dlp_line,
    save_inventory,
    split_playlist_count,
    yt_dlp_command,
)


def test_parse_yt_dlp_line():
    entry = parse_yt_dlp_line(
        'תקציר המשחק: מכבי Rapyd ת"א - מילאנו 102:88|dRsHKQtTRBM|177', "2024/25", "2024/25 Season",
    )
    assert entry == VideoEntry(
        video_id="dRsHKQtTRBM",
        title='תקציר המשחק: מכבי Rapyd ת"א - מילאנו 102:88',
        duration_seconds=177,
        season="2024/25",
        playlist="2024/25 Season",
        published=None,
    )


def test_parse_yt_dlp_line_with_a_pipe_inside_the_title():
    """Titles contain '|' themselves, so the split has to come from the right."""
    entry = parse_yt_dlp_line(
        "Highlights: Gilboa/Galil vs Maccabi 60:77 | תקציר|f_H-g84B-yQ|185", "2021/22", "Season 2021/22",
    )
    assert entry.video_id == "f_H-g84B-yQ"
    assert entry.title == "Highlights: Gilboa/Galil vs Maccabi 60:77 | תקציר"
    assert entry.duration_seconds == 185


@pytest.mark.parametrize("duration", ["NA", "", "None"])
def test_parse_yt_dlp_line_without_a_duration(duration):
    entry = parse_yt_dlp_line(f"Some title|abc12345678|{duration}", "2024/25", "2024/25 Season")
    assert entry is not None
    assert entry.duration_seconds is None


def test_parse_yt_dlp_line_rejects_a_malformed_line():
    assert parse_yt_dlp_line("no separators here", "2024/25", "p") is None


def test_inventory_round_trip(tmp_path: Path):
    entries = [
        VideoEntry("abc", 'תקציר המשחק: מכבי - מילאנו 102:88', 177, "2024/25", "p", "2026-09-11T10:52:14+00:00"),
        VideoEntry("def", "Full Game: Barcelona - Maccabi 89:71", None, "2013/14", "q", None),
    ]
    path = tmp_path / "inventory.json"
    save_inventory(entries, path)
    assert load_inventory(path) == entries


@pytest.mark.parametrize("line,count,rest", [
    ("508|Some title|abc123|177", 508, "Some title|abc123|177"),
    ("NA|Some title|abc123|177", None, "Some title|abc123|177"),
    ("no separators", None, "no separators"),
])
def test_split_playlist_count(line, count, rest):
    assert split_playlist_count(line) == (count, rest)


def test_yt_dlp_command_is_overridable(monkeypatch):
    """An out-of-date yt-dlp truncates playlists at 100 items, so which build runs
    has to be selectable without touching whatever is on PATH."""
    monkeypatch.delenv("YT_DLP_COMMAND", raising=False)
    assert yt_dlp_command() == ["yt-dlp"]
    monkeypatch.setenv("YT_DLP_COMMAND", "uvx yt-dlp@latest")
    assert yt_dlp_command() == ["uvx", "yt-dlp@latest"]
