"""How basketball game-page titles name things differently from the game's own fields."""

# Game-page titles name a competition by its historical short form where the wiki does:
# all Winner Cup pages are titled "... - גביע ווינר" while storing "גביע ווינר סל".
# The bot's page-name builder (maccabipediabot.common.page_names) holds the same map for writing
# titles; it does not import this one, so the uploaders do not load maccabistats. A bot test
# keeps the two equal.
TITLE_COMPETITION = {
    "גביע ווינר סל": "גביע ווינר",
}


def basketball_title_competition(competition: str) -> str:
    """The competition as a basketball game-page title names it."""
    return TITLE_COMPETITION.get(competition, competition)
