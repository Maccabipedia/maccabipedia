"""The commands of the player-titles job: rebuild the data page, verify the table, restore it.

Until player profiles read the table, the data page belongs to the bot: `rebuild` rewrites
it from the rule. It still refuses to write over anything it did not expect to find.
"""
from __future__ import annotations

import difflib
import logging
import time
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from maccabipediabot.maintenance.football.player_titles.api import Api, ApiError
from maccabipediabot.maintenance.football.player_titles.exports import seasons_played, won_titles
from maccabipediabot.maintenance.football.player_titles.page import (
    HEADER_MARKER,
    PAGE_TITLE,
    parse_page,
    render_page,
    stored_credits,
)
from maccabipediabot.maintenance.football.player_titles.rule import RULE, Credit
from maccabipediabot.maintenance.football.player_titles.wiki import PageState, read_page, save_page, table_credits

logger = logging.getLogger(__name__)

# Saving the page empties the table and fills it again row by row, so for a while after any
# save the table is short. Nothing is saved or judged on top of a revision younger than this.
QUIET_PERIOD = timedelta(minutes=5)

# The table is read a second time, this much later, before it is called wrong.
VERIFY_WAIT_SECONDS = 60

# The corrections that live on player profiles today, in the fields
# `הסרת זכיות ... כשחקן`. They move to the data page so the table gives the same answer
# the profile shows; the fields themselves are retired when profiles start reading the table.
PROFILE_REMOVALS: dict[Credit, str] = {
    Credit("אסטר סוקלר", "2026/27", "אלוף האלופים"): "הגיע אחרי הזכייה (הועבר משדה ההסרה בפרופיל)",
    Credit("נועם לוי", "2026/27", "אלוף האלופים"): "הגיע אחרי הזכייה (הועבר משדה ההסרה בפרופיל)",
}

REBUILD_SUMMARY = "בניית עמוד תארי שחקני הכדורגל מנתוני המשחקים (בוט)"
RESTORE_SUMMARY = "אחסון מחדש של שורות הטבלה (בוט)"

_DIFF_LINES_SHOWN = 60
_DIFFERENCES_SHOWN = 20


def _is_quiet(state: PageState, now: datetime) -> bool:
    return state.last_edit is None or now - state.last_edit >= QUIET_PERIOD


def _refusal_to_overwrite(state: PageState, bot_user: str) -> str | None:
    """Why the page as found must not be rewritten, or None."""
    if not state.exists:
        return None
    if state.is_redirect:
        return "the page is a redirect"
    if HEADER_MARKER not in state.text:
        return "the page does not carry the data page's header marker"
    if state.last_editor != bot_user:
        return f"the page was last edited by {state.last_editor}, not by {bot_user}"
    return None


def rebuild(
    api: Api,
    exports_api: Api,
    *,
    live: bool,
    only_season: str | None,
    bot_user: str,
    now: datetime | None = None,
    verify_wait_seconds: float = VERIFY_WAIT_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Rewrite the data page from the rule. Returns the exit code."""
    now = now or datetime.now(timezone.utc)
    credits_by_title = RULE(won_titles(exports_api), seasons_played(exports_api))
    removed = dict(PROFILE_REMOVALS)
    if only_season is not None:
        credits_by_title = {title: players for title, players in credits_by_title.items() if title.season == only_season}
        removed = {credit: reason for credit, reason in removed.items() if credit.season == only_season}
    if not credits_by_title:
        logger.error("No won title to write%s", f" in season {only_season}" if only_season else "")
        return 1

    text = render_page(credits_by_title, removed)
    state = read_page(api)
    refusal = _refusal_to_overwrite(state, bot_user)
    if refusal:
        logger.error("Not rebuilding %s: %s", PAGE_TITLE, refusal)
        return 1

    logger.info(
        "%s: %d titles, %d stored lines, %d bytes",
        PAGE_TITLE, len(credits_by_title), sum(stored_credits(parse_page(text)).values()), len(text.encode("utf-8")),
    )
    if text == state.text:
        logger.info("The page already holds this text; nothing to save")
        return verify(api, wait_seconds=verify_wait_seconds, sleep=sleep) if live else 0

    diff = list(difflib.unified_diff(state.text.splitlines(), text.splitlines(), "on the wiki", "rebuilt", lineterm="", n=0))
    logger.info("%d diff lines; the first %d:\n%s", len(diff), _DIFF_LINES_SHOWN, "\n".join(diff[:_DIFF_LINES_SHOWN]))
    if not live:
        logger.info("[DRY-RUN] Nothing saved")
        return 0

    if not _is_quiet(state, now):
        logger.error("Not rebuilding %s: its last revision is under %s old and may still be storing", PAGE_TITLE, QUIET_PERIOD)
        return 1
    try:
        result = save_page(api, text, state, summary=REBUILD_SUMMARY)
    except ApiError as error:
        logger.error("The save failed (%s). Read the page before trying again - the save may have gone through", error)
        return 1
    logger.info("Saved revision %s in %.1f s", result.revision_id, result.seconds)
    return verify(api, wait_seconds=verify_wait_seconds, sleep=sleep)


def verify(api: Api, *, wait_seconds: float = VERIFY_WAIT_SECONDS, sleep: Callable[[float], None] = time.sleep) -> int:
    """The table must hold exactly the rows the page stores. Returns the exit code."""
    expected: Counter[Credit] = Counter()
    actual: Counter[Credit] = Counter()
    for attempt in (1, 2):
        state = read_page(api)
        if not state.exists:
            logger.error("%s does not exist", PAGE_TITLE)
            return 1
        expected = stored_credits(parse_page(state.text))
        actual = table_credits(api)
        if expected == actual:
            logger.info("The table equals the page: %d rows", sum(actual.values()))
            return 0
        if attempt == 1:
            logger.warning("The table differs from the page; reading again in %s s", wait_seconds)
            sleep(wait_seconds)

    missing, extra = expected - actual, actual - expected
    logger.error(
        "The table differs from the page: %d rows on the page are not in the table, %d rows in the table are not on the page",
        sum(missing.values()), sum(extra.values()),
    )
    for label, difference in (("not in the table", missing), ("not on the page", extra)):
        for credit, count in list(difference.items())[:_DIFFERENCES_SHOWN]:
            logger.error("  %s: %s | %s | %s (x%d)", label, credit.player, credit.season, credit.competition, count)
    return 1


def restore(
    api: Api,
    *,
    now: datetime | None = None,
    verify_wait_seconds: float = VERIFY_WAIT_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Make the page store its rows again without changing its text.

    A save with unchanged text makes no revision, and Cargo still deletes the page's rows
    and stores them again. A purge does not.
    """
    now = now or datetime.now(timezone.utc)
    state = read_page(api)
    if not state.exists or state.is_redirect:
        logger.error("%s is missing or a redirect; nothing to restore", PAGE_TITLE)
        return 1
    if not _is_quiet(state, now):
        logger.error("Not restoring %s: its last revision is under %s old and may still be storing", PAGE_TITLE, QUIET_PERIOD)
        return 1
    try:
        result = save_page(api, state.text, state, summary=RESTORE_SUMMARY)
    except ApiError as error:
        logger.error("The restoring save failed (%s)", error)
        return 1
    logger.info("Stored again in %.1f s (%s)", result.seconds, "a new revision was made" if result.changed else "no new revision")
    return verify(api, wait_seconds=verify_wait_seconds, sleep=sleep)
