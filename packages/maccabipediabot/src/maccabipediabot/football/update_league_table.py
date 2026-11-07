import logging

import mwparserfromhell
import requests

from maccabipediabot.basketball.livescore_table import games_in_play
from maccabipediabot.common.wiki_login import get_site
from maccabipediabot.football.football_co_il_table import TeamRow, fetch_standings, league_table

# Bump each season: the wiki page and football.co.il's season ("26/27") both follow from it.
SEASON = "2026/27"
_LEAGUE_TABLE_TEMPLATE_ON_MACCABIPEDIA = f'תבנית:טבלת_ליגת_כדורגל_{SEASON}'
_FOOTBALL_CO_IL_SEASON = SEASON[2:]
_TABLE_RENDERER = 'טבלת ליגת כדורגל'
_TABLE_STATUS_KEY = 'טבלה'

# The numbers come from football.co.il, the league's own site (see football_co_il_table).
# livescore only says whether a game is being played right now: no table is saved then.
# All three stages, all season: games_in_play only counts games dated within a day, so the
# stages not being played add nothing, and the playoff switch needs no swap here.
LIVESCORE_STAGES_TO_CHECK_FOR_GAMES_IN_PLAY = [
    "https://prod-public-api.livescore.com/v1/api/app/stage/soccer/israel/premier-league/3?locale=en&MD=1",
    "https://prod-public-api.livescore.com/v1/api/app/stage/soccer/israel/premier-league-championship-group/3",
    "https://prod-public-api.livescore.com/v1/api/app/stage/soccer/israel/premier-league-relegation-group/3",
]

from maccabipediabot.common.logging_setup import setup_logging
setup_logging(level=logging.DEBUG)

# We need to log before we run any of our maccabipedia (pywikibot or it's import) related code
site = get_site()

import pywikibot as pw


def a_game_is_in_play() -> bool:
    for url in LIVESCORE_STAGES_TO_CHECK_FOR_GAMES_IN_PLAY:
        stage = requests.get(url, timeout=30).json()["Stages"][0]
        if "Events" not in stage:
            # Without its games, the check would pass on any answer and save mid-game.
            raise RuntimeError(f'livescore stage has no games list, cannot tell a game in play: {url}')
        if in_play := games_in_play(stage):
            logging.warning(f'Not updating the league table, games in play: {in_play}')
            return True
    return False


def games_played_on_the_wiki(table_rows: str) -> dict[str, int]:
    """Games played per team in a saved |טבלה= value (rows "name^played^...", comma-separated)."""
    played = {}
    for row in table_rows.split(","):
        fields = row.strip().split("^")
        if len(fields) > 1 and fields[1].strip().isdigit():
            played[fields[0].strip()] = int(fields[1])
    return played


def check_against_the_wiki(rows: list[TeamRow], saved_played: dict[str, int]) -> None:
    """The new table must hold the teams already on the wiki, none with fewer games.

    Fewer games means a broken table (football.co.il's 2025/26 archive has an all-zero regular
    season), never a newer one. An empty page (a new season) passes.
    """
    if not saved_played:
        return
    names = {row.name for row in rows}
    if names != set(saved_played):
        raise ValueError(f'football.co.il and the wiki list different teams: only on football.co.il '
                         f'{sorted(names - set(saved_played))}, only on the wiki {sorted(set(saved_played) - names)}')
    if behind := [f'{row.name} {saved_played[row.name]}→{row.played}' for row in rows
                  if row.played < saved_played[row.name]]:
        raise ValueError(f'football.co.il has fewer games than the wiki for {behind}; not saving. If a game '
                         f'was really annulled, lower that team\'s games in |{_TABLE_STATUS_KEY}= on the wiki once.')


def update_league_table_status() -> None:
    if a_game_is_in_play():
        return
    rows = league_table(fetch_standings(_FOOTBALL_CO_IL_SEASON))

    league_table_template_page = pw.Page(site, _LEAGUE_TABLE_TEMPLATE_ON_MACCABIPEDIA)
    parsed_mw_text = mwparserfromhell.parse(league_table_template_page.text)
    table_template = next(template for template in parsed_mw_text.filter_templates(recursive=False)
                          if template.name.strip() == _TABLE_RENDERER)
    if table_template.has(_TABLE_STATUS_KEY):
        check_against_the_wiki(rows, games_played_on_the_wiki(str(table_template.get(_TABLE_STATUS_KEY).value)))

    league_table_data = ",\n".join(row.as_template_row() for row in rows)
    logging.info(f'Fetched league table data from football.co.il: {league_table_data}')
    table_template.add(_TABLE_STATUS_KEY, league_table_data)

    league_table_template_page.text = parsed_mw_text

    league_table_template_page.save(summary="MaccabiBot - Update league table")


if __name__ == '__main__':
    update_league_table_status()
