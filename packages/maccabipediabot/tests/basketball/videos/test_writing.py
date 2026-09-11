"""Tests for writing matched videos to game pages, and for the season purge afterwards."""
from pathlib import Path

import pytest

from maccabipediabot.basketball.videos.inventory import VideoEntry
from maccabipediabot.basketball.videos.matcher import Bucket, VideoMatch
from maccabipediabot.basketball.videos.title_parser import ParsedTitle, VideoKind
from maccabipediabot.basketball.videos.writing import (
    WriteOutcome,
    load_written_video_ids,
    season_page_titles,
    write_matches,
)

WRITER_PATH = "maccabipediabot.basketball.videos.writing.set_video_field"


def make_match(video_id, *, bucket=Bucket.EXACT, slot="תקציר וידאו", season="2024/25",
               page=None, source="maccabi-channel"):
    entry = VideoEntry(video_id, f"title {video_id}", 180, season, "playlist", None)
    parsed = ParsedTitle(VideoKind.HIGHLIGHTS, "מילאנו", 102, 88, "he")
    return VideoMatch(entry, parsed, bucket, "score and opponent agree",
                      page_name=page or f"כדורסל:page-{video_id}", slot=slot, source=source)


@pytest.fixture
def writes(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        WRITER_PATH,
        lambda site, page_title, field, url, summary=None, sport="basketball":
            recorded.append((page_title, field, url, summary)),
    )
    return recorded


def test_writes_only_exact_matches_that_have_a_slot(writes, tmp_path):
    matches = [make_match("a"),
               make_match("b", bucket=Bucket.AMBIGUOUS),
               make_match("c", slot=None),
               make_match("d", bucket=Bucket.OVERFLOW)]
    result = write_matches(None, matches, progress_path=tmp_path / "p.log")
    assert [page for page, _, _, _ in writes] == ["כדורסל:page-a"]
    assert result.written == 1
    assert result.seasons == {"2024/25"}


def test_dry_run_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(WRITER_PATH,
                        lambda *args, **kwargs: pytest.fail("must not write during a dry run"))
    result = write_matches(None, [make_match("a")], progress_path=tmp_path / "p.log", dry_run=True)
    assert result.written == 0
    assert result.would_write == 1
    assert result.seasons == {"2024/25"}


def test_dry_run_leaves_no_progress_behind(monkeypatch, tmp_path):
    monkeypatch.setattr(WRITER_PATH, lambda *args, **kwargs: None)
    progress = tmp_path / "p.log"
    write_matches(None, [make_match("a")], progress_path=progress, dry_run=True)
    assert load_written_video_ids(progress) == set()


def test_a_rerun_skips_what_is_already_written(writes, tmp_path):
    progress = tmp_path / "p.log"
    write_matches(None, [make_match("a")], progress_path=progress)
    write_matches(None, [make_match("a")], progress_path=progress)
    assert len(writes) == 1


def test_progress_is_recorded_per_video(writes, tmp_path):
    progress = tmp_path / "p.log"
    write_matches(None, [make_match("a"), make_match("b")], progress_path=progress)
    assert load_written_video_ids(progress) == {"a", "b"}


def test_limit_caps_the_number_of_writes(writes, tmp_path):
    write_matches(None, [make_match("a"), make_match("b"), make_match("c")],
                  progress_path=tmp_path / "p.log", limit=2)
    assert len(writes) == 2


def test_only_the_named_pages_are_written(writes, tmp_path):
    matches = [make_match("a", page="כדורסל:wanted"), make_match("b", page="כדורסל:other")]
    write_matches(None, matches, progress_path=tmp_path / "p.log", pages={"כדורסל:wanted"})
    assert [page for page, _, _, _ in writes] == ["כדורסל:wanted"]


def test_the_edit_summary_names_the_source_channel(writes, tmp_path):
    write_matches(None, [make_match("a"), make_match("b", source="euroleague-channel")],
                  progress_path=tmp_path / "p.log")
    summaries = [summary for _, _, _, summary in writes]
    assert "official channel" in summaries[0]
    assert "EuroLeague" in summaries[1]
    assert all(summary.startswith("MaccabiBot - ") for summary in summaries)


def test_a_slot_taken_since_the_cargo_snapshot_is_skipped_not_fatal(monkeypatch, tmp_path):
    """Cargo lags the wiki, so a slot can fill between reading and writing."""
    def refuse(site, page_title, field, url, summary=None, sport="basketball"):
        raise ValueError(f"Field '{field}' already has a value on {page_title}: other")

    monkeypatch.setattr(WRITER_PATH, refuse)
    result = write_matches(None, [make_match("a"), make_match("b")],
                           progress_path=tmp_path / "p.log")
    assert result.written == 0
    assert result.skipped == 2
    assert result.failed == 0


def test_an_unexpected_error_stops_the_run(monkeypatch, tmp_path):
    """A run of a thousand pages must not grind on through a broken login."""
    def explode(site, page_title, field, url, summary=None, sport="basketball"):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(WRITER_PATH, explode)
    with pytest.raises(RuntimeError):
        write_matches(None, [make_match("a")], progress_path=tmp_path / "p.log")


def test_season_page_titles_are_sorted_and_prefixed():
    assert season_page_titles({"2024/25", "1999/00"}) == [
        "כדורסל:עונת 1999/00", "כדורסל:עונת 2024/25",
    ]


def test_season_page_titles_ignores_an_empty_season():
    assert season_page_titles({"", "2024/25"}) == ["כדורסל:עונת 2024/25"]


def test_write_outcome_counts_add_up(writes, tmp_path):
    result = write_matches(None, [make_match("a"), make_match("b", bucket=Bucket.AMBIGUOUS)],
                           progress_path=tmp_path / "p.log")
    assert isinstance(result, WriteOutcome)
    assert result.written == 1
    assert result.considered == 1


def test_progress_file_survives_a_missing_directory(writes, tmp_path):
    progress = tmp_path / "nested" / "deeper" / "p.log"
    write_matches(None, [make_match("a")], progress_path=progress)
    assert Path(progress).exists()
