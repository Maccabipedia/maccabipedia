"""Fetch the upload date of many videos at once, straight from the watch page.

yt-dlp gives the same answer but costs a full extraction per video, which is minutes
for a handful and hours for a channel. The watch page carries `"uploadDate":"..."` in
its embedded metadata, so one plain GET per video is enough, and they can run
concurrently.

The date is the one piece of evidence about a match that does NOT come from the title,
which is what makes it worth fetching for every video rather than a sample.
"""
import asyncio
import logging
import re

import aiohttp

logger = logging.getLogger(__name__)

_WATCH_URL = "https://www.youtube.com/watch?v={video_id}"
_UPLOAD_DATE_RE = re.compile(r'"uploadDate"\s*:\s*"(\d{4})-(\d{2})-(\d{2})')
_MAX_CONCURRENT = 12
_TIMEOUT = aiohttp.ClientTimeout(total=30)
_RETRIES = 2
# A browser-ish header: the bare watch page is served to anyone, but an empty
# user agent occasionally gets a consent interstitial with no metadata in it.
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}


def parse_upload_date(page_html: str) -> str | None:
    """The YYYYMMDD upload date embedded in a watch page, or None."""
    found = _UPLOAD_DATE_RE.search(page_html)
    return f"{found.group(1)}{found.group(2)}{found.group(3)}" if found else None


async def _fetch_one(session: aiohttp.ClientSession, video_id: str,
                     semaphore: asyncio.Semaphore) -> tuple[str, str | None]:
    for attempt in range(_RETRIES + 1):
        async with semaphore:
            try:
                async with session.get(_WATCH_URL.format(video_id=video_id)) as response:
                    if response.status != 200:
                        return video_id, None
                    return video_id, parse_upload_date(await response.text())
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                if attempt == _RETRIES:
                    logger.warning("Upload date unavailable for %s: %s", video_id, error)
                    return video_id, None
                await asyncio.sleep(1 + attempt)
    return video_id, None


async def fetch_upload_dates_async(video_ids: list[str]) -> dict[str, str]:
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
    async with aiohttp.ClientSession(timeout=_TIMEOUT, headers=_HEADERS) as session:
        results = await asyncio.gather(
            *(_fetch_one(session, video_id, semaphore) for video_id in video_ids))
    return {video_id: date for video_id, date in results if date}


def fetch_upload_dates(video_ids: list[str]) -> dict[str, str]:
    """Upload dates for as many of these videos as YouTube will tell us about."""
    logger.info("Fetching upload dates for %d videos", len(video_ids))
    dates = asyncio.run(fetch_upload_dates_async(video_ids))
    logger.info("Got %d of %d upload dates", len(dates), len(video_ids))
    return dates
