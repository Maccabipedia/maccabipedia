"""Fetch what the watch page knows about many videos at once: upload date and description.

yt-dlp gives the same answers but costs a full extraction per video, which is minutes
for a handful and hours for a channel. The watch page carries both `"uploadDate":"..."`
and `"shortDescription":"..."` in its embedded metadata, so one plain GET per video is
enough, and they can run concurrently.

Both are evidence about a match that does NOT come from the title, which is what makes
them worth fetching for every video rather than a sample. The upload date places a
modern video against the game it follows; the description is the only place the club
writes the date of an ARCHIVE game, which the titles never carry.
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)

_WATCH_URL = "https://www.youtube.com/watch?v={video_id}"
_UPLOAD_DATE_RE = re.compile(r'"uploadDate"\s*:\s*"(\d{4})-(\d{2})-(\d{2})')
_DESCRIPTION_RE = re.compile(r'"shortDescription":"(.*?)","isCrawlable"', re.DOTALL)

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


@dataclass(frozen=True)
class WatchPageFacts:
    """What one watch page said. Either field is None when the page did not carry it."""
    upload_date: str | None = None
    description: str | None = None


def parse_upload_date(page_html: str) -> str | None:
    """The YYYYMMDD upload date embedded in a watch page, or None."""
    found = _UPLOAD_DATE_RE.search(page_html)
    return f"{found.group(1)}{found.group(2)}{found.group(3)}" if found else None


def parse_description(page_html: str) -> str | None:
    """The description text embedded in a watch page, or None.

    The page holds it as a JSON string literal, escapes and all, so json does the
    unescaping rather than a second-guessing regex.
    """
    found = _DESCRIPTION_RE.search(page_html)
    if found is None:
        return None
    try:
        return json.loads(f'"{found.group(1)}"')
    except json.JSONDecodeError:
        logger.warning("Description did not decode as a JSON string literal")
        return None


def parse_watch_page(page_html: str) -> WatchPageFacts:
    return WatchPageFacts(upload_date=parse_upload_date(page_html),
                          description=parse_description(page_html))


async def _fetch_one(session: aiohttp.ClientSession, video_id: str,
                     semaphore: asyncio.Semaphore) -> tuple[str, WatchPageFacts]:
    for attempt in range(_RETRIES + 1):
        async with semaphore:
            try:
                async with session.get(_WATCH_URL.format(video_id=video_id)) as response:
                    if response.status != 200:
                        return video_id, WatchPageFacts()
                    return video_id, parse_watch_page(await response.text())
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                if attempt == _RETRIES:
                    logger.warning("Watch page unavailable for %s: %s", video_id, error)
                    return video_id, WatchPageFacts()
                await asyncio.sleep(1 + attempt)
    return video_id, WatchPageFacts()


async def fetch_watch_pages_async(video_ids: list[str]) -> dict[str, WatchPageFacts]:
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
    async with aiohttp.ClientSession(timeout=_TIMEOUT, headers=_HEADERS) as session:
        results = await asyncio.gather(
            *(_fetch_one(session, video_id, semaphore) for video_id in video_ids))
    return dict(results)


def fetch_watch_pages(video_ids: list[str]) -> dict[str, WatchPageFacts]:
    """Upload date and description for as many of these videos as YouTube will tell us."""
    logger.info("Fetching watch pages for %d videos", len(video_ids))
    facts = asyncio.run(fetch_watch_pages_async(video_ids))
    with_date = sum(1 for fact in facts.values() if fact.upload_date)
    with_description = sum(1 for fact in facts.values() if fact.description)
    logger.info("Got %d upload dates and %d descriptions of %d videos",
                with_date, with_description, len(video_ids))
    return facts
