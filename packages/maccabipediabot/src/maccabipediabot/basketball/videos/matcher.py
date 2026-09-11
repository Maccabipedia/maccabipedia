"""Decide which game page, if any, each channel video belongs to.

A title gives the season (from its playlist), the final score and the opponent — never
a date. The score pair is very nearly unique inside one season, so it does the work of
finding candidate games, and the opponent confirms the answer. Anything the pair plus
the opponent cannot settle is reported for a human rather than guessed at:

    exact            one game, opponent agrees -> safe to write
    ambiguous        several games share the score, or the opponent disagrees,
                     or only the reversed score exists, or the duration is wrong
    unmatched        no game in that season ended with that score
    already_present  that exact URL is already on the page
    overflow         the page has no free slot left for this kind of video
"""
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum

from maccabipediabot.basketball.videos.aliases import opponent_matches, resolve_opponent
from maccabipediabot.basketball.videos.cargo import GameRow
from maccabipediabot.basketball.videos.inventory import VideoEntry
from maccabipediabot.basketball.videos.title_parser import ParsedTitle, VideoKind, parse_game_video_title

logger = logging.getLogger(__name__)

HIGHLIGHTS_SLOTS = ("תקציר וידאו", "תקציר וידאו2")
FULL_GAME_SLOTS = ("משחק מלא", "משחק מלא2")

# A תרכיז is an extended highlight, so it shares the תקציר slots rather than
# competing with a real full game for the משחק מלא pair.
SLOTS: dict[VideoKind, tuple[str, str]] = {
    VideoKind.HIGHLIGHTS: HIGHLIGHTS_SLOTS,
    VideoKind.CONDENSED: HIGHLIGHTS_SLOTS,
    VideoKind.FULL_GAME: FULL_GAME_SLOTS,
}

# Within one slot family a real תקציר outranks a תרכיז, and Hebrew outranks English.
_KIND_RANK = {VideoKind.HIGHLIGHTS: 0, VideoKind.FULL_GAME: 0, VideoKind.CONDENSED: 1}

# Sanity ranges, in seconds. Only applied when a duration is known: RSS has none.
DURATION_RANGE: dict[VideoKind, tuple[int, int]] = {
    VideoKind.HIGHLIGHTS: (45, 20 * 60),
    VideoKind.CONDENSED: (5 * 60, 45 * 60),
    VideoKind.FULL_GAME: (40 * 60, 5 * 60 * 60),
}

MACCABI_CHANNEL = "maccabi-channel"
EUROLEAGUE_CHANNEL = "euroleague-channel"


class Bucket(Enum):
    EXACT = "exact"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"
    ALREADY_PRESENT = "already_present"
    OVERFLOW = "overflow"


@dataclass
class VideoMatch:
    entry: VideoEntry
    parsed: ParsedTitle | None
    bucket: Bucket
    reason: str
    page_name: str | None = None
    candidates: list[str] = field(default_factory=list)
    slot: str | None = None
    source: str = MACCABI_CHANNEL

    @property
    def url(self) -> str:
        return self.entry.url


def existing_urls_for_family(row: GameRow, family: tuple[str, str]) -> tuple[str, str]:
    return row.highlights if family == HIGHLIGHTS_SLOTS else row.full_games


def _duration_is_sane(entry: VideoEntry, kind: VideoKind) -> bool:
    if not entry.duration_seconds:
        return True  # unknown duration: nothing to check against
    low, high = DURATION_RANGE[kind]
    return low <= entry.duration_seconds <= high


def _classify(entry: VideoEntry, parsed: ParsedTitle,
              rows_by_season: dict[str, list[GameRow]], overrides: dict[str, str]) -> VideoMatch:
    if entry.video_id in overrides:
        return VideoMatch(entry, parsed, Bucket.EXACT, "override", page_name=overrides[entry.video_id])

    season_rows = rows_by_season.get(entry.season, [])
    score = (parsed.maccabi_points, parsed.opponent_points)
    same_score = [row for row in season_rows if (row.maccabi_points, row.opponent_points) == score]

    if not same_score:
        reversed_score = [row for row in season_rows
                          if (row.opponent_points, row.maccabi_points) == score]
        if reversed_score:
            return VideoMatch(entry, parsed, Bucket.AMBIGUOUS, "only the swapped score exists",
                              candidates=[row.page_name for row in reversed_score])
        return VideoMatch(entry, parsed, Bucket.UNMATCHED, "no game in this season ended with that score")

    by_opponent = [row for row in same_score if opponent_matches(parsed.opponent_raw, row.opponent)]
    if len(by_opponent) != 1:
        if len(by_opponent) > 1:
            reason = "several games against this opponent share the score"
            candidates = [row.page_name for row in by_opponent]
        elif resolve_opponent(parsed.opponent_raw) is None:
            reason = f"opponent not recognised: {parsed.opponent_raw!r}"
            candidates = [row.page_name for row in same_score]
        elif len(same_score) == 1:
            reason = (f"opponent disagrees: title says {parsed.opponent_raw!r}, "
                      f"page says {same_score[0].opponent!r}")
            candidates = [same_score[0].page_name]
        else:
            reason = "several games share this score and none matches the opponent"
            candidates = [row.page_name for row in same_score]
        return VideoMatch(entry, parsed, Bucket.AMBIGUOUS, reason, candidates=candidates)

    chosen = by_opponent[0]
    if not _duration_is_sane(entry, parsed.kind):
        return VideoMatch(entry, parsed, Bucket.AMBIGUOUS,
                          f"duration {entry.duration_seconds}s is outside the {parsed.kind.value} range",
                          candidates=[chosen.page_name])
    if entry.url in existing_urls_for_family(chosen, SLOTS[parsed.kind]):
        return VideoMatch(entry, parsed, Bucket.ALREADY_PRESENT, "this URL is already on the page",
                          page_name=chosen.page_name)
    return VideoMatch(entry, parsed, Bucket.EXACT, "score and opponent agree", page_name=chosen.page_name)


def assign_slots(matches: list[VideoMatch], rows_by_page: dict[str, GameRow]) -> None:
    """Give each exact match a free template parameter, or mark it as overflow.

    Grouped by slot FAMILY rather than by kind, so highlights and condensed games
    compete for the same two תקציר parameters instead of each claiming both.
    """
    per_page_family: dict[tuple[str, tuple[str, str]], list[VideoMatch]] = defaultdict(list)
    for match in matches:
        if match.bucket == Bucket.EXACT and match.parsed is not None and match.page_name:
            per_page_family[(match.page_name, SLOTS[match.parsed.kind])].append(match)

    for (page_name, family), group in per_page_family.items():
        group.sort(key=lambda match: (_KIND_RANK[match.parsed.kind],
                                      match.parsed.language != "he",
                                      match.entry.video_id))
        row = rows_by_page.get(page_name)
        existing = existing_urls_for_family(row, family) if row else ("", "")
        free_slots = [slot for slot, url in zip(family, existing) if not url]
        for match in group:
            if free_slots:
                match.slot = free_slots.pop(0)
            else:
                match.bucket = Bucket.OVERFLOW
                match.reason = f"no free {family[0]} slot on the page"


def match_videos(entries: list[VideoEntry], rows: list[GameRow],
                 overrides: dict[str, str]) -> list[VideoMatch]:
    rows_by_season: dict[str, list[GameRow]] = defaultdict(list)
    for row in rows:
        rows_by_season[row.season].append(row)
    rows_by_page = {row.page_name: row for row in rows}

    matches: list[VideoMatch] = []
    seen_video_ids: set[str] = set()
    skipped_non_game = 0
    for entry in entries:
        if entry.video_id in seen_video_ids:
            continue  # the same video is listed in both the season and highlights playlists
        seen_video_ids.add(entry.video_id)
        parsed = parse_game_video_title(entry.title)
        if parsed is None:
            skipped_non_game += 1
            continue
        matches.append(_classify(entry, parsed, rows_by_season, overrides))

    assign_slots(matches, rows_by_page)
    logger.info("Matched %d game videos (%d channel videos were not game videos)",
                len(matches), skipped_non_game)
    return matches


def count_non_game_videos(entries: list[VideoEntry]) -> int:
    """How many distinct videos were not game videos at all (for the report header)."""
    seen: set[str] = set()
    non_game = 0
    for entry in entries:
        if entry.video_id in seen:
            continue
        seen.add(entry.video_id)
        if parse_game_video_title(entry.title) is None:
            non_game += 1
    return non_game
