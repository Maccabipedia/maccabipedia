"""The Super Cup (אלוף האלופים) is one game, a final, and the club site gives it no round.

The wiki writes its stage as "גמר" (editors set it by hand on every new page), so the club-site
source writes it too. A round the site does give is kept as it is.
"""
import logging

logger = logging.getLogger(__name__)

SUPER_CUP = "אלוף האלופים"
FINAL_STAGE = "גמר"
_NO_ROUND_FOUND = "No round found"


def fix_super_cup_stage(maccabi_games_stats):
    """Set the stage of club-site Super Cup games with no round to "גמר". Changes the games in place."""
    for game in maccabi_games_stats.games:
        if game.competition == SUPER_CUP and game.fixture in ("", _NO_ROUND_FOUND, None):
            logger.info(f"Setting Super Cup stage at {game.date} to: {FINAL_STAGE}")
            game.fixture = FINAL_STAGE
    return maccabi_games_stats
