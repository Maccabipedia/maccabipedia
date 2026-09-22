import logging
from dataclasses import dataclass
from typing import Dict, Optional
from maccabipediabot.common.logging_setup import setup_logging
from maccabipediabot.common.wiki_login import get_site

import mwparserfromhell as mw
import pywikibot as pw

setup_logging(level=logging.DEBUG)

site = get_site()

games_template_name = "משחק כדורעף"

SHOULD_SAVE = True
SHOULD_SHOW_DIFF = False


@dataclass
class PlayerData:
    name: str
    score: Optional[int]
    shirt_number: Optional[int]

    def __str__(self):
        shirt_number = 'ללא-מספר' if self.shirt_number is None else self.shirt_number
        score = 'ללא-נקודות' if self.score is None else self.score

        return f'{self.name}::{shirt_number}::{score}'


def iterate_games_pages():
    """
    :rtype: list of pywikibot.page.Page
    """
    iterate_only_over_these_games = set()
    # Uncomment the next line in order to iterate only on this page
    # iterate_only_over_these_games.add("משחק:16-09-2020 מכבי תל אביב נגד דינמו ברסט - מוקדמות ליגת האלופות")

    games_template_page = pw.Page(site, games_template_name, ns="תבנית")
    for index, game_page in enumerate(games_template_page.getReferences(only_template_inclusion=True)):
        logging.info(f"Page number: {index}")

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


def extract_players_shirt_numbers(game_template) -> Dict[str, str]:
    all_players_numbers = {}
    if not game_template.has("סגל מכבי"):
        return all_players_numbers

    players_rows = game_template.get("סגל מכבי").split('\n')

    for player_row in players_rows:
        player_row = player_row.strip('').replace('{{ש}}', '')

        if not player_row.strip() or player_row.find('סגל מכבי') > -1:
            continue

        number = 'ללא-מספר'
        if player_row.find('.') != -1:
            number, player_row = player_row.split('.')
            player_row = player_row.strip()

        name = ''
        if player_row.find('[[כדורעף:') != -1:
            name = player_row.split('[[כדורעף:')[1].split('|')[0]
        else:
            name = player_row

        all_players_numbers[name] = number

    return all_players_numbers


def extract_players_scores(game_template) -> Dict[str, str]:
    all_players_scores = {}
    if not game_template.has("סיכום משחק"):
        return all_players_scores

    players_rows = game_template.get("סיכום משחק").split('\n')

    for player_row in players_rows:
        player_row = player_row.strip('').replace('{{ש}}', '')

        if not player_row.strip() or player_row.find('סיכום משחק') > -1 or player_row.find("נק'") == -1:
            continue

        score = 'ללא-נקודות'
        if player_row.find('-') != -1:
            player_row, score = player_row.split('-')
            player_row = player_row.strip()
            score = score.split('נק')[0].strip()

        name = ''
        if player_row.find('[[כדורעף:') != -1:
            name = player_row.split('[[כדורעף:')[1].split('|')[0]
        else:
            name = player_row.replace("#", "").strip()

        all_players_scores[name] = score

    return all_players_scores


def build_players_data(players_shirts_number: Dict[str, str], players_scores: Dict[str, str]):
    possible_players = set(list(players_shirts_number.keys()) + list(players_scores.keys()))

    return [PlayerData(name=player_name, score=players_scores.get(player_name),
                       shirt_number=players_shirts_number.get(player_name)) for player_name in possible_players]


def reorder_game_page(game_page):
    """
    :type game_page: pywikibot.page.Page
    """
    parsed_mw_text = mw.parse(game_page.text)
    templates = parsed_mw_text.filter_templates(matches=matches_games_template)
    if not templates:
        logging.warning(f"Found no game template in this page: {game_page.title()}")
        return

    game_template = templates[0]

    if not game_template.has('שחקנים מכבי'):
        logging.warning(f"Page hasn't the right maccabi players property: {game_page.title()}")
        return

    players_raw = game_template.get("שחקנים מכבי").value

    unordered_players = [item.replace(",", "") for item in players_raw.split("\n") if item]

    ordered_players = sorted(unordered_players,
                             key=lambda i: -1 if i.split("::")[1] == 'ללא-מספר' else int(i.split("::")[1]))

    final_players = "\n,".join(ordered_players)
    if final_players:
        final_players += "\n"

    game_template.add('שחקנים מכבי', final_players)

    if not SHOULD_SAVE:
        logging.info(f"SHOULD_SAVE=False, dont saving changes for page: {game_page.title()}")
        return

    if game_page.text == parsed_mw_text:
        logging.info('Page is the same, skipping')
        return

    game_page.text = parsed_mw_text
    game_page.save(summary="MaccabiPediaBot - Reordering volleyball players events", bot=True)


def main():
    logging.info("Should save : {save}".format(save=SHOULD_SAVE))
    logging.info("Should show diff: {diff}\n".format(diff=SHOULD_SHOW_DIFF))

    logging.info("\nIterating all pages that uses football games template:")
    for game_page in iterate_games_pages():
        try:
            reorder_game_page(game_page)
        except TypeError:
            logging.exception(f"Probably unknown event description, skipping this game: {game_page.title()}")
        except Exception:
            logging.exception(f"Unknown exception, skipping this game: {game_page.title()}")


if __name__ == '__main__':
    main()
