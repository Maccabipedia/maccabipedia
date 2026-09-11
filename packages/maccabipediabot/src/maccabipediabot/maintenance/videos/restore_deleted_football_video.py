"""End-to-end restore of a deleted football video:

  1. Upload the local backup to MaccabiPedia's YouTube channel.
  2. Add the new video to its season playlist (creating the playlist if missing).
  3. Update the matching field on the wiki game page to point at the new URL.

Game metadata (season, competition, stage, opponent, scores) is read directly from
the wiki page template — the wiki is the single source of truth. The operator only
supplies the backup file, the wiki page title, and the video type.

Pre-flight: the target wiki field must be empty. If it's already filled we abort
before touching YouTube (don't clobber a working link).

If upload succeeds but the wiki step fails, the video URL is logged loudly with the
exact recovery command. There is no rollback: YouTube uploads cost 1,600 quota units
and the daily cap is 10,000, so re-uploading on every retry would burn through fast.

Scope: football only. Basketball/volleyball use different wiki templates and Cargo
tables; a ball-sports variant can reuse the youtube/ helpers if needed.
"""
import argparse
import logging
import shlex
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

import mwparserfromhell as mw
import pywikibot as pw

from maccabipediabot.common.logging_setup import setup_logging
from maccabipediabot.common.wiki_login import get_site
from maccabipediabot.maintenance.videos.sport_templates import FOOTBALL
from maccabipediabot.maintenance.videos.update_wiki_video_field import set_video_field

TEMPLATE_NAME = FOOTBALL.template_name
from maccabipediabot.maintenance.videos.youtube.title import (
    FULL_MATCH,
    HIGHLIGHTS,
    VideoType,
    format_video_title,
    season_playlist_title,
)
from maccabipediabot.maintenance.videos.youtube.upload import upload_and_add_to_playlist

logger = logging.getLogger(__name__)

VIDEO_TYPE_TO_WIKI_FIELD: dict[VideoType, str] = {
    FULL_MATCH: "משחק מלא",
    HIGHLIGHTS: "תקציר וידאו",
}

CLI_VIDEO_TYPE_TO_INTERNAL: dict[str, VideoType] = {
    "full-match": FULL_MATCH,
    "highlights": HIGHLIGHTS,
}


@dataclass(frozen=True)
class GameMetadata:
    season: str  # normalized to "YYYY-YY" (dash form, matching channel title convention)
    competition: str
    stage: str
    opponent: str
    maccabi_score: int
    opponent_score: int


def wiki_page_url(wiki_page_title: str) -> str:
    """URL-encode the title so YouTube's auto-linkifier treats the description as clickable."""
    return "https://www.maccabipedia.co.il/" + urllib.parse.quote(wiki_page_title.replace(" ", "_"), safe=":")


def _game_template(wikitext: str, page_title_hint: str) -> mw.nodes.Template:
    parsed = mw.parse(wikitext)
    templates = parsed.filter_templates(matches=lambda tmpl: tmpl.name.strip() == TEMPLATE_NAME)
    if not templates:
        raise LookupError(f"Template '{TEMPLATE_NAME}' not found on {page_title_hint}")
    return templates[0]


def parse_game_metadata(wikitext: str, page_title_hint: str = "") -> GameMetadata:
    """Pure function: extract `GameMetadata` from the page's wikitext."""
    tmpl = _game_template(wikitext, page_title_hint)

    def required(field: str) -> str:
        if not tmpl.has(field):
            raise LookupError(f"Required field '{field}' missing on {page_title_hint}")
        value = str(tmpl.get(field).value).strip()
        if not value:
            raise LookupError(f"Required field '{field}' is empty on {page_title_hint}")
        return value

    return GameMetadata(
        season=required("עונה").replace("/", "-"),
        competition=required("מפעל"),
        stage=required("שלב במפעל"),
        opponent=required("שם יריבה"),
        maccabi_score=int(required("תוצאת משחק מכבי")),
        opponent_score=int(required("תוצאת משחק יריבה")),
    )


def fetch_game_metadata(site: pw.Site, page_title: str) -> GameMetadata:
    page = pw.Page(site, page_title)
    if not page.exists():
        raise LookupError(f"Wiki page not found: {page_title}")
    return parse_game_metadata(page.text, page_title)


def _check_wiki_field_empty(site: pw.Site, wiki_page_title: str, field: str) -> None:
    """Abort if the target wiki field already has a value — we don't want to clobber it.

    Race note: a concurrent edit between this check and `set_video_field`'s save can still
    happen; set_video_field re-checks at save time and raises if the field became non-empty.
    """
    page = pw.Page(site, wiki_page_title)
    if not page.exists():
        raise LookupError(f"Wiki page not found: {wiki_page_title}")
    tmpl = _game_template(page.text, wiki_page_title)
    existing = str(tmpl.get(field).value).strip() if tmpl.has(field) else ""
    if existing:
        raise ValueError(
            f"Wiki field '{field}' on {wiki_page_title} is already set to '{existing}'. "
            f"Refusing to clobber. If the existing value is broken, clear it manually first."
        )


def restore(
    *,
    video_path: Path,
    wiki_page_title: str,
    video_type: VideoType,
    dry_run: bool = False,
) -> str:
    """Run the full restore pipeline.

    When `dry_run=True`, fetches metadata, runs the pre-flight check, and prints the
    YouTube title / playlist / wiki field it *would* produce — without uploading or
    editing the wiki. Returns an empty string.
    """
    if not video_path.is_file():
        raise FileNotFoundError(f"Backup video not found: {video_path}")

    wiki_field = VIDEO_TYPE_TO_WIKI_FIELD[video_type]
    site = get_site()
    _check_wiki_field_empty(site, wiki_page_title, wiki_field)

    metadata = fetch_game_metadata(site, wiki_page_title)
    logger.info("Fetched metadata from wiki: %s", metadata)

    youtube_title = format_video_title(
        season=metadata.season,
        competition=metadata.competition,
        round_name=metadata.stage,
        maccabi_score=metadata.maccabi_score,
        opponent=metadata.opponent,
        opponent_score=metadata.opponent_score,
        video_type=video_type,
    )
    description = wiki_page_url(wiki_page_title)
    playlist_title = season_playlist_title(metadata.season)

    if dry_run:
        logger.info("DRY RUN — would upload:")
        logger.info("  file:        %s", video_path)
        logger.info("  title:       %s", youtube_title)
        logger.info("  playlist:    %s", playlist_title)
        logger.info("  description: %s", description)
        logger.info("  wiki field:  %s on %s", wiki_field, wiki_page_title)
        return ""

    logger.info("Uploading %s as %r to %r", video_path, youtube_title, playlist_title)
    video_id = upload_and_add_to_playlist(video_path, youtube_title, playlist_title, description)
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    logger.info("Uploaded %s — now updating wiki field %r on %s", video_url, wiki_field, wiki_page_title)

    try:
        set_video_field(site, wiki_page_title, wiki_field, video_url)
    except Exception:
        # Build a copy-pasteable recovery command — %r wraps Hebrew strings in single
        # quotes that the shell re-interprets, breaking the paste. shlex.quote emits
        # shell-safe quoting that survives a real copy-paste.
        recovery = " ".join([
            "uv run python -m maccabipediabot.maintenance.videos.update_wiki_video_field",
            f"--page {shlex.quote(wiki_page_title)}",
            f"--field {shlex.quote(wiki_field)}",
            f"--url {shlex.quote(video_url)}",
        ])
        logger.exception(
            "Upload succeeded (%s) but wiki update failed. Run this to finish the job:\n%s",
            video_url, recovery,
        )
        raise
    return video_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", required=True, help="Path to backup video file")
    parser.add_argument("--wiki-page", required=True, help="Full wiki page title (e.g. 'משחק:...')")
    parser.add_argument(
        "--video-type", required=True, choices=sorted(CLI_VIDEO_TYPE_TO_INTERNAL.keys()),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch metadata and print the computed YouTube title / playlist / wiki "
             "field, but don't upload or edit the wiki. No quota cost.",
    )
    args = parser.parse_args()

    setup_logging(level=logging.INFO)
    pw.config.verbose_output = False

    video_id = restore(
        video_path=Path(args.file),
        wiki_page_title=args.wiki_page,
        video_type=CLI_VIDEO_TYPE_TO_INTERNAL[args.video_type],
        dry_run=args.dry_run,
    )
    if video_id:
        logger.info("Done. https://www.youtube.com/watch?v=%s", video_id)


if __name__ == "__main__":
    main()
