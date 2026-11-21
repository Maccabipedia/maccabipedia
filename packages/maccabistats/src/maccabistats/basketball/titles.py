"""How basketball game-page titles name things differently from the game's own fields."""

# Game-page titles name a competition by its historical short form where the wiki does:
# all Winner Cup pages are titled "... - גביע ווינר" while storing "גביע ווינר סל".
_TITLE_COMPETITION = {
    "גביע ווינר סל": "גביע ווינר",
}


def basketball_title_competition(competition: str) -> str:
    """The competition as a basketball game-page title names it."""
    return _TITLE_COMPETITION.get(competition, competition)
