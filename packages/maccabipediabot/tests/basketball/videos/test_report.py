"""Tests for the HTML review page Roee reads before anything is written to the wiki."""
from maccabipediabot.basketball.videos.inventory import VideoEntry
from maccabipediabot.basketball.videos.matcher import (
    Bucket,
    EUROLEAGUE_CHANNEL,
    VideoMatch,
)
from maccabipediabot.basketball.videos.report import render_report, wiki_url
from maccabipediabot.basketball.videos.title_parser import ParsedTitle, VideoKind

PAGE = "כדורסל:22-11-2024 מכבי תל אביב נגד מילאנו - יורוליג"


def exact_match():
    entry = VideoEntry("dRsHKQtTRBM", 'תקציר המשחק: מכבי Rapyd ת"א - מילאנו 102:88',
                       177, "2024/25", "2024/25 Season", None)
    parsed = ParsedTitle(VideoKind.HIGHLIGHTS, "מילאנו", 102, 88, "he")
    return VideoMatch(entry, parsed, Bucket.EXACT, "score and opponent agree",
                      page_name=PAGE, slot="תקציר וידאו")


def ambiguous_match():
    entry = VideoEntry("xyz", "Highlights: Maccabi Playtika Tel Aviv - Unknown FC 80:77",
                       180, "2024/25", "2024/25 Season", None)
    parsed = ParsedTitle(VideoKind.HIGHLIGHTS, "Unknown FC", 80, 77, "en")
    return VideoMatch(entry, parsed, Bucket.AMBIGUOUS, "opponent not recognised",
                      candidates=[PAGE, "כדורסל:08-11-2024 הפועל חולון נגד מכבי תל אביב - ליגת העל"])


def test_report_is_rtl_and_utf8():
    html = render_report([exact_match()], skipped_non_game=5200)
    assert 'dir="rtl"' in html
    assert 'charset="utf-8"' in html


def test_report_links_each_video_and_its_page():
    html = render_report([exact_match()], skipped_non_game=0)
    assert "https://www.youtube.com/watch?v=dRsHKQtTRBM" in html
    assert wiki_url(PAGE) in html


def test_report_shows_bucket_counts():
    html = render_report([exact_match(), ambiguous_match()], skipped_non_game=12)
    assert "exact" in html
    assert "ambiguous" in html
    assert "12" in html  # the non-game count is reported, not silently dropped


def test_report_lists_every_candidate_of_an_ambiguous_video():
    html = render_report([ambiguous_match()], skipped_non_game=0)
    for candidate in ambiguous_match().candidates:
        assert wiki_url(candidate) in html


def test_report_escapes_page_titles_and_reasons():
    match = ambiguous_match()
    match.reason = 'opponent disagrees: <script>alert("x")</script>'
    html = render_report([match], skipped_non_game=0)
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_report_marks_the_source_channel():
    match = exact_match()
    match.source = EUROLEAGUE_CHANNEL
    html = render_report([match], skipped_non_game=0)
    assert "euroleague" in html.lower()


def test_report_groups_by_season():
    html = render_report([exact_match()], skipped_non_game=0)
    assert "2024/25" in html


def test_wiki_url_uses_the_bare_path_form():
    assert wiki_url("כדורסל:עונת 2024/25").startswith("https://www.maccabipedia.co.il/")
    assert " " not in wiki_url("כדורסל:עונת 2024/25")
