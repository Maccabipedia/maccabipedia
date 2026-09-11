"""Attach official-channel and EuroLeague videos to basketball game pages.

Two uses, one entry point:

* the one-off backfill, reading an inventory built by yt-dlp over every season;
* the scheduled job, reading YouTube's RSS feeds for the current and previous season.

Nothing is written without --write, and --write only ever fills a template parameter
that is empty. Run --report first and read the result.
"""
import argparse
import csv
import logging
from datetime import date
from pathlib import Path

from maccabipediabot.basketball.videos import rss
from maccabipediabot.basketball.videos.cargo import fetch_basketball_game_rows
from maccabipediabot.basketball.videos.inventory import (
    MACCABI_CHANNEL_ID,
    VideoEntry,
    load_inventory,
)
from maccabipediabot.basketball.videos.matcher import (
    Bucket,
    count_non_game_videos,
    match_euroleague_videos,
    match_videos,
)
from maccabipediabot.basketball.videos.report import render_report, render_sample_section
from maccabipediabot.basketball.videos.sampling import choose_verification_sample, verify_sample
from maccabipediabot.basketball.videos.youtube_metadata import fetch_upload_date

logger = logging.getLogger(__name__)

# The season turns over at the start of August, between the finals and the next
# pre-season. Matching only ever looks at the current and previous season in the
# scheduled job, so a game whose video appears late is still caught.
_SEASON_ROLLOVER_MONTH = 8

# Playlist ids for the RSS path, which cannot discover them itself. Only the current
# and previous season are needed; the channel feed still works without them, at lower
# signal density. Add the new season here once a year — the run warns when it is missing.
SEASON_PLAYLIST_IDS: dict[str, list[str]] = {
    "2025/26": ["PLCWRG1vLyuBJUaQ1PPFjaZxPkliR-Rxrx", "PLCWRG1vLyuBLo2wPrw3qKdc-HKwEqPUAF"],
    "2024/25": ["PLCWRG1vLyuBKq5_S6xV8mYE9mxAXBFi6R", "PLCWRG1vLyuBIznrtzPIXDCMawGrr5WPJZ"],
}


def season_label(start_year: int) -> str:
    return f"{start_year}/{(start_year + 1) % 100:02d}"


def current_and_previous_seasons(today: date) -> list[str]:
    start_year = today.year if today.month >= _SEASON_ROLLOVER_MONTH else today.year - 1
    return [season_label(start_year - 1), season_label(start_year)]


def resolve_seasons(argument: str, today: date | None = None) -> list[str] | None:
    """None means every season."""
    if argument in ("all", ""):
        return None
    if argument == "current,previous":
        return current_and_previous_seasons(today or date.today())
    return [season.strip() for season in argument.split(",") if season.strip()]


def load_overrides(path: Path | None) -> dict[str, str]:
    """A hand-written 'video_id,page_name' CSV promoting videos out of the review list."""
    if path is None:
        return {}
    overrides: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) >= 2 and row[0].strip() and not row[0].startswith("#"):
                overrides[row[0].strip()] = row[1].strip()
    logger.info("Loaded %d overrides from %s", len(overrides), path)
    return overrides


def collect_entries_from_rss(seasons: list[str]) -> list[VideoEntry]:
    entries: list[VideoEntry] = []
    for season in seasons:
        playlist_ids = SEASON_PLAYLIST_IDS.get(season)
        if playlist_ids is None:
            logger.warning(
                "No playlist ids for season %s: falling back to the channel feed alone. "
                "Add them to SEASON_PLAYLIST_IDS for denser coverage.", season)
            playlist_ids = []
        entries.extend(rss.collect_from_feeds(MACCABI_CHANNEL_ID, season, playlist_ids))
    return entries


def build_matches(entries: list[VideoEntry], euroleague_entries: list[VideoEntry],
                  seasons: list[str] | None, overrides: dict[str, str]):
    rows = fetch_basketball_game_rows(seasons)
    club_matches = match_videos(entries, rows, overrides)
    euroleague_matches = match_euroleague_videos(
        euroleague_entries, rows, overrides, already_assigned=club_matches)
    return club_matches + euroleague_matches, rows


def log_bucket_counts(matches) -> None:
    for bucket in Bucket:
        count = sum(1 for match in matches if match.bucket == bucket)
        logger.info("  %-16s %d", bucket.value, count)
    writable = sum(1 for match in matches if match.bucket == Bucket.EXACT and match.slot)
    logger.info("  %-16s %d", "writable", writable)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("file", "rss"), default="file",
                        help="file: a yt-dlp inventory JSON. rss: YouTube's public feeds.")
    parser.add_argument("--inventory", type=Path,
                        help="Club-channel inventory JSON (required for --source file).")
    parser.add_argument("--euroleague-inventory", type=Path,
                        help="EuroLeague inventory JSON (optional).")
    parser.add_argument("--seasons", default="all",
                        help="'all', 'current,previous', or a comma-separated list.")
    parser.add_argument("--overrides", type=Path, help="CSV of video_id,page_name.")
    parser.add_argument("--report", type=Path, help="Write the HTML review page here.")
    parser.add_argument("--sample", type=int, default=0,
                        help="Verify N matches against their real upload date and pin the "
                             "result to the top of the report.")
    args = parser.parse_args()

    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
    seasons = resolve_seasons(args.seasons)

    if args.source == "rss":
        if seasons is None:
            raise SystemExit("--source rss needs --seasons (feeds carry only recent videos)")
        entries = collect_entries_from_rss(seasons)
    else:
        if args.inventory is None:
            raise SystemExit("--source file needs --inventory")
        entries = load_inventory(args.inventory)

    euroleague_entries = (load_inventory(args.euroleague_inventory)
                          if args.euroleague_inventory else [])
    logger.info("Loaded %d club videos and %d EuroLeague videos",
                len(entries), len(euroleague_entries))

    matches, rows = build_matches(entries, euroleague_entries, seasons,
                                  load_overrides(args.overrides))
    log_bucket_counts(matches)

    sample_section = ""
    if args.sample:
        rows_by_page = {row.page_name: row for row in rows}
        sample = choose_verification_sample(matches, rows_by_page, size=args.sample)
        logger.info("Verifying %d sampled matches against their upload dates", len(sample))
        checks = verify_sample(sample, rows_by_page, fetch_upload_date)
        sample_section = render_sample_section(checks)
        for verdict in {check.verdict for check in checks}:
            logger.info("  sample %-16s %d", verdict.value,
                        sum(1 for check in checks if check.verdict == verdict))

    if args.report:
        args.report.write_text(
            render_report(matches, skipped_non_game=count_non_game_videos(entries),
                          sample_section=sample_section),
            encoding="utf-8",
        )
        logger.info("Report written to %s", args.report)


if __name__ == "__main__":
    main()
