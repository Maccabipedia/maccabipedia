"""The table of football players' titles: build its data page, check it, prove it.

`Football_Player_Titles` holds one row per credit (player, season, competition). The rows
are stored by one wiki page, `הזנת תארי שחקני כדורגל`, which this job writes from the game
sheets and the won titles. Nothing reads the table yet.

Usage (every command is a dry run or read-only unless --live is given):

    # What a rebuild would write to production:
    uv run python -m maccabipediabot.maintenance.football.player_titles rebuild

    # Write one season first (the canary), then everything:
    uv run python -m maccabipediabot.maintenance.football.player_titles rebuild --live --only-season 1925
    uv run python -m maccabipediabot.maintenance.football.player_titles rebuild --live

    # Does the table hold exactly the rows the page stores?
    uv run python -m maccabipediabot.maintenance.football.player_titles verify

    # Make the page store its rows again without changing it (after a save that died):
    uv run python -m maccabipediabot.maintenance.football.player_titles restore --live

    # Do the credits give every profile the title lists it shows today? (read-only)
    uv run python -m maccabipediabot.maintenance.football.player_titles gate --credits-from rule
    uv run python -m maccabipediabot.maintenance.football.player_titles gate --credits-from table
    uv run python -m maccabipediabot.maintenance.football.player_titles gate --selftest   # must fail

    # The local test wiki instead of production (the page and table there, the game data
    # from production, because the local wiki holds only a sample of games):
    LOCAL_WIKI_USER=... LOCAL_WIKI_PASSWORD=... uv run python -m \\
        maccabipediabot.maintenance.football.player_titles rebuild --live \\
        --local-api-url http://localhost:8080/api.php --exports-from-production
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from maccabipediabot.common.logging_setup import setup_logging
from maccabipediabot.maintenance.football.player_titles import gate, job
from maccabipediabot.maintenance.football.player_titles.api import Api, local_api, production_api
from maccabipediabot.maintenance.football.player_titles.exports import competition_kinds, seasons_played, won_titles
from maccabipediabot.maintenance.football.player_titles.page import parse_page, render_page, stored_credits
from maccabipediabot.maintenance.football.player_titles.rule import RULE
from maccabipediabot.maintenance.football.player_titles.wiki import logged_in_user, table_credits

logger = logging.getLogger(__name__)


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("rebuild", "verify", "restore", "gate"))
    parser.add_argument("--live", action="store_true", help="Actually save (default: dry run)")
    parser.add_argument("--local-api-url", help="Work on the local test wiki at this api.php instead of production")
    parser.add_argument(
        "--exports-from-production", action="store_true",
        help="With --local-api-url: take the game sheets and won titles from production",
    )
    parser.add_argument("--only-season", help="rebuild: write only this season (the canary), e.g. 1925")
    parser.add_argument(
        "--allow-shrink", action="store_true",
        help="rebuild: allow a text that drops a title or many lines the page holds now",
    )
    parser.add_argument(
        "--credits-from", choices=("rule", "table"), default="rule",
        help="gate: compare the live lists with what the rule would write, or with the table as it is",
    )
    parser.add_argument("--limit", type=int, help="gate: compare only the first N profiles")
    parser.add_argument("--selftest", action="store_true", help="gate: compare two different players; must fail")
    return parser.parse_args()


def _gate(arguments: argparse.Namespace, production: Api) -> int:
    """Always against production: the live profiles are there."""
    if arguments.credits_from == "table":
        credits = table_credits(production)
    else:
        text = render_page(RULE(won_titles(production), seasons_played(production)), job.PROFILE_REMOVALS)
        credits = stored_credits(parse_page(text))

    profiles = gate.profiles(production)
    name_override = None
    if arguments.selftest:
        profiles = [profile for profile in profiles if profile.title == gate.SELFTEST_PROFILE]
        name_override = gate.SELFTEST_OTHER_PLAYER
        logger.info("SELFTEST: %s against the credits of %s - this must fail", gate.SELFTEST_PROFILE, name_override)
    elif arguments.limit:
        profiles = profiles[:arguments.limit]
    return gate.run_gate(production, profiles, credits.elements(), competition_kinds(production), credits_name_override=name_override)


def main() -> int:
    arguments = _parse_arguments()
    setup_logging(level=logging.INFO)

    if arguments.command == "gate":
        return _gate(arguments, production_api())

    if arguments.local_api_url:
        api = local_api(arguments.local_api_url, os.environ["LOCAL_WIKI_USER"], os.environ["LOCAL_WIKI_PASSWORD"])
        exports_api = production_api() if arguments.exports_from_production else api
    else:
        api = exports_api = production_api()

    if arguments.command == "verify":
        return job.verify(api)
    if arguments.command == "restore":
        if not arguments.live:
            logger.info("[DRY-RUN] restore would save the page with its text unchanged; pass --live")
            return 0
        return job.restore(api)
    return job.rebuild(
        api, exports_api, live=arguments.live, only_season=arguments.only_season, bot_user=logged_in_user(api),
        allow_shrink=arguments.allow_shrink,
    )


if __name__ == "__main__":
    sys.exit(main())
