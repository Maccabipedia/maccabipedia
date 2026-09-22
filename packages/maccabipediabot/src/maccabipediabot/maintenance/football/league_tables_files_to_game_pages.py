import logging
import sys
from maccabipediabot.common.page_names import build_football_game_page_name
from maccabipediabot.common.wiki_login import get_site

import mwparserfromhell

import pywikibot as pw
from maccabistats import load_from_maccabipedia_source
from pywikibot import pagegenerators, Category, Page

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler(sys.stdout))

football_games_template_name = "קטלוג משחקים"
league_table_files_category_name = "קטגוריה:קטעי_עיתונות/טבלאות_ליגה"
league_table_file_argument_name = "טבלת ליגה"

maccabi_games = load_from_maccabipedia_source()

site = get_site()


def generate_page_name_from_game(game):
    """
    :type game: maccabistats.models.game_data.GameData
    :rtype: str
    """

    page_name = build_football_game_page_name(
        game_date=game.date,
        home_team=game.home_team.name,
        away_team=game.away_team.name,
        competition=game.competition,
    )

    page_name = page_name.replace('ביתר', 'בית"ר')  # Patch for now, we don't write beitar with ", as i should be.

    return page_name


def _get_word_after(text_to_search_in, word_before_wanted):
    for index, word in enumerate(text_to_search_in.split()):
        if word == word_before_wanted:
            # In case this word is the last word before the file extension
            return text_to_search_in.split()[index + 1].split(".")[0]

    raise RuntimeError(f"Cant find: {word_before_wanted} in '{text_to_search_in}'")


def extract_game_page_from_league_table_file(league_table_file_page):
    league_table_file_name = league_table_file_page.title()
    season = _get_word_after(league_table_file_name, "עונת").replace("-", "/")
    fixture_number = f'מחזור {_get_word_after(league_table_file_name, "מחזור")}'

    season_games = maccabi_games.get_games_by_season(season)
    game = [g for g in season_games if g.fixture == fixture_number]
    if len(game) != 1:
        raise RuntimeError(f"Too much matching games: {game}")

    game_page_name = generate_page_name_from_game(game[0])

    return Page(site, game_page_name)


def make_sure_league_table_file_is_on_game_page(league_table_file_page):
    game_page = extract_game_page_from_league_table_file(league_table_file_page)
    if not game_page.exists():
        raise RuntimeError(f"Could not find this game page: {game_page.title()}."
                           f"Created from this league table: {league_table_file_page.title()}")

    parsed_mw_text = mwparserfromhell.parse(game_page.text)
    football_game_template = parsed_mw_text.filter_templates(football_games_template_name)[0]

    table_arg_dont_exist = league_table_file_argument_name not in football_game_template
    # Contain just \n or spaces:
    empty_table_arg_exist = (league_table_file_argument_name in football_game_template) and not football_game_template.get(
        league_table_file_argument_name).value.strip()

    if table_arg_dont_exist or empty_table_arg_exist:
        logger.info(f"Adding league table file to the page: {game_page.title()}")
        football_game_template.add(league_table_file_argument_name, league_table_file_page.title(with_ns=False))

        game_page.text = parsed_mw_text
        game_page.save(summary="MaccabiBot - Updating league tables files to the relevant game pages", bot=True)

    else:
        # The current league table is a File (ns=6)
        current_league_table_file = Page(site, football_game_template.get(league_table_file_argument_name).value, ns=6)
        if current_league_table_file != league_table_file_page:
            logger.warning(f"Found an existing league table which is different from what we have."
                           f"Current: {current_league_table_file}, We have: {league_table_file_page}")
        else:
            logger.info(f"Page: {game_page.title()} has an existing league table and its a good one!")


def league_table_files():
    league_table_files_category = Category(site, league_table_files_category_name)
    return pagegenerators.CategorizedPageGenerator(league_table_files_category)


def update_league_table_files_in_game_pages():
    for league_table_file_page in league_table_files():
        try:
            make_sure_league_table_file_is_on_game_page(league_table_file_page)
        except Exception:
            logger.exception(f"Unhandled with: {league_table_file_page.title()}")


if __name__ == '__main__':
    update_league_table_files_in_game_pages()
