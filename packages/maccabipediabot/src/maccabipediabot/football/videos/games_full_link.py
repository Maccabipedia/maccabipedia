import json
import logging
import sys
from maccabipediabot.common.paths import videos_dir
from maccabipediabot.common.page_names import build_football_game_page_name
from maccabipediabot.common.wiki_login import get_site

import pywikibot as pw
from maccabistats import get_maccabi_stats_as_newest_wrapper

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler(sys.stdout))

site = get_site()

UPLOAD_FULL_GAMES_LINKS = True
UPLOAD_HIGHLIGHTS_LINKS = True
REFRESH_PAGES = False
SHOULD_SAVE = True
SHOULD_SHOW_DIFF = True
SHOULD_CHECK_FOR_UPDATE_IN_EXISTING_PAGES = False



def get_games_to_add():
    maccabi_games = get_maccabi_stats_as_newest_wrapper()
    return maccabi_games


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

    return page_name


def find_game_by_season_and_fixture(g, unformatted_season, fixture):
    season = unformatted_season[:4] + "/" + unformatted_season[4:]

    possible_games = [gg for gg in g if gg.fixture == f"מחזור {fixture}" and gg.season == f"{season}"]

    if not possible_games:
        raise RuntimeError(f"Could not find any games at season: {season} and fixture: {fixture}")

    if len(possible_games) > 1:
        raise RuntimeError(f"Found {len(possible_games)} of possible games at season: {season} and fixture: {fixture}")

    return possible_games[0]


def get_full_game_links_json():
    with open(videos_dir() / 'full_games.json') as f:
        return json.load(f)


def get_highlights_links_json():
    with open(videos_dir() / 'highlights.json') as f:
        return json.load(f)


def add_param_to_game_page(page_name, param_name, param_value):
    page = pw.Page(site, page_name)

    if not page.exists():
        raise RuntimeError("Cannot find this page")

    replace_me = "גוף שידור="
    new_line_pipe = "|"
    add_me = f"{param_name}={param_value}"

    if f"{param_name}=" in page.text:
        raise RuntimeError(f"This game already has this param: {param_name}")

    # Something bad happen here when debugging page variable in pycharm watch window, dont expand 'page'
    without_link = page.text
    with_full_game_link = without_link.replace(replace_me, f"{replace_me} {new_line_pipe} {add_me}")

    page.text = with_full_game_link
    # Same stuff as above, dont debug this, pycharm evaluation destroy the internal state of the page object
    if "http" in page.text:
        page.save(summary="Adding full game link")


def main():
    logger.info("Should save : {save}".format(save=SHOULD_SAVE))
    logger.info("Should show diff: {diff}\n".format(diff=SHOULD_SHOW_DIFF))

    g = get_games_to_add()

    logger.info("Uploading full games links (just the league ones)")
    full_games_links = get_full_game_links_json()

    if UPLOAD_FULL_GAMES_LINKS:
        for season in full_games_links:
            for fixture in full_games_links[season]:
                full_game_link = full_games_links[season][fixture]
                try:
                    current_game = find_game_by_season_and_fixture(g, season, fixture)
                    current_page_name = generate_page_name_from_game(current_game)
                    add_param_to_game_page(current_page_name, "משחק מלא", full_game_link)
                except Exception as e:
                    print(e)
    else:
        logger.info("Do not upload full games links (by configuration")

    logger.info("Uploading highlights links (just the league ones)")
    highlights_links = get_highlights_links_json()

    if UPLOAD_HIGHLIGHTS_LINKS:
        for season in highlights_links:
            for fixture in highlights_links[season]:
                full_game_link = highlights_links[season][fixture]
                try:
                    current_game = find_game_by_season_and_fixture(g, season, fixture)
                    current_page_name = generate_page_name_from_game(current_game)
                    add_param_to_game_page(current_page_name, "תקציר וידאו", full_game_link)
                except Exception as e:
                    print(e)
    else:
        logger.info("Do not upload highlights links (by configuration")


if __name__ == '__main__':
    main()
