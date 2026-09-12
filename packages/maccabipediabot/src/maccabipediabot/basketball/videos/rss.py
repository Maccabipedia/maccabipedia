"""Read YouTube's public RSS feeds for a channel or a playlist.

This is how the scheduled job sees new videos. The feed endpoint needs no API key, no
quota and no proxy, and it answers from any IP — including GitHub's datacenter ranges,
where yt-dlp is blocked. Each feed returns the 15 newest items with a publish time.

A playlist feed is much denser than the channel feed for our purpose: the channel mixes
game videos with player clips and interviews, while the season's highlights playlist is
almost entirely game videos.
"""
import logging
from dataclasses import replace
from xml.etree import ElementTree

import requests

from maccabipediabot.basketball.videos.dates import parse_upload_date
from maccabipediabot.basketball.videos.inventory import VideoEntry

# A basketball season turns over between the finals and the next pre-season.
SEASON_ROLLOVER_MONTH = 8


def season_of_publish(published: str | None) -> str:
    """The season a video published at this time belongs to, or "" if it cannot be told."""
    if not published:
        return ""
    when = parse_upload_date(published)
    if when is None:
        return ""
    start_year = when.year if when.month >= SEASON_ROLLOVER_MONTH else when.year - 1
    return f"{start_year}/{(start_year + 1) % 100:02d}"

logger = logging.getLogger(__name__)

FEED_BASE = "https://www.youtube.com/feeds/videos.xml"
_NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}
_REQUEST_TIMEOUT_SECONDS = 30


def channel_feed_url(channel_id: str) -> str:
    return f"{FEED_BASE}?channel_id={channel_id}"


def playlist_feed_url(playlist_id: str) -> str:
    return f"{FEED_BASE}?playlist_id={playlist_id}"


def parse_feed(xml_text: str, season: str, playlist: str) -> list[VideoEntry]:
    """Turn one feed document into entries. Durations are absent from feeds."""
    root = ElementTree.fromstring(xml_text)
    entries = []
    for entry in root.findall("atom:entry", _NAMESPACES):
        video_id = entry.findtext("yt:videoId", namespaces=_NAMESPACES)
        title = entry.findtext("media:group/media:title", namespaces=_NAMESPACES)
        if title is None:
            title = entry.findtext("atom:title", namespaces=_NAMESPACES)
        if not video_id or not title:
            continue
        entries.append(VideoEntry(
            video_id=video_id.strip(),
            title=title.strip(),
            duration_seconds=None,
            season=season,
            playlist=playlist,
            published=entry.findtext("atom:published", namespaces=_NAMESPACES),
        ))
    return entries


class NoFeedsAvailable(RuntimeError):
    """Every feed we asked for failed, so this run saw nothing rather than nothing new."""


def fetch_feed(url: str, season: str, playlist: str) -> list[VideoEntry]:
    response = requests.get(url, timeout=_REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return parse_feed(response.text, season=season, playlist=playlist)


def _fetch_feed_or_none(url: str, season: str, playlist: str) -> list[VideoEntry] | None:
    """One feed's entries, or None if that feed could not be read.

    YouTube's feed endpoint is not guaranteed: on 2026-09-12 it began answering 404 for
    every channel, its own included, while watch pages kept working. One feed failing
    must not lose the others, but ALL of them failing is not "no new videos" — it is a
    run that saw nothing, and saying so is the difference between a quiet no-op and a
    silent stop.
    """
    try:
        return fetch_feed(url, season, playlist)
    except (requests.RequestException, ElementTree.ParseError) as error:
        # ParseError matters as much as a network failure here: a feed can answer 200
        # with an interstitial or a truncated body, and letting that escape would abort
        # the whole collection — losing every other feed, which is the one thing this
        # wrapper exists to prevent.
        logger.warning("Feed unavailable (%s): %s", playlist, error)
        return None


def collect_from_feeds(channel_id: str, playlist_ids_by_season: dict[str, list[str]]) -> list[VideoEntry]:
    """Entries from the channel feed plus each season's playlist feeds, deduplicated.

    The channel feed says nothing about which season a video belongs to, so its entries
    take their season from their own publish date. Stamping them with a season chosen by
    the caller looked simpler and was wrong: the scheduled run asks for two seasons, and
    every channel-feed video ended up labelled with whichever was iterated first, so a
    new video was either dropped as unmatched or matched against the previous season.

    A playlist-sourced entry still wins over the channel-sourced one, because a playlist
    states the season outright rather than inferring it.
    """
    by_video_id: dict[str, VideoEntry] = {}
    attempted = 0
    succeeded = 0

    attempted += 1
    channel_entries = _fetch_feed_or_none(channel_feed_url(channel_id), "", "channel")
    if channel_entries is not None:
        succeeded += 1
        for entry in channel_entries:
            by_video_id[entry.video_id] = replace(entry,
                                                  season=season_of_publish(entry.published))

    for season, playlist_ids in playlist_ids_by_season.items():
        for playlist_id in playlist_ids:
            attempted += 1
            playlist_entries = _fetch_feed_or_none(playlist_feed_url(playlist_id),
                                                   season, playlist_id)
            if playlist_entries is None:
                continue
            succeeded += 1
            for entry in playlist_entries:
                by_video_id[entry.video_id] = entry

    if succeeded == 0:
        raise NoFeedsAvailable(
            f"none of the {attempted} YouTube feeds could be read — the run saw no videos "
            f"at all, which is not the same as there being none")
    logger.info("RSS: %d distinct videos from %d of %d feeds",
                len(by_video_id), succeeded, attempted)
    return list(by_video_id.values())
