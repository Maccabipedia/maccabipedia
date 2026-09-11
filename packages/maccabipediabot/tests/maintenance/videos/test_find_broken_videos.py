import asyncio
import requests
from datetime import date
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest

from maccabipediabot.maintenance.videos.find_broken_videos import (
    BrokenVideo,
    _oembed_endpoint,
    _fetch_from_table,
    _normalize_url,
    format_report,
    format_removal_report,
    is_video_broken,
)


def test_format_report_header_contains_count():
    broken = [
        BrokenVideo(
            page_name='משחק:01-01-2001 מכבי תל אביב נגד בית"ר ירושלים - ליגת העל',
            url="https://www.youtube.com/watch?v=abc123",
            video_type="משחק מלא",
        )
    ]
    report = format_report(broken, date(2026, 4, 8))
    assert "נמצאו 1" in report
    assert "2026-04-08" in report


def test_format_report_includes_page_name_url_and_type():
    broken = [
        BrokenVideo(
            page_name='משחק:01-01-2001 מכבי תל אביב נגד בית"ר ירושלים - ליגת העל',
            url="https://www.youtube.com/watch?v=abc123",
            video_type="משחק מלא",
        )
    ]
    report = format_report(broken, date(2026, 4, 8))
    assert 'משחק:01-01-2001 מכבי תל אביב נגד בית"ר ירושלים - ליגת העל' in report
    assert "https://www.youtube.com/watch?v=abc123" in report
    assert "משחק מלא" in report


def test_format_report_groups_multiple_broken_under_same_page():
    broken = [
        BrokenVideo("משחק:01-01-2001 א נגד ב - ליגה", "https://youtu.be/1", "תקציר ראשי"),
        BrokenVideo("משחק:01-01-2001 א נגד ב - ליגה", "https://youtu.be/2", "תקציר משני"),
        BrokenVideo("משחק:02-02-2002 ג נגד ד - ליגה", "https://youtu.be/3", "משחק מלא"),
    ]
    report = format_report(broken, date(2026, 4, 8))
    assert "נמצאו 3" in report
    assert report.count("משחק:01-01-2001 א נגד ב - ליגה") == 1
    assert "https://youtu.be/1" in report
    assert "https://youtu.be/2" in report
    assert "https://youtu.be/3" in report


def test_normalize_url_fixes_html_encoded_ampersand():
    assert _normalize_url("https://youtu.be/abc&amp;t=6s") == "https://youtu.be/abc&t=6s"


def test_normalize_url_fixes_duplicate_question_mark():
    assert _normalize_url("https://www.youtube.com/watch?v=KOGbFAPcYHY?t=2156") == \
        "https://www.youtube.com/watch?v=KOGbFAPcYHY&t=2156"


def test_normalize_url_leaves_valid_url_unchanged():
    assert _normalize_url("https://www.youtube.com/watch?v=abc&t=60") == \
        "https://www.youtube.com/watch?v=abc&t=60"


def test_fetch_from_table_returns_video_entries():
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.json.return_value = [
        {
            "_pageName": "משחק:01-01-2001 מכבי תל אביב נגד בית\"ר ירושלים - ליגת העל",
            "FullGame": "https://www.youtube.com/watch?v=abc",
            "Highlights": None,
            "Highlights2": None,
        }
    ]
    fields = {"FullGame": "משחק מלא", "Highlights": "תקציר ראשי", "Highlights2": "תקציר משני"}
    with patch(
        "maccabipediabot.maintenance.videos.find_broken_videos._session.get",
        return_value=mock_response,
    ):
        entries = _fetch_from_table("Games_Videos", fields)

    assert len(entries) == 1
    assert entries[0] == (
        "משחק:01-01-2001 מכבי תל אביב נגד בית\"ר ירושלים - ליגת העל",
        "https://www.youtube.com/watch?v=abc",
        "משחק מלא",
    )


def test_fetch_from_table_skips_null_urls():
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.json.return_value = [
        {"_pageName": "משחק:01-01-2001 א נגד ב - ליגה", "FullGame": None, "Highlights": None, "Highlights2": None}
    ]
    fields = {"FullGame": "משחק מלא", "Highlights": "תקציר ראשי", "Highlights2": "תקציר משני"}
    with patch(
        "maccabipediabot.maintenance.videos.find_broken_videos._session.get",
        return_value=mock_response,
    ):
        entries = _fetch_from_table("Games_Videos", fields)

    assert entries == []


def test_fetch_from_table_raises_on_http_error():
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = requests.HTTPError("500")
    with patch(
        "maccabipediabot.maintenance.videos.find_broken_videos._session.get",
        return_value=mock_response,
    ):
        with pytest.raises(requests.HTTPError):
            _fetch_from_table("Games_Videos", {"FullGame": "משחק מלא"})


def test_fetch_from_table_raises_on_non_json_response():
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.headers = {"Content-Type": "text/html", "Server": "openresty"}
    mock_response.text = "<html>error</html>"
    mock_response.json = Mock(side_effect=ValueError("Expecting value: line 1 column 1"))
    with patch(
        "maccabipediabot.maintenance.videos.find_broken_videos._session.get",
        return_value=mock_response,
    ):
        with pytest.raises(ValueError, match="CargoExport returned a non-JSON body"):
            _fetch_from_table("Games_Videos", {"FullGame": "משחק מלא"})


def test_fetch_from_table_raises_on_object_instead_of_rows():
    """``for row in <dict>`` walks the dict's *keys*, so this used to surface as an opaque
    'string indices must be integers' — one of the WAF-hunt crash signatures."""
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.headers = {"Content-Type": "application/json", "Server": "openresty"}
    mock_response.text = '{"error": "query failed"}'
    mock_response.json = Mock(return_value={"error": "query failed"})
    with patch(
        "maccabipediabot.maintenance.videos.find_broken_videos._session.get",
        return_value=mock_response,
    ):
        with pytest.raises(ValueError, match="CargoExport returned a bare dict"):
            _fetch_from_table("Games_Videos", {"FullGame": "משחק מלא"})


def test_format_removal_report_contains_count_and_wiki_url():
    removed = [
        BrokenVideo(
            page_name='משחק:16-09-1999 מכבי תל אביב נגד לאנס - גביע אופא',
            url="https://www.youtube.com/watch?v=JwUrFyR75sY",
            video_type="משחק מלא",
        )
    ]
    report = format_removal_report(removed, date(2026, 4, 9))
    assert "הוסרו 1" in report
    assert "2026-04-09" in report
    assert '<a href="https://www.maccabipedia.co.il/' in report
    assert "16-09-1999" in report
    assert "משחק מלא" in report
    assert "https://www.youtube.com/watch?v=JwUrFyR75sY" in report


def test_format_removal_report_url_encodes_special_chars():
    removed = [
        BrokenVideo(
            page_name='משחק:22-12-2018 בית"ר ירושלים נגד מכבי תל אביב - גביע המדינה',
            url="https://www.youtube.com/watch?v=abc",
            video_type="תקציר משני",
        )
    ]
    report = format_removal_report(removed, date(2026, 4, 9))
    # Extract href URL — between href=" and the closing "
    href_url = report.split('href="')[1].split('"')[0]
    assert '"' not in href_url


def test_oembed_endpoint_returns_none_for_unknown_domain():
    assert _oembed_endpoint("https://www.facebook.com/video/123") is None


def test_oembed_endpoint_returns_youtube_for_youtube_url():
    result = _oembed_endpoint("https://www.youtube.com/watch?v=abc")
    assert result is not None
    assert "youtube.com/oembed" in result


def _make_mock_session(status: int) -> Mock:
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    mock_session = Mock()
    mock_session.get = Mock(return_value=mock_resp)
    return mock_session


def test_is_video_broken_returns_true_on_400():
    result = asyncio.run(is_video_broken(_make_mock_session(400), "https://www.youtube.com/watch?v=broken"))
    assert result is True


def test_is_video_broken_returns_true_on_404():
    result = asyncio.run(is_video_broken(_make_mock_session(404), "https://www.youtube.com/watch?v=broken"))
    assert result is True


def test_is_video_broken_returns_true_on_401():
    result = asyncio.run(is_video_broken(_make_mock_session(401), "https://www.youtube.com/watch?v=private"))
    assert result is True


def test_is_video_broken_returns_false_on_200():
    result = asyncio.run(is_video_broken(_make_mock_session(200), "https://www.youtube.com/watch?v=valid"))
    assert result is False


def test_is_video_broken_returns_false_on_500():
    result = asyncio.run(is_video_broken(_make_mock_session(500), "https://www.youtube.com/watch?v=server_error"))
    assert result is False


def test_is_video_broken_returns_false_for_unknown_domain():
    mock_session = Mock()
    result = asyncio.run(is_video_broken(mock_session, "https://www.facebook.com/video/123"))
    assert result is False
    mock_session.get.assert_not_called()
