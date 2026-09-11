import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from urllib.parse import quote

import aiohttp
import mwparserfromhell as mw
import pywikibot as pw

from maccabipediabot.common.maccabipedia_http import build_maccabipedia_session, parse_cargo_rows

logger = logging.getLogger(__name__)

_session = build_maccabipedia_session()

CARGO_BASE = (
    "https://www.maccabipedia.co.il/index.php"
    "?title=Special:CargoExport&format=json"
    "&limit=5000&offset=0"
)
WIKI_BASE_URL = "https://www.maccabipedia.co.il"
OEMBED_ENDPOINTS = {
    "youtube.com": "https://www.youtube.com/oembed?url={url}&format=json",
    "youtu.be": "https://www.youtube.com/oembed?url={url}&format=json",
    "vimeo.com": "https://vimeo.com/api/oembed.json?url={url}",
    "dailymotion.com": "https://www.dailymotion.com/services/oembed?url={url}&format=json",
}
MAX_CONCURRENT = 20
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)

_FOOTBALL_FIELDS = {
    "FullGame": "משחק מלא",
    "Highlights": "תקציר ראשי",
    "Highlights2": "תקציר משני",
}
_BALL_SPORTS_FIELDS = {
    "FullGameVideo": "משחק מלא",
    "FullGameVideo2": "משחק מלא 2",
    "HighlightsVideo": "תקציר ראשי",
    "HighlightsVideo2": "תקציר משני",
    "FansVideo": "וידאו אוהדים",
}

VIDEO_TABLES: list[tuple[str, dict[str, str]]] = [
    ("Games_Videos", _FOOTBALL_FIELDS),
    ("Volleyball_Games", _BALL_SPORTS_FIELDS),
    ("Basketball_Games", _BALL_SPORTS_FIELDS),
]

FOOTBALL_TEMPLATE = "קטלוג משחקים"
TEMPLATE_FIELD_MAP = {
    "משחק מלא": "משחק מלא",
    "תקציר ראשי": "תקציר וידאו",
    "תקציר משני": "תקציר וידאו2",
}


@dataclass
class BrokenVideo:
    page_name: str
    url: str
    video_type: str


def _page_url(page_name: str) -> str:
    return f"{WIKI_BASE_URL}/{quote(page_name.replace(' ', '_'), safe='/:')}"


def format_report(broken: list[BrokenVideo], report_date: date) -> str:
    by_page: dict[str, list[BrokenVideo]] = {}
    for v in broken:
        by_page.setdefault(v.page_name, []).append(v)

    lines = [f"סרטונים שבורים — {report_date} — נמצאו {len(broken)}"]
    for page_name, videos in sorted(by_page.items()):
        lines.append("")
        lines.append(page_name)
        for v in videos:
            lines.append(f"  ❌ {v.video_type}: {v.url}")
    return "\n".join(lines)


def format_removal_report(removed: list[BrokenVideo], report_date: date) -> str:
    by_page: dict[str, list[BrokenVideo]] = {}
    for v in removed:
        by_page.setdefault(v.page_name, []).append(v)

    lines = [f"הוסרו {len(removed)} קישורי וידאו שבורים — {report_date}"]
    for page_name, videos in sorted(by_page.items()):
        page_url = _page_url(page_name)
        video_links = ", ".join(f'<a href="{v.url}">{v.video_type}</a>' for v in videos)
        lines.append(f'\u200f<a href="{page_url}">{page_name}</a> ({video_links})\u200b')
    return "\n".join(lines)


def _fetch_from_table(table: str, fields: dict[str, str]) -> list[tuple[str, str, str]]:
    """Returns (page_name, url, label) for every non-null video URL in the given table."""
    fields_str = "_pageName," + ",".join(fields.keys())
    response = _session.get(f"{CARGO_BASE}&tables={table}&fields={fields_str}")
    response.raise_for_status()
    result = []
    for row in parse_cargo_rows(response):
        page_name = row["_pageName"]
        for field, label in fields.items():
            video_url = row.get(field)
            if video_url:
                result.append((page_name, _normalize_url(video_url), label))
    return result


def _normalize_url(url: str) -> str:
    """Fix common wiki URL encoding issues (e.g. &amp; → &, duplicate ? → &)."""
    url = url.replace("&amp;", "&")
    # Fix malformed URLs like ?v=ID?t=123 → ?v=ID&t=123
    first_q = url.find("?")
    if first_q != -1 and "?" in url[first_q + 1:]:
        url = url[:first_q + 1] + url[first_q + 1:].replace("?", "&")
    return url


def fetch_game_videos() -> list[tuple[str, str, str]]:
    """Returns (page_name, url, label) for all non-null video URLs across all sports."""
    all_videos: list[tuple[str, str, str]] = []
    for table, fields in VIDEO_TABLES:
        all_videos.extend(_fetch_from_table(table, fields))
    return all_videos


def _oembed_endpoint(url: str) -> str | None:
    for domain, endpoint in OEMBED_ENDPOINTS.items():
        if domain in url:
            return endpoint.format(url=url)
    return None


async def is_video_broken(session: aiohttp.ClientSession, url: str) -> bool:
    oembed = _oembed_endpoint(url)
    if not oembed:
        logger.debug("No oEmbed endpoint for %s — skipping", url)
        return False
    async with session.get(oembed) as resp:
        if resp.status in (400, 401, 404):
            return True
        if resp.status != 200:
            logger.warning("Unexpected oEmbed status %s for %s — skipping", resp.status, url)
            return False
        return False


async def _find_broken_videos() -> list[BrokenVideo]:
    entries = fetch_game_videos()
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    broken: list[BrokenVideo] = []

    async def check(session: aiohttp.ClientSession, page_name: str, url: str, label: str) -> None:
        async with sem:
            if await is_video_broken(session, url):
                broken.append(BrokenVideo(page_name=page_name, url=url, video_type=label))

    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
        tasks = [check(session, page_name, url, label) for page_name, url, label in entries]
        await asyncio.gather(*tasks)

    return broken


def _remove_broken_link(site: pw.Site, video: BrokenVideo) -> bool:
    """Remove the broken URL from the wiki page. Returns True if the page was saved."""
    if not video.page_name.startswith("משחק:"):
        logger.warning("Skipping non-football page: %s", video.page_name)
        return False

    field = TEMPLATE_FIELD_MAP.get(video.video_type)
    if not field:
        logger.warning("Unknown video type '%s' in: %s", video.video_type, video.page_name)
        return False

    page = pw.Page(site, video.page_name)
    if not page.exists():
        logger.warning("Page not found: %s", video.page_name)
        return False

    parsed = mw.parse(page.text)
    templates = parsed.filter_templates(matches=lambda t: t.name.strip() == FOOTBALL_TEMPLATE)
    if not templates:
        logger.warning("Template not found in: %s", video.page_name)
        return False

    tmpl = templates[0]
    if not tmpl.has(field) or not str(tmpl.get(field).value).strip():
        return False

    tmpl.get(field).value = "\n"
    page.text = str(parsed)
    try:
        page.save(summary="MaccabiBot - Remove broken video link", bot=True)
    except pw.exceptions.PageSaveRelatedError:
        logger.exception("Failed to save page: %s", video.page_name)
        return False
    logger.info("Cleared '%s' in: %s", field, video.page_name)
    return True


def remove_broken_links(broken: list[BrokenVideo]) -> list[BrokenVideo]:
    """Remove broken video links from wiki pages. Returns the videos that were successfully removed."""
    if not broken:
        return []

    from maccabipediabot.common.wiki_login import get_site
    pw.config.verbose_output = False
    site = get_site()

    removed = []
    for video in broken:
        if _remove_broken_link(site, video):
            removed.append(video)
    return removed


def main() -> None:
    from maccabipediabot.common.logging_setup import setup_logging
    setup_logging(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    broken = asyncio.run(_find_broken_videos())
    if not broken:
        return
    removed = remove_broken_links(broken)
    if removed:
        print(format_removal_report(removed, date.today()))


if __name__ == "__main__":
    main()
