import logging
import re
from datetime import timedelta
from typing import List

from maccabipediabot.common.wiki_login import get_site


import mwparserfromhell
import pywikibot as pw
from mwparserfromhell.nodes.template import Template
from pywikibot import pagegenerators, Category

site = get_site()

from maccabistats import get_maccabi_stats_as_newest_wrapper
from maccabistats.models.player_game_events import GameEventTypes
from maccabistats.stats.maccabi_games_stats import MaccabiGamesStats
from maccabipediabot.common.logging_setup import setup_logging
from maccabipediabot.common.page_names import build_football_game_page_name
from maccabipediabot.common.maccabistats_player_event import PlayerEvent
from maccabipediabot.common.prettify_games_pages import prettify_game_page_main_template
from maccabipediabot.football.sort_players_events import sort_player_events_in_games_page

setup_logging(level=logging.INFO)

football_games_prefix = "משחק"
football_games_template_name = "קטלוג משחקים"
football_games_category_name = "קטגוריה:משחקים"

# Legend games templates args consts:s
GAME_ID = "תאריך המשחק"
GAME_HOUR = "שעת המשחק"
SEASON = "עונה"
COMPETITION = "מפעל"
ROUND_IN_COMPETITION = "שלב במפעל"
OPPONENT_NAME = "שם יריבה"
HOME_OR_AWAY = "בית חוץ"
STADIUM = "אצטדיון"
MACCABI_RESULT = "תוצאת משחק מכבי"
OPPONENT_RESULT = "תוצאת משחק יריבה"
MACCABI_COACH = "מאמן מכבי"
OPPONENT_COACH = "מאמן יריבה"
REFEREE = "שופט ראשי"
REFEREE_ASSISTERS = "עוזרי שופט"
CROWD = "כמות קהל"
BROADCAST = "גוף שידור"
COSTUME = "מדים"
PLAYERS_EVENTS = "אירועי שחקנים"

REFRESH_PAGES = False
JUST_EVENTS = True
SHOULD_SAVE = True
SHOULD_SHOW_DIFF = True
SHOULD_CHECK_FOR_UPDATE_IN_EXISTING_PAGES = False
SHOULD_PURGE_RELATED_PAGES = True  # Purge related pages (opponent, players, coaches) after game uploads


def all_maccabi_games():
    maccabi_games = get_maccabi_stats_as_newest_wrapper()
    return maccabi_games


def get_football_games_template_arguments():
    legend_games_template_page = pw.Page(site, football_games_template_name)
    legend_games_template_text = mwparserfromhell.parse(legend_games_template_page.text)
    return legend_games_template_text.filter_arguments()


def get_all_football_games_category_pages():
    games_category = Category(site, football_games_category_name)
    games_category = list(pagegenerators.CategorizedPageGenerator(games_category))
    return games_category


def get_football_games_template_object():
    return Template(football_games_template_name)


def generate_page_name_from_game(game):
    """
    :type game: maccabistats.models.game_data.GameData
    :rtype: str
    """
    return build_football_game_page_name(
        game_date=game.date,
        home_team=game.home_team.name,
        away_team=game.away_team.name,
        competition=game.competition,
    )


def get_players_events_for_template(game):
    """
    Return the events as they should be written to template:
    the separator between players attributes is '::'
    the separator between players is ','
    :type game: maccabistats.models.game_data.GameData
    :return:
    """

    # Atm, no sub event type is supported.
    # Bench event type is added for players who doesnt has line-up event.

    # Maccabi players
    unsorted_events = [
        PlayerEvent.from_maccabistats_event_type(player.name, player.number, player_event.time_occur,
                                                 player_event.event_type,
                                                 getattr(player_event, "goal_type", None), maccabi_player=True)
        for player in game.maccabi_team.players
        for player_event in player.events]

    # Maccabi players that not played
    unsorted_events.extend(
        [PlayerEvent.from_maccabistats_event_type(player.name, player.number, timedelta(minutes=0),
                                                  GameEventTypes.BENCHED, None, maccabi_player=True)
         for player in game.maccabi_team.players if not player.has_event_type(GameEventTypes.LINE_UP)]
    )

    # Opponent players
    unsorted_events.extend(
        [PlayerEvent.from_maccabistats_event_type(player.name, player.number, player_event.time_occur,
                                                  player_event.event_type,
                                                  getattr(player_event, "goal_type", None), maccabi_player=False)
         for player in game.not_maccabi_team.players
         for player_event in player.events])

    # Opponent players that not played
    unsorted_events.extend(
        [PlayerEvent.from_maccabistats_event_type(player.name, player.number, timedelta(minutes=0),
                                                  GameEventTypes.BENCHED, None,
                                                  maccabi_player=False)
         for player in game.not_maccabi_team.players if not player.has_event_type(GameEventTypes.LINE_UP)]
    )

    events = sorted(unsorted_events, key=lambda player_event: player_event.minute_occur)

    # Remove the last new line
    wikimedia_formatted_events = ",".join(player_event.__maccabipedia__() for player_event in events).rstrip()

    return wikimedia_formatted_events


def __get_football_game_template_with_maccabistats_game_value(game):
    """
    Return dict of the (template arguments->data taken from game).
    :type game: maccabistats.models.game_data.GameData
    :return: dict from str to str
    """

    template_arguments = dict()

    template_arguments[GAME_ID] = str(game.date.strftime("%d-%m-%Y"))
    # We don't want to upload the hour if it's equal to zero (that an unknown time)
    template_arguments[GAME_HOUR] = game.date.hour if game.date.hour != 0 else ''

    template_arguments[SEASON] = game.season
    template_arguments[COMPETITION] = game.competition
    template_arguments[
        ROUND_IN_COMPETITION] = "" if game.fixture == "No round found" else game.fixture  # Empty for unknown rounds
    template_arguments[OPPONENT_NAME] = game.not_maccabi_team.name
    template_arguments[HOME_OR_AWAY] = "בית" if game.is_maccabi_home_team else "חוץ"
    template_arguments[STADIUM] = game.stadium
    template_arguments[MACCABI_RESULT] = game.maccabi_team.score
    template_arguments[OPPONENT_RESULT] = game.not_maccabi_team.score
    template_arguments[MACCABI_COACH] = "" if game.maccabi_team.coach == "Cant found coach" else game.maccabi_team.coach
    template_arguments[
        OPPONENT_COACH] = "" if game.not_maccabi_team.coach == "Cant found coach" else game.not_maccabi_team.coach
    template_arguments[REFEREE] = "" if game.referee == "Cant found referee" else game.referee
    template_arguments[REFEREE_ASSISTERS] = ""
    template_arguments[CROWD] = "" if game.crowd == "Cant found crowd" else game.crowd
    template_arguments[BROADCAST] = ""
    template_arguments[COSTUME] = ""
    template_arguments[PLAYERS_EVENTS] = get_players_events_for_template(game)

    return template_arguments


def handle_existing_page(game_page, game):
    """
    :type game_page: pywikibot.page.Page
    :type game: maccabistats.models.game_data.GameData
    """

    if JUST_EVENTS:
        parsed_mw_text = mwparserfromhell.parse(game_page.text)
        football_game_template = parsed_mw_text.filter_templates(football_games_template_name)[0]

        arguments = __get_football_game_template_with_maccabistats_game_value(game)

        football_game_template.add(PLAYERS_EVENTS, arguments[PLAYERS_EVENTS])

        game_page.text = parsed_mw_text

    else:
        parsed_mw_text = mwparserfromhell.parse(game_page.text)
        football_game_template = parsed_mw_text.filter_templates(football_games_template_name)[0]

        arguments = __get_football_game_template_with_maccabistats_game_value(game)

        for argument_name, argument_value in arguments.items():
            if str(argument_value) != football_game_template.get(argument_name).value and SHOULD_SHOW_DIFF:
                logging.info("Found diff between arguments on this argument_name: {arg_name}\n"
                             "existing value: {existing_value}\nnew_value: {new_value}".
                             format(arg_name=argument_name,
                                    existing_value=football_game_template.get(argument_name).value,
                                    new_value=argument_value))

                football_game_template.add(argument_name, argument_value)

        game_page.text = parsed_mw_text

        if REFRESH_PAGES:
            from random import randint
            game_page.text += "<!--{num}-->".format(num=randint(0, 10000))


def handle_new_page(game_page, game):
    """
    :type game_page: pywikibot.page.Page
    :type game: maccabistats.models.game_data.GameData
    """

    football_game_template = get_football_games_template_object()

    arguments = __get_football_game_template_with_maccabistats_game_value(game)

    for argument_name, argument_value in arguments.items():
        football_game_template.add(argument_name, argument_value)

    game_page.text = str(football_game_template)


def create_or_update_game_page(game, overwrite_existing_pages: bool = True) -> bool:
    """Returns True if the page was saved, False if skipped."""
    logging.info(f"create_or_update_game_page : {game}")

    page_name = generate_page_name_from_game(game)

    game_page = pw.Page(site, page_name)

    # handle_new_page & handle_existing_page changes the game_page.text attribute.
    if game_page.exists():
        if not overwrite_existing_pages:
            logging.info(f"Don't edit existing pages, skipping: {page_name}")
            return False

        logging.info("Page : {name} exists, check for updates\n".format(name=page_name))
        handle_existing_page(game_page, game)
    else:
        logging.info("Page : {name} does not exists, creating\n".format(name=page_name))
        handle_new_page(game_page, game)

    logging.info("")  # Empty line
    if SHOULD_SAVE:
        logging.info("Saving {name}".format(name=game_page.title()))
        game_page.save(summary="MaccabiBot - Uploading Games")

        logging.info(f"Prettifying {game_page.title()}")
        prettify_game_page_main_template(game_page)

        logging.info(f"Sorting events {game_page.title()}")
        sort_player_events_in_games_page(game_page)
    else:
        logging.info("Not saving {name}".format(name=game_page.title()))

    return True


def get_games_that_has_existing_pages(games: List[str]):
    existing_games = []
    existing_games_pages = get_all_football_games_category_pages()
    for game_page in existing_games_pages:
        game_date_match = re.search("([0-9]{2}\-[0-9]{2}\-[0-9]{4})", game_page.title())
        if game_date_match is None:
            logging.warning("Found game page title without date, skipping this page, wtf?? - {title}".format(
                title=game_page.title()))
            continue
        game_date = game_date_match.group()
        game_date = game_date.replace("-", ".")  # For maccabistats format played(before\after).

        game = games.played_before(game_date).played_after(game_date)
        if len(game) > 1:
            raise RuntimeError("found more than one game for {date}".format(date=game_date))
        existing_games.append(game[0])

    return existing_games


def collect_related_pages_from_game(game) -> set[str]:
    """Collect all pages that should be purged after this game is uploaded."""
    pages_to_purge = set()

    pages_to_purge.add(game.not_maccabi_team.name)

    # Player pages live in the main namespace (no prefix)
    for player in game.maccabi_team.players:
        if player.name:
            pages_to_purge.add(player.name)

    if game.maccabi_team.coach and game.maccabi_team.coach != "Cant found coach":
        pages_to_purge.add(game.maccabi_team.coach)

    if game.not_maccabi_team.coach and game.not_maccabi_team.coach != "Cant found coach":
        pages_to_purge.add(game.not_maccabi_team.coach)

    if game.season:
        pages_to_purge.add(f"עונת {game.season}")

    if game.competition:
        pages_to_purge.add(game.competition)

    if game.referee and game.referee != "Cant found referee":
        pages_to_purge.add(game.referee)

    if game.stadium:
        pages_to_purge.add(game.stadium)

    return pages_to_purge


def purge_pages_batch(pages_to_purge: set[str]) -> None:
    """Purge a batch of pages efficiently."""
    if not pages_to_purge:
        return

    logging.info(f"Purging {len(pages_to_purge)} unique related pages...")
    results = {"purged": 0, "skipped": 0, "failed": 0}

    for page_name in sorted(pages_to_purge):
        try:
            page = pw.Page(site, page_name)
            if page.exists():
                logging.debug(f"Purging: {page_name}")
                page.purge(forcelinkupdate=True)
                results["purged"] += 1
            else:
                logging.debug(f"Page doesn't exist, skipping: {page_name}")
                results["skipped"] += 1
        except Exception as e:
            logging.warning(f"Failed to purge {page_name}: {e}")
            results["failed"] += 1

    logging.info(f"Purge complete: {results['purged']} purged, {results['skipped']} skipped, {results['failed']} failed")


def upload_games_to_maccabipedia(maccabi_games_to_add: MaccabiGamesStats):
    logging.info("")  # Empty line

    logging.info("Should save : {save}".format(save=SHOULD_SAVE))
    logging.info("Should show diff: {diff}\n".format(diff=SHOULD_SHOW_DIFF))

    # Collect pages to purge across all games
    all_pages_to_purge = set()

    for game in maccabi_games_to_add:
        was_saved = create_or_update_game_page(game, overwrite_existing_pages=False)
        if was_saved:
            pages_from_game = collect_related_pages_from_game(game)
            all_pages_to_purge.update(pages_from_game)

    logging.info("Finished adding new games.")

    # The main page shows the latest 5 games list, and the players portal shows
    # the top scorers/assisters leaderboards, so purge them too
    if all_pages_to_purge:
        all_pages_to_purge.add("עמוד ראשי")
        all_pages_to_purge.add("פורטל שחקנים")

    # Batch purge all collected pages at the end
    if SHOULD_SAVE and SHOULD_PURGE_RELATED_PAGES:
        purge_pages_batch(all_pages_to_purge)

    if SHOULD_CHECK_FOR_UPDATE_IN_EXISTING_PAGES:
        logging.info("Now handling existing games:")
        existing_games = get_games_that_has_existing_pages(maccabi_games_to_add.games)

        for game in existing_games:
            create_or_update_game_page(game)
            pages_from_game = collect_related_pages_from_game(game)
            all_pages_to_purge.update(pages_from_game)

        # Purge again if we updated existing games
        if SHOULD_SAVE and SHOULD_PURGE_RELATED_PAGES:
            purge_pages_batch(all_pages_to_purge)
    else:
        logging.info("Don't check for updates in existing pages")

    logging.info("Finished handling existing games.")


if __name__ == '__main__':
    upload_games_to_maccabipedia(all_maccabi_games())
