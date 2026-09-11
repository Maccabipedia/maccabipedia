"""Write matched videos onto game pages, one at a time, and purge the season pages.

A backfill run edits over a thousand pages, so it keeps a progress file: one line per
video written, which lets a killed run resume without re-editing anything. Only exact
matches holding a free slot are written; everything else is for the report.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pywikibot as pw

from maccabipediabot.basketball.videos.matcher import (
    Bucket,
    EUROLEAGUE_CHANNEL,
    VideoMatch,
)
from maccabipediabot.common.wiki_purge import purge_pages
from maccabipediabot.maintenance.videos.update_wiki_video_field import set_video_field

logger = logging.getLogger(__name__)

BASKETBALL_SEASON_PAGE_PREFIX = "כדורסל:עונת "
_SOURCE_LABELS = {
    EUROLEAGUE_CHANNEL: "EuroLeague channel",
}
_DEFAULT_SOURCE_LABEL = "official channel"


@dataclass
class WriteOutcome:
    considered: int = 0
    written: int = 0
    would_write: int = 0
    skipped: int = 0
    failed: int = 0
    seasons: set[str] = field(default_factory=set)


def edit_summary(match: VideoMatch) -> str:
    label = _SOURCE_LABELS.get(match.source, _DEFAULT_SOURCE_LABEL)
    return f"MaccabiBot - Attach {label} video ({match.url})"


def load_written_video_ids(progress_path: Path) -> set[str]:
    """Video ids already written, from a previous run of the same backfill."""
    if not progress_path.exists():
        return set()
    written = set()
    for line in progress_path.read_text(encoding="utf-8").splitlines():
        video_id = line.split("\t", 1)[0].strip()
        if video_id:
            written.add(video_id)
    return written


def _record(progress_path: Path, match: VideoMatch) -> None:
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    with progress_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{match.entry.video_id}\t{match.slot}\t{match.page_name}\n")
        handle.flush()


def write_matches(site: pw.Site, matches: list[VideoMatch], *, progress_path: Path,
                  dry_run: bool = False, limit: int | None = None,
                  pages: set[str] | None = None,
                  min_confidence: int | None = None) -> WriteOutcome:
    """Write every exact match that holds a slot. Returns what happened.

    `min_confidence` refuses anything scored below it, so a run can be restricted to
    the matches whose evidence is strongest.
    """
    outcome = WriteOutcome()
    already_written = load_written_video_ids(progress_path)

    writable = [match for match in matches
                if match.bucket == Bucket.EXACT and match.slot and match.page_name]
    if min_confidence is not None:
        below = [match for match in writable
                 if (match.confidence or 0) < min_confidence]
        writable = [match for match in writable if match not in below]
        if below:
            logger.info("Holding back %d matches scored below %d", len(below), min_confidence)
    if pages is not None:
        writable = [match for match in writable if match.page_name in pages]
    writable.sort(key=lambda match: (match.page_name, match.slot))

    for match in writable:
        if limit is not None and (outcome.written + outcome.would_write) >= limit:
            break
        outcome.considered += 1
        outcome.seasons.add(match.entry.season)

        if match.entry.video_id in already_written:
            outcome.skipped += 1
            continue

        if dry_run:
            outcome.would_write += 1
            logger.info("[DRY-RUN] %s <- %s = %s", match.page_name, match.slot, match.url)
            continue

        try:
            set_video_field(site, match.page_name, match.slot, match.url,
                            summary=edit_summary(match), sport="basketball")
        except ValueError as error:
            # The slot filled between the Cargo read and this write, or the parameter
            # was rejected. Neither is worth abandoning the run for.
            outcome.skipped += 1
            logger.warning("Skipped %s: %s", match.page_name, error)
            continue
        except LookupError as error:
            outcome.failed += 1
            logger.warning("Failed %s: %s", match.page_name, error)
            continue

        outcome.written += 1
        _record(progress_path, match)
        logger.info("Wrote %s <- %s", match.page_name, match.slot)

    logger.info("Write finished: considered=%d written=%d would_write=%d skipped=%d failed=%d",
                outcome.considered, outcome.written, outcome.would_write,
                outcome.skipped, outcome.failed)
    return outcome


def season_page_titles(seasons: set[str]) -> list[str]:
    return sorted(f"{BASKETBALL_SEASON_PAGE_PREFIX}{season}" for season in seasons if season)


def purge_season_pages(site: pw.Site, seasons: set[str], dry_run: bool = False) -> int:
    """Refresh the season pages so their Cargo queries pick the new videos up."""
    titles = season_page_titles(seasons)
    if not titles:
        return 0
    return purge_pages(site, titles, dry_run=dry_run)
