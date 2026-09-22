import logging
from maccabipediabot.common.wiki_login import get_site

import mwparserfromhell as mw
import pywikibot as pw
from pywikibot import pagegenerators

from maccabipediabot.common.maccabistats_player_event import PlayerEvent, SQUAD, CARDS_AND_SUBS, GOALS_INVOLVED

from maccabipediabot.common.logging_setup import setup_logging
setup_logging(level=logging.DEBUG)

site = get_site()

games_page_prefix = "משחק:"
games_template_name = "קטלוג משחקים"

SHOULD_SAVE = True
SHOULD_SHOW_DIFF = False


def iterate_games_pages():
    """
    :rtype: list of pywikibot.page.Page
    """
    iterate_only_over_these_games = set()
    # Uncomment the next line in order to iterate only on this page
    # iterate_only_over_these_games.add("משחק:16-09-2020 מכבי תל אביב נגד דינמו ברסט - מוקדמות ליגת האלופות")

    games_template_page = pw.Page(site, games_template_name, ns="תבנית")
    for index, game_page in enumerate(pagegenerators.ReferringPageGenerator(games_template_page)):
        logging.info(f"Page number: {index}")

        if not game_page.title().startswith(games_page_prefix):
            logging.debug(
                f"Skipping ({game_page.title()} with uses '{games_template_name}' but does not start with '{games_page_prefix}' prefix")
            continue

        if iterate_only_over_these_games:
            if game_page.title() in iterate_only_over_these_games:
                yield game_page
        else:
            yield game_page


def _save_page_changes(game_page, new_text):
    """
    :type game_page: pywikibot.page.Page
    :type new_text: str
    """
    if game_page.text == new_text:
        return

    if SHOULD_SHOW_DIFF:
        pw.showDiff(game_page.text, new_text)
    if not SHOULD_SAVE:
        logging.info(f"SHOULD_SAVE=False, dont saving changes for page: {game_page.title()}")
        return

    game_page.text = new_text
    game_page.save(summary="MaccabiBot - Sort players events", bot=True)


def matches_games_template(*args, **kwargs):
    return args[0].name.strip() == games_template_name


def sort_players_event_by_groups(players_event):
    """
    Sorts the players events by "groups", first "squad", then "subs & cards" and finally the rest.
    For each group, first we write maccabi events and after that the opponent events.
    :param players_event: All game events
    :type players_event: list of PlayerEvent
    :return: List of ordered events, each ordered events is list of events.
    :rtype: list of (list of PlayerEvent)
    """

    # Maccabi:
    unsorted_maccabi_squad_events = [e for e in players_event if e.event_type in SQUAD and e.maccabi_player]
    unsorted_maccabi_subs_and_cards_events = [e for e in players_event if
                                              e.event_type in CARDS_AND_SUBS and e.maccabi_player]
    unsorted_maccabi_goals_involved_events = [e for e in players_event if
                                              e.event_type in GOALS_INVOLVED and e.maccabi_player]

    # Opponent
    unsorted_opponent_squad_events = [e for e in players_event if e.event_type in SQUAD and not e.maccabi_player]
    unsorted_opponent_subs_and_cards_events = [e for e in players_event if
                                               e.event_type in CARDS_AND_SUBS and not e.maccabi_player]
    unsorted_opponent_goals_involved_events = [e for e in players_event if
                                               e.event_type in GOALS_INVOLVED and not e.maccabi_player]

    if len(unsorted_maccabi_squad_events) + len(unsorted_opponent_squad_events) + len(
            unsorted_maccabi_subs_and_cards_events) + len(
            unsorted_opponent_subs_and_cards_events) + len(unsorted_maccabi_goals_involved_events) + len(
        unsorted_opponent_goals_involved_events) != len(players_event):
        raise RuntimeError("We have missed some events!")

    unsorted_maccabi_squad_events.sort()
    unsorted_maccabi_subs_and_cards_events.sort()
    unsorted_maccabi_goals_involved_events.sort()

    unsorted_opponent_squad_events.sort()
    unsorted_opponent_subs_and_cards_events.sort()
    unsorted_opponent_goals_involved_events.sort()

    return (unsorted_maccabi_squad_events, unsorted_opponent_squad_events,
            unsorted_maccabi_subs_and_cards_events, unsorted_opponent_subs_and_cards_events,
            unsorted_maccabi_goals_involved_events, unsorted_opponent_goals_involved_events)


def sort_player_events_in_games_page(game_page):
    """
    :type game_page: pywikibot.page.Page
    """
    parsed_mw_text = mw.parse(game_page.text)
    templates = parsed_mw_text.filter_templates(matches=matches_games_template)
    if not templates:
        logging.warning(f"Found no game template in this page: {game_page.title()}")
        return

    game_template = templates[0]

    player_events_param = [param for param in game_template.params if str(param.name).strip() == "אירועי שחקנים"][0]
    if not str(player_events_param.value).strip():
        return  # Handle games without any player events (may be technical games at 50's).

    raw_players_events = str(player_events_param.value).split(",")

    player_events = [PlayerEvent.from_maccabipedia_format(raw_event) for raw_event in raw_players_events]
    sorted_grouped_events = sort_players_event_by_groups(player_events)

    # Need a "," between each two events (which means between each two groups also).
    # Skip empty groups so we wont have extra "," with no events near them
    raw_sorted_events = "\n,".join(
        (",".join(event.__maccabipedia__() for event in group_events) for group_events in sorted_grouped_events if
         group_events))
    player_events_param.value = f"\n{raw_sorted_events}\n"  # Start and end with newline, better visualize in the ui editor.

    _save_page_changes(game_page, parsed_mw_text)


def main():
    logging.info("Should save : {save}".format(save=SHOULD_SAVE))
    logging.info("Should show diff: {diff}\n".format(diff=SHOULD_SHOW_DIFF))

    logging.info("\nIterating all pages that uses football games template:")
    for game_page in iterate_games_pages():
        try:
            sort_player_events_in_games_page(game_page)
        except TypeError:
            logging.exception(f"Probably unknown event description, skipping this game: {game_page.title()}")
        except Exception:
            logging.exception(f"Unknown exception, skipping this game: {game_page.title()}")


if __name__ == '__main__':
    main()
