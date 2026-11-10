"""List the club channel's videos through the YouTube Data API v3.

This is how the scheduled job sees new videos. It replaced YouTube's public RSS feeds
(`feeds/videos.xml`), which from late 2026 answered 404/500 for every channel, YouTube's
own included, for hours almost every night, while the rest of the site answered 200.

Each call is `playlistItems.list` (1 quota unit per page of 50, out of 10,000 a day):
- the channel's uploads playlist (`UU…`), first page only: the 50 newest uploads;
- each wanted season's playlists, every page: a playlist states its season outright.

A playlist item carries the video's title, description and publish time, which are all
the matcher reads, so no watch page is fetched for these entries.
"""
import logging
from dataclasses import replace

import requests

from maccabipediabot.basketball.videos.dates import parse_upload_date
from maccabipediabot.basketball.videos.inventory import VideoEntry

logger = logging.getLogger(__name__)

PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
_PAGE_SIZE = 50
_REQUEST_TIMEOUT_SECONDS = 30
# A season playlist has held up to ~500 videos; this bounds a runaway paging loop.
_MAX_PAGES_PER_PLAYLIST = 20
# Titles YouTube gives a video that is in the playlist but cannot be shown.
_UNAVAILABLE_TITLES = {"Private video", "Deleted video"}

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


def uploads_playlist_id(channel_id: str) -> str:
    """Every channel's uploads playlist is its id with `UC` swapped for `UU`."""
    if not channel_id.startswith("UC"):
        raise ValueError(f"not a channel id: {channel_id!r}")
    return "UU" + channel_id[2:]


class NoVideosAvailable(RuntimeError):
    """Every playlist we asked for failed, so this run saw nothing rather than nothing new."""


class ApiKeyRejected(RuntimeError):
    """The API refused the key itself. Every call would fail the same way, so stop at once."""


def parse_playlist_items(payload: dict, season: str, playlist: str) -> list[VideoEntry]:
    """Turn one page of `playlistItems.list` into entries. Durations are not listed."""
    entries = []
    for item in payload.get("items", []):
        snippet = item.get("snippet", {})
        video_id = snippet.get("resourceId", {}).get("videoId")
        title = (snippet.get("title") or "").strip()
        if not video_id or not title or title in _UNAVAILABLE_TITLES:
            continue
        entries.append(VideoEntry(
            video_id=video_id,
            title=title,
            duration_seconds=None,
            season=season,
            playlist=playlist,
            # videoPublishedAt is when the video went up; snippet.publishedAt is only
            # when it was added to this playlist, which can be months later.
            published=item.get("contentDetails", {}).get("videoPublishedAt"),
            description=snippet.get("description") or "",
        ))
    return entries


def _error_reason(response: requests.Response) -> str:
    """The API's own reason code ("keyInvalid", "playlistNotFound"…), never the URL."""
    try:
        errors = response.json().get("error", {}).get("errors", [])
    except ValueError:
        return "no JSON body"
    return errors[0].get("reason", "unknown") if errors else "unknown"


def fetch_playlist(playlist_id: str, api_key: str, season: str, playlist: str,
                   max_pages: int = _MAX_PAGES_PER_PLAYLIST) -> list[VideoEntry]:
    """Every item of one playlist, up to `max_pages` pages of 50.

    Raises ApiKeyRejected on 400/401/403: a bad key, the API not enabled on the project,
    or the day's quota spent — none of which another playlist would answer differently.
    Raises requests.HTTPError for anything else, a 404 for a missing playlist included.
    """
    entries: list[VideoEntry] = []
    page_token = None
    for _ in range(max_pages):
        params = {"part": "snippet,contentDetails", "playlistId": playlist_id,
                  "maxResults": _PAGE_SIZE, "key": api_key}
        if page_token:
            params["pageToken"] = page_token
        response = requests.get(PLAYLIST_ITEMS_URL, params=params,
                                timeout=_REQUEST_TIMEOUT_SECONDS)
        if response.status_code in (400, 401, 403):
            raise ApiKeyRejected(f"YouTube Data API refused the request: HTTP "
                                 f"{response.status_code} {_error_reason(response)}")
        if response.status_code != 200:
            # Built by hand: requests' own message carries the URL, and the URL the key.
            raise requests.HTTPError(f"HTTP {response.status_code} {_error_reason(response)}")
        payload = response.json()
        entries.extend(parse_playlist_items(payload, season, playlist))
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    return entries


def _fetch_playlist_or_none(playlist_id: str, api_key: str, season: str,
                            playlist: str, max_pages: int) -> list[VideoEntry] | None:
    """One playlist's entries, or None if that playlist could not be read."""
    try:
        return fetch_playlist(playlist_id, api_key, season, playlist, max_pages)
    except requests.HTTPError as error:
        logger.warning("Playlist unavailable (%s): %s", playlist, error)
    except (requests.RequestException, ValueError) as error:
        # Only the type: a connection error's message repeats the URL, key included.
        logger.warning("Playlist unavailable (%s): %s", playlist, type(error).__name__)
    return None


def collect_from_api(channel_id: str, playlist_ids_by_season: dict[str, list[str]],
                     api_key: str) -> list[VideoEntry]:
    """Entries from the channel's newest uploads plus each season's playlists, deduplicated.

    An upload carries no season, so it takes one from its own publish date. A
    playlist-sourced entry wins over it, because a playlist states its season outright.
    """
    if not api_key:
        raise ApiKeyRejected("no YouTube Data API key: set YOUTUBE_API_KEY")
    by_video_id: dict[str, VideoEntry] = {}
    attempted = 0
    succeeded = 0

    attempted += 1
    uploads = _fetch_playlist_or_none(uploads_playlist_id(channel_id), api_key, "",
                                      "channel", max_pages=1)
    if uploads is not None:
        succeeded += 1
        for entry in uploads:
            by_video_id[entry.video_id] = replace(entry,
                                                  season=season_of_publish(entry.published))

    for season, playlist_ids in playlist_ids_by_season.items():
        for playlist_id in playlist_ids:
            attempted += 1
            playlist_entries = _fetch_playlist_or_none(playlist_id, api_key, season,
                                                       playlist_id, _MAX_PAGES_PER_PLAYLIST)
            if playlist_entries is None:
                continue
            succeeded += 1
            for entry in playlist_entries:
                by_video_id[entry.video_id] = entry

    if succeeded == 0:
        raise NoVideosAvailable(
            f"none of the {attempted} YouTube playlists could be read — the run saw no "
            f"videos at all, which is not the same as there being none")
    logger.info("YouTube API: %d distinct videos from %d of %d playlists",
                len(by_video_id), succeeded, attempted)
    return list(by_video_id.values())
