"""Sync DPL-based navigation templates onto trophy/seasons category pages.

Replaces the older `football/add_player_category_navbars.py` (which built a
different, now-superseded per-(sport,type) template system).

For every existing category page matching one of four patterns:
  - שחקני {sport} שזכו ב-{N} {trophy_type}
  - אנשי צוות {sport} שזכו ב-{N} {trophy_type}
  - שחקני {sport} ששיחקו {N} עונות במכבי
  - אנשי צוות {sport} שהיו {N} עונות במכבי

…overwrite the page with the canonical `{{ניווט קטגוריות …}}` invocation
when it differs from the current text, then purge with forcelinkupdate=true
so the DPL caches refresh.

Idempotent — safe to re-run.

Usage:
    # Dry-run (default; prints planned changes, makes no edits):
    uv run python -m maccabipediabot.maintenance.sync_navigation_categories

    # Live run (all sports):
    uv run python -m maccabipediabot.maintenance.sync_navigation_categories --live

    # Live run, single sport:
    uv run python -m maccabipediabot.maintenance.sync_navigation_categories --live --sport כדורסל
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterator, Literal

import pywikibot

from maccabipediabot.common.logging_setup import setup_logging
from maccabipediabot.common.wiki_login import get_site
from maccabipediabot.common.wiki_purge import purge_pages

logger = logging.getLogger(__name__)

EDIT_SUMMARY = "בוט: התקנת תבנית ניווט בעמוד קטגוריה"

# Count is 1–99 — mirrors the DPL templates' [1-9] and [1-9][0-9] regex.
# N=0 and N≥100 don't render in the nav strip, so don't waste edits on them.
_RE_TROPHY_PLAYERS = re.compile(r"^שחקני (\S+) שזכו ב-([1-9][0-9]?) (.+)$")
_RE_TROPHY_STAFF = re.compile(r"^אנשי צוות (\S+) שזכו ב-([1-9][0-9]?) (.+)$")
_RE_SEASONS_PLAYERS = re.compile(r"^שחקני (\S+) ששיחקו ([1-9][0-9]?) עונות במכבי$")
_RE_SEASONS_STAFF = re.compile(r"^אנשי צוות (\S+) שהיו ([1-9][0-9]?) עונות במכבי$")

TEMPLATE_TROPHY = "ניווט קטגוריות זכיה בתארים"
TEMPLATE_SEASONS = "ניווט קטגוריות עונות במכבי"


@dataclass(frozen=True)
class ParsedMatch:
    kind: Literal["זכיה", "עונות"]
    sport: str
    role: Literal["שחקנים", "צוות"]
    count: int
    trophy_type: str | None  # None for עונות


def parse_category_title(title: str) -> ParsedMatch | None:
    """Parse a category title into a ParsedMatch, or return None if it doesn't match.

    `title` is the page title without the `קטגוריה:` namespace prefix.
    """
    for regex, kind, role in (
        (_RE_TROPHY_PLAYERS, "זכיה", "שחקנים"),
        (_RE_TROPHY_STAFF, "זכיה", "צוות"),
    ):
        trophy_match = regex.match(title)
        if trophy_match:
            return ParsedMatch(
                kind=kind,
                sport=trophy_match.group(1),
                role=role,
                count=int(trophy_match.group(2)),
                trophy_type=trophy_match.group(3),
            )
    for regex, role in (
        (_RE_SEASONS_PLAYERS, "שחקנים"),
        (_RE_SEASONS_STAFF, "צוות"),
    ):
        seasons_match = regex.match(title)
        if seasons_match:
            return ParsedMatch(
                kind="עונות",
                sport=seasons_match.group(1),
                role=role,
                count=int(seasons_match.group(2)),
                trophy_type=None,
            )
    return None


def build_canonical_wikitext(parsed: ParsedMatch) -> str:
    """Return the exact wikitext a category page should contain for this match."""
    staff_param = " |האם אנשי צוות=כן" if parsed.role == "צוות" else ""
    if parsed.kind == "זכיה":
        return (
            f"{{{{{TEMPLATE_TROPHY} |ענף={parsed.sport} "
            f"|תואר={parsed.trophy_type}{staff_param}}}}}"
        )
    return f"{{{{{TEMPLATE_SEASONS} |ענף={parsed.sport}{staff_param}}}}}"


_DISCOVERY_PREFIXES = ("שחקני ", "אנשי צוות ")


def discover_matches(
    site: pywikibot.Site, sport_filter: str | None = None
) -> Iterator[tuple[str, ParsedMatch]]:
    """Yield (title, ParsedMatch) for every category page matching the four patterns.

    Iterates `site.allcategories(prefix=...)` for the two role prefixes; sport_filter
    (if given) further narrows to a single sport.
    """
    for prefix in _DISCOVERY_PREFIXES:
        for cat in site.allcategories(prefix=prefix):
            title = cat.title(with_ns=False)
            parsed = parse_category_title(title)
            if parsed is None:
                continue
            if sport_filter is not None and parsed.sport != sport_filter:
                continue
            yield title, parsed


def main(
    dry_run: bool,
    sport_filter: str | None,
    skip_purge: bool,
) -> int:
    """Run one full sync. Returns 0 (reserved for future error signalling)."""
    setup_logging(level=logging.INFO)
    site = get_site()

    edited = 0
    matched_pages: list[pywikibot.Page] = []

    for title, parsed in discover_matches(site, sport_filter=sport_filter):
        page = pywikibot.Page(site, f"קטגוריה:{title}")
        matched_pages.append(page)
        canonical = build_canonical_wikitext(parsed)
        if page.text == canonical:
            logger.info("[SKIP] %s", page.title())
        else:
            logger.info("[INSTALL] %s → %s", page.title(), canonical)
            edited += 1
            if not dry_run:
                page.text = canonical
                page.save(summary=EDIT_SUMMARY, minor=False)

    purged = 0
    if not skip_purge:
        purged = purge_pages(site, matched_pages, dry_run=dry_run)

    logger.info(
        "Done: %d/%d edited, %d purged",
        edited, len(matched_pages), purged,
    )
    return 0


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", default=False,
        help="Actually edit the wiki (default: dry-run)",
    )
    parser.add_argument(
        "--sport", default=None,
        help="Only process this sport (Hebrew, e.g. כדורגל)",
    )
    parser.add_argument(
        "--no-purge", action="store_true", default=False, help="Skip the purge step"
    )
    args = parser.parse_args()
    sys.exit(main(
        dry_run=not args.live,
        sport_filter=args.sport,
        skip_purge=args.no_purge,
    ))
