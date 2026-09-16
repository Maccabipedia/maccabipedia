"""Fetch one video's real upload date, for the verification sample.

This is a per-video request, unlike everything else here, so it runs only over the
sample and paces itself between calls.
"""
import logging
import subprocess
import time

from maccabipediabot.basketball.videos.inventory import yt_dlp_command

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 120
_PAUSE_BETWEEN_CALLS_SECONDS = 2.0


def fetch_upload_date(video_id: str, pause: float = _PAUSE_BETWEEN_CALLS_SECONDS) -> str | None:
    """The YYYYMMDD upload date of one video, or None when it cannot be read."""
    completed = subprocess.run(
        [*yt_dlp_command(), "--skip-download", "--no-warnings",
         "--print", "%(upload_date)s", f"https://www.youtube.com/watch?v={video_id}"],
        capture_output=True, text=True, timeout=_TIMEOUT_SECONDS, check=False,
    )
    time.sleep(pause)
    if completed.returncode != 0:
        logger.warning("Could not read the upload date of %s: %s",
                       video_id, completed.stderr.strip()[-200:])
        return None
    value = completed.stdout.strip().splitlines()[0] if completed.stdout.strip() else ""
    return value if value.isdigit() and len(value) == 8 else None
