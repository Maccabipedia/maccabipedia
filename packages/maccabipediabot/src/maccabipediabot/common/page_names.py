from datetime import date

_FOOTBALL_PREFIX = "משחק"
_VOLLEYBALL_PREFIX = "כדורעף"
_BASKETBALL_PREFIX = "כדורסל"


def build_game_page_name(prefix: str, game_date: date, home_team: str,
                     away_team: str, competition: str) -> str:
    formatted_date = game_date.strftime('%d-%m-%Y')
    return f'{prefix}:{formatted_date} {home_team} נגד {away_team} - {competition}'


def build_football_game_page_name(game_date: date, home_team: str,
                                  away_team: str, competition: str) -> str:
    return build_game_page_name(_FOOTBALL_PREFIX, game_date, home_team, away_team, competition)


def build_volleyball_game_page_name(game_date: date, home_team: str,
                                    away_team: str, competition: str) -> str:
    return build_game_page_name(_VOLLEYBALL_PREFIX, game_date, home_team, away_team, competition)


# Competitions whose game-page titles use a shorter name than the Competition field:
# all 46 Winner Cup pages are titled "... - גביע ווינר" while storing "גביע ווינר סל".
_BASKETBALL_TITLE_COMPETITION = {
    "גביע ווינר סל": "גביע ווינר",
}


def build_basketball_game_page_name(game_date: date, home_team: str,
                                    away_team: str, competition: str) -> str:
    title_competition = _BASKETBALL_TITLE_COMPETITION.get(competition, competition)
    return build_game_page_name(_BASKETBALL_PREFIX, game_date, home_team, away_team, title_competition)
