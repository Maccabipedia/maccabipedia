"""Write a European game's stage the way MaccabiPedia's editors write it by hand.

The club site gives a qualifier round as a digit ("סיבוב 2") and never says which leg a game is.
The wiki writes the round as a word and adds the leg: "סיבוב שני - משחק 1", "פלייאוף - משחק 2",
"שמינית גמר - משחק 1". League-phase rounds ("מחזור 3") are written as the site gives them.

Runs on the club-site source only, after the general fixes made the competition the plain name.
The leg is the game's place, by date, among the season's games of the same competition and stage,
so it needs the whole crawled season, not only the newest game.
"""
import logging
import re
from collections import defaultdict

logger = logging.getLogger(__name__)

EUROPEAN_COMPETITIONS = frozenset(["ליגת האלופות", "הליגה האירופית", "הליגה האזורית"])

_ROUND_ORDINALS = {1: "ראשון", 2: "שני", 3: "שלישי", 4: "רביעי"}
_NUMBERED_ROUND = re.compile(r"^סיבוב (\d+)$")
_LEG_SEPARATOR = " - "
_LEAGUE_PHASE_ROUND = "מחזור"
_SINGLE_GAME_STAGES = frozenset(["גמר"])
NO_ROUND_FOUND = "No round found"


def _stage_with_round_as_word(stage: str) -> str:
    numbered_round = _NUMBERED_ROUND.match(stage)
    if not numbered_round:
        return stage
    ordinal = _ROUND_ORDINALS.get(int(numbered_round.group(1)))
    return f"סיבוב {ordinal}" if ordinal else stage


def _is_two_legged_stage(stage: str) -> bool:
    if stage in ("", NO_ROUND_FOUND) or stage in _SINGLE_GAME_STAGES:
        return False
    if stage.startswith(_LEAGUE_PHASE_ROUND) or _LEG_SEPARATOR in stage:
        return False
    return True


def fix_european_stages(maccabi_games_stats):
    """Rewrite each European game's fixture to the wiki's wording. Changes the games in place."""
    games_by_stage = defaultdict(list)
    for game in maccabi_games_stats.games:
        if game.competition not in EUROPEAN_COMPETITIONS or not isinstance(game.fixture, str):
            continue
        stage = _stage_with_round_as_word(game.fixture)
        if stage != game.fixture:
            logger.info(f"Changing European stage at {game.date} from: {game.fixture}-->{stage}")
            game.fixture = stage
        if _is_two_legged_stage(stage):
            games_by_stage[(game.season, game.competition, stage)].append(game)

    for (_, _, stage), games in games_by_stage.items():
        for leg, game in enumerate(sorted(games, key=lambda stage_game: stage_game.date), start=1):
            game.fixture = f"{stage}{_LEG_SEPARATOR}משחק {leg}"
            logger.info(f"Setting European stage at {game.date} to: {game.fixture}")

    return maccabi_games_stats
