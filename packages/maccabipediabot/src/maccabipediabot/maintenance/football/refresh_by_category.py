"""Reparse profile pages so their live-computed title/season categories refresh.

A player's "won N titles" / "played N seasons" categories are computed inside the
profile template from Cargo data (the player's played seasons intersected with
Maccabi's `Achievements` rows). MediaWiki does NOT re-parse those pages when the
underlying Cargo data changes, so after a new title is recorded the counts stay
frozen at the old value. New milestone categories — e.g.
`שחקני כדורגל שזכו ב-18 תארים` — therefore never gain members: they stay red-linked
and invisible in the DPL navigation strips.

The game-upload purge doesn't cover this: it only purges players who *appeared in
the uploaded game*, while the trophy is a separate `Achievements` row written by a
season-page edit that purges no profiles at all.

Scope
-----
By default this refreshes only the players who played for Maccabi in the **two most
recent seasons** (~60 pages, ~2 min). That is the set whose counts can actually
change when a title is recorded, because the profile template derives titles from
*seasons the player played* — so a squad member who never played doesn't earn the
title under the current model anyway.

Two seasons rather than one, because the seasons roll over mid-July while a title
for the season that just ended is recorded around then: refreshing only the newest
season would miss winners who left the club over the summer.

`--all` sweeps every profile in the category instead (~800 pages, ~30 min). That
is only needed after **historical** data work that rewrites old `Achievements`
rows, since adding an old *game* already purges its players via the game-upload
path. Run it by hand after such a fix rather than on a schedule.

Idempotent — safe to re-run.

Usage:
    # Dry-run of the latest season (default; purges nothing):
    uv run python -m maccabipediabot.maintenance.football.refresh_by_category

    # Live, latest season (what the scheduled workflow runs):
    uv run python -m maccabipediabot.maintenance.football.refresh_by_category --live

    # Live, a specific season:
    uv run python -m maccabipediabot.maintenance.football.refresh_by_category --live --season 2024/25

    # Live, every profile — after historical Achievements fixes:
    uv run python -m maccabipediabot.maintenance.football.refresh_by_category --live --all
"""
from __future__ import annotations

import logging

import pywikibot
from pywikibot.exceptions import ServerError, TimeoutError as PwbTimeoutError

from maccabipediabot.common.logging_setup import setup_logging
from maccabipediabot.common.wiki_login import get_site
from maccabipediabot.common.wiki_purge import purge_pages

logger = logging.getLogger(__name__)

DEFAULT_CATEGORY = "פרופילי כדורגל"

# Games_Events.Team is an Integer flag: 1 = Maccabi, 0 = the opponent.
MACCABI_TEAM_ID = 1

# Two seasons, not one: a title for the season that just ended is typically
# recorded *after* the next season has already kicked off (mid-July rollover), so
# refreshing only the newest season would miss winners who then left the club.
DEFAULT_RECENT_SEASONS = 2

# Profile pages are expensive to re-parse (each runs several Cargo/stats queries,
# ~2-3s per page), and `forcelinkupdate` makes the server do that work inline.
# wiki_purge's default of 50 titles/request overshoots the 45s read timeout and
# aborts the whole sweep, so batch far smaller here.
BATCH_SIZE = 10


def cargo_query(site: pywikibot.Site, **params: str | int) -> list[dict]:
    """Run a Cargo query over pywikibot's authenticated session, return its rows."""
    response = site.simple_request(action="cargoquery", format="json", **params).submit()
    return [row["title"] for row in response.get("cargoquery", [])]


def resolve_recent_seasons(site: pywikibot.Site, count: int) -> list[str]:
    """Return the `count` most recently played seasons, newest first."""
    rows = cargo_query(
        site,
        tables="Football_Games",
        fields="Season, MAX(Date)=LastDate",
        group_by="Season",
        order_by="MAX(Date) DESC",
        limit=count,
    )
    if not rows:
        raise RuntimeError("Could not resolve recent seasons — Football_Games is empty")
    return [row["Season"] for row in rows]


def collect_season_players(
    site: pywikibot.Site, seasons: list[str]
) -> list[pywikibot.Page]:
    """Return profile pages for everyone who played for Maccabi in `seasons`."""
    quoted_seasons = ", ".join(f"'{season}'" for season in seasons)
    rows = cargo_query(
        site,
        tables="Games_Events=e, Football_Games=g",
        join_on="e.Date=g.Date",
        fields="e.PlayerName=PlayerName",
        where=f"g.Season IN ({quoted_seasons}) AND e.Team={MACCABI_TEAM_ID}",
        group_by="e.PlayerName",
        limit=500,
    )
    return [pywikibot.Page(site, row["PlayerName"]) for row in rows if row.get("PlayerName")]


def collect_members(site: pywikibot.Site, category: str) -> list[pywikibot.Page]:
    """Return the article members of `category` (excludes subcategories)."""
    return list(pywikibot.Category(site, category).articles(recurse=False))


def purge_in_batches(site: pywikibot.Site, pages: list[pywikibot.Page], dry_run: bool) -> int:
    """Purge `pages` in small independent batches. Returns the failed-batch count.

    A batch that times out is logged and skipped rather than aborting the sweep,
    so one slow request can't cost us the remaining profiles.
    """
    purged = 0
    failed_batches = 0
    for start in range(0, len(pages), BATCH_SIZE):
        batch = pages[start:start + BATCH_SIZE]
        try:
            purged += purge_pages(site, batch, dry_run=dry_run, chunk_size=BATCH_SIZE)
        except (ServerError, PwbTimeoutError) as exc:
            # The server is just slow on these re-parses; the next scheduled run
            # retries this batch. Keep going so one batch can't sink the sweep.
            failed_batches += 1
            logger.warning(
                "Batch %d-%d failed (%s: %s) — continuing",
                start, start + len(batch) - 1, type(exc).__name__, exc,
            )

    logger.info(
        "Done: %d/%d pages %s, %d batches failed",
        purged, len(pages), "would be purged" if dry_run else "purged", failed_batches,
    )
    return failed_batches


def main(
    dry_run: bool,
    refresh_all: bool,
    category: str,
    season: str | None,
    recent_seasons: int,
) -> int:
    """Refresh profiles so their live categorylinks reflect current Cargo data.

    Returns 1 if any batch failed so CI surfaces a partial sweep.
    """
    setup_logging(level=logging.INFO)
    site = get_site()

    if refresh_all:
        pages = collect_members(site, category)
        logger.info("Refreshing all %d profiles in category %r", len(pages), category)
    else:
        seasons = [season] if season else resolve_recent_seasons(site, recent_seasons)
        pages = collect_season_players(site, seasons)
        logger.info(
            "Refreshing %d players who played in season(s) %s",
            len(pages), ", ".join(seasons),
        )

    return 1 if purge_in_batches(site, pages, dry_run=dry_run) else 0


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", default=False,
        help="Actually purge the pages (default: dry-run)",
    )
    parser.add_argument(
        "--all", dest="refresh_all", action="store_true", default=False,
        help="Refresh every profile instead of just the latest season (slow; "
             "for after historical Achievements fixes)",
    )
    parser.add_argument(
        "--season", default=None,
        help="Refresh exactly this season instead of the recent ones (e.g. 2024/25)",
    )
    parser.add_argument(
        "--recent-seasons", type=int, default=DEFAULT_RECENT_SEASONS,
        help=f"How many recent seasons to refresh (default: {DEFAULT_RECENT_SEASONS}). "
             "Two covers the mid-year rollover, when a title for the season that just "
             "ended is recorded after the next season has already started.",
    )
    parser.add_argument(
        "--category", default=DEFAULT_CATEGORY,
        help=f"Profiles category swept by --all (default: {DEFAULT_CATEGORY})",
    )
    args = parser.parse_args()
    sys.exit(main(
        dry_run=not args.live,
        refresh_all=args.refresh_all,
        category=args.category,
        season=args.season,
        recent_seasons=args.recent_seasons,
    ))
