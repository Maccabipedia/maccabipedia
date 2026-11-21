"""The Super Cup (אלוף האלופים) stage, which the club site does not give.

The site gives no round, or the competition name itself as the round. The wiki writes "גמר" for a
one-game Super Cup, and "גמר - משחק 1" / "גמר - משחק 2" for the two-legged ones (1965/66, 2020/21),
so the leg is the game's date order among the season's Super Cup games. A real round the site
gives is kept as it is.
"""
import logging
from collections import defaultdict

from maccabistats.parse.maccabi_tlv_site.european_stages import NO_ROUND_FOUND

logger = logging.getLogger(__name__)

SUPER_CUP = "אלוף האלופים"
FINAL_STAGE = "גמר"
_ROUNDS_THAT_SAY_NOTHING = ("", NO_ROUND_FOUND, None, SUPER_CUP)


def fix_super_cup_stage(maccabi_games_stats):
    """Set the stage of club-site Super Cup games with no round. Changes the games in place."""
    games_by_season = defaultdict(list)
    for game in maccabi_games_stats.games:
        if game.competition == SUPER_CUP and game.fixture in _ROUNDS_THAT_SAY_NOTHING:
            games_by_season[game.season].append(game)

    for games in games_by_season.values():
        if len(games) == 1:
            games[0].fixture = FINAL_STAGE
        else:
            for leg, game in enumerate(sorted(games, key=lambda super_cup_game: super_cup_game.date), start=1):
                game.fixture = f"{FINAL_STAGE} - משחק {leg}"
        for game in games:
            logger.info(f"Setting Super Cup stage at {game.date} to: {game.fixture}")

    return maccabi_games_stats
