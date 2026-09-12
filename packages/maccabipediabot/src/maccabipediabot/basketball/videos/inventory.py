"""Collect the channel's videos, with the season each one belongs to.

Two sources, one shape:

* yt-dlp, for the one-off backfill run from a workstation. It can list the channel's
  playlists, which is the only way to learn which season a video belongs to, and it
  reports durations.
* RSS feeds (see rss.py), for the scheduled job. No key and no blocking, but only the
  15 newest items per feed and no durations.

The result is cached as JSON so matching and reporting can be re-run without touching
YouTube again.
"""
import json
import logging
import os
import shlex
import subprocess
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from maccabipediabot.basketball.videos.season_token import season_from_playlist_title
from maccabipediabot.basketball.videos.upload_dates import fetch_upload_dates

logger = logging.getLogger(__name__)

MACCABI_CHANNEL_ID = "UCqxNoI856R_vgs7aQolQhlg"
MACCABI_PLAYLISTS_URL = f"https://www.youtube.com/channel/{MACCABI_CHANNEL_ID}/playlists"
EUROLEAGUE_SEARCH_URL = "https://www.youtube.com/@EuroLeague/search?query=Maccabi+highlights"

_YT_DLP_TIMEOUT_SECONDS = 1800

# Which yt-dlp to run. An out-of-date build silently stops paginating a playlist after
# its first 100 items — a 2026.03 build returned 100 of a 508-video season playlist —
# so this is overridable without touching whatever yt-dlp happens to be on PATH:
#   YT_DLP_COMMAND="uvx yt-dlp@latest"
_DEFAULT_YT_DLP_COMMAND = "yt-dlp"


def yt_dlp_command() -> list[str]:
    return shlex.split(os.environ.get("YT_DLP_COMMAND", _DEFAULT_YT_DLP_COMMAND))


def split_playlist_count(line: str) -> tuple[int | None, str]:
    """Split a '<playlist_count>|<rest>' line. yt-dlp prints 'NA' when it has no count."""
    count_text, separator, rest = line.partition("|")
    if not separator:
        return None, line
    return (int(count_text) if count_text.strip().isdigit() else None), rest


@dataclass(frozen=True)
class VideoEntry:
    video_id: str
    title: str
    duration_seconds: int | None
    season: str
    playlist: str
    published: str | None = None

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


def save_inventory(entries: list[VideoEntry], path: Path) -> None:
    path.write_text(
        json.dumps([asdict(entry) for entry in entries], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )


def load_inventory(path: Path) -> list[VideoEntry]:
    return [VideoEntry(**raw) for raw in json.loads(path.read_text(encoding="utf-8"))]


def parse_yt_dlp_line(line: str, season: str, playlist: str) -> VideoEntry | None:
    """Parse one '%(title)s|%(id)s|%(duration)s' line. Titles contain '|', so split right."""
    parts = line.rsplit("|", 2)
    if len(parts) != 3:
        return None
    title, video_id, duration = (part.strip() for part in parts)
    if not video_id:
        return None
    return VideoEntry(
        video_id=video_id,
        title=title,
        duration_seconds=int(duration) if duration.isdigit() else None,
        season=season,
        playlist=playlist,
    )


def _run_yt_dlp(url: str, print_format: str) -> list[str]:
    completed = subprocess.run(
        [*yt_dlp_command(), "--flat-playlist", "--ignore-errors", "--no-warnings",
         "--print", print_format, url],
        capture_output=True, text=True, timeout=_YT_DLP_TIMEOUT_SECONDS, check=False,
    )
    if completed.returncode != 0 and not completed.stdout:
        raise RuntimeError(f"yt-dlp failed for {url}: {completed.stderr[-500:]}")
    return [line for line in completed.stdout.splitlines() if line.strip()]


def _list_playlist(playlist_id: str, season: str, playlist_title: str) -> list[VideoEntry]:
    """Every video in one playlist, refusing a silently truncated listing."""
    entries: list[VideoEntry] = []
    expected_count: int | None = None
    for line in _run_yt_dlp(f"https://www.youtube.com/playlist?list={playlist_id}",
                            "%(playlist_count)s|%(title)s|%(id)s|%(duration)s"):
        count, rest = split_playlist_count(line)
        expected_count = expected_count or count
        entry = parse_yt_dlp_line(rest, season, playlist_title)
        if entry is not None:
            entries.append(entry)

    if expected_count is not None and len(entries) < expected_count:
        # An out-of-date yt-dlp stops after the first page and says nothing. Backfilling
        # from a truncated listing would look like a successful run with missing videos.
        raise RuntimeError(
            f"yt-dlp listed only {len(entries)} of {expected_count} videos in playlist "
            f"{playlist_title!r}. The build is too old to paginate; re-run with "
            f'YT_DLP_COMMAND="uvx yt-dlp@latest".'
        )
    return entries


def collect_with_yt_dlp(playlists_url: str = MACCABI_PLAYLISTS_URL,
                        seasons: list[str] | None = None) -> list[VideoEntry]:
    """Walk the channel's season playlists and list each one's videos."""
    entries: list[VideoEntry] = []
    for line in _run_yt_dlp(playlists_url, "%(title)s|%(id)s"):
        playlist_title, _, playlist_id = line.rpartition("|")
        season = season_from_playlist_title(playlist_title)
        if season is None or (seasons and season not in seasons):
            continue
        found = _list_playlist(playlist_id, season, playlist_title)
        logger.info("Playlist %r (season %s): %d videos", playlist_title, season, len(found))
        entries.extend(found)
    return entries


def with_upload_dates(entries: list[VideoEntry]) -> list[VideoEntry]:
    """The same entries with `published` filled in wherever YouTube will say.

    Kept beside the collectors rather than left to the caller, because the upload date is
    what lifts a match from "the score and the name agree" to "and it went up the day of
    the game" — without it every match built from a yt-dlp inventory is capped at 9.
    """
    missing = sorted({entry.video_id for entry in entries if not entry.published})
    if not missing:
        return entries
    dates = fetch_upload_dates(missing)
    return [replace(entry, published=dates.get(entry.video_id, entry.published))
            for entry in entries]


def collect_euroleague_with_yt_dlp(search_url: str = EUROLEAGUE_SEARCH_URL) -> list[VideoEntry]:
    """List the EuroLeague channel's videos that mention Maccabi.

    The season comes from each title, not from a playlist, so the season field is left
    empty here and filled in by the EuroLeague title parser.
    """
    entries = []
    for line in _run_yt_dlp(search_url, "%(title)s|%(id)s"):
        title, _, video_id = line.rpartition("|")
        if not video_id.strip():
            continue
        entries.append(VideoEntry(
            video_id=video_id.strip(),
            title=title.strip(),
            duration_seconds=None,
            season="",
            playlist="euroleague-search",
        ))
    return entries
