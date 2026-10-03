import logging
import subprocess
from datetime import datetime
from logging import FileHandler
from pathlib import Path

from maccabistats import load_from_maccabipedia_source, ErrorsFinder
from maccabistats.maccabilogging import remove_live_logging
from maccabistats.stats.maccabi_games_stats import MaccabiGamesStats


def _get_repo_root() -> Path:
    return Path(subprocess.check_output(
        ['git', 'rev-parse', '--show-toplevel'], text=True
    ).strip())

logging.basicConfig(format='%(message)s', level=logging.INFO)


def show_double_league_fixtures(errors_finder: ErrorsFinder) -> None:
    problematic_games = errors_finder.get_double_league_games_fixtures()
    if not problematic_games:
        return

    logging.info(f'\nLeague games with the same season and fixture:')
    for fixture_and_season, maccabi_games_stats in problematic_games:
        logging.info(f'    {fixture_and_season}: {maccabi_games_stats.games}')


def show_games_with_difference_between_the_score_and_goals_amount(errors_finder: ErrorsFinder) -> None:
    problematic_games = errors_finder.get_games_with_wrong_goals_team_belonging()
    if not problematic_games:
        return

    logging.info(f'\nGames with wrong team goals belonging:')
    for game in problematic_games:
        logging.info(f'    {game}')


def show_games_with_missing_goals_events(errors_finder: ErrorsFinder) -> None:
    problematic_games = errors_finder.get_games_with_missing_goals_events()
    if not problematic_games:
        return

    logging.info(f'\nGames with missing goals events:')
    for game in problematic_games:
        logging.info(f'    {game}')


def show_games_with_incorrect_seasons(errors_finder: ErrorsFinder) -> None:
    problematic_games = errors_finder.get_games_with_incorrect_season()
    if not problematic_games:
        return

    logging.info(f'\nGames with incorrect season:')
    for record in problematic_games:
        logging.info(f'    {record}')


def show_games_without_11_lineup_players(errors_finder: ErrorsFinder) -> None:
    problematic_games = errors_finder.get_games_without_11_maccabi_players_on_lineup()
    if not problematic_games:
        return

    logging.info(f'\nGames without 11 players on lineup:')
    for game in problematic_games:
        logging.info(f'    {game}')


def show_players_that_start_the_game_and_have_sub_in_event(errors_finder: ErrorsFinder) -> None:
    problematic_players = errors_finder.get_lineup_players_with_substitution_in()
    if not problematic_players:
        return

    logging.info(f'\nPlayers that start the game and have sub-in event:')
    for player_record in problematic_players:
        logging.info(f'    Player: {player_record[0].name}, Game: {player_record[1]}')


def show_players_with_unknown_events(errors_finder: ErrorsFinder) -> None:
    problematic_players = errors_finder.get_players_with_unknown_events()
    if not problematic_players:
        return

    logging.info(f'\nPlayers with an unrecognized event:')
    for player_record in problematic_players:
        logging.info(
            f'    Player: {player_record[0].name}, Events: {player_record[0].events}, Game: {player_record[1]}')


def show_errors_for_maccabi_games(maccabi_games: MaccabiGamesStats) -> None:
    logging.info(f"Showing errors for: {maccabi_games}:\n")
    maccabipedia_errors_finder = ErrorsFinder(maccabi_games)

    show_double_league_fixtures(maccabipedia_errors_finder)
    show_games_with_difference_between_the_score_and_goals_amount(maccabipedia_errors_finder)
    show_games_with_missing_goals_events(maccabipedia_errors_finder)
    show_games_with_incorrect_seasons(maccabipedia_errors_finder)
    show_games_without_11_lineup_players(maccabipedia_errors_finder)

    show_players_that_start_the_game_and_have_sub_in_event(maccabipedia_errors_finder)
    show_players_with_unknown_events(maccabipedia_errors_finder)


def show_all_errors() -> None:
    remove_live_logging()

    root_folder = _get_repo_root()
    base_log_file_name = root_folder / f'{datetime.now().strftime("%Y_%m_%d")}__maccabipedia_errors'

    logging.info('Loading MaccabiPedia games, official games only, no friendly games')
    maccabipedia_games = load_from_maccabipedia_source().official_games
    logging.info(f'Loaded MaccabiPedia games: {maccabipedia_games}')

    # Full dates on purpose: a bare year like "1950" is parsed with today's month and day, so the split
    # would drift every day and the games between the two cut-offs would never be checked at all.
    old_games_file_handler = FileHandler(f'{base_log_file_name}_before_1950.txt', encoding='utf8')
    logging.getLogger().addHandler(old_games_file_handler)
    show_errors_for_maccabi_games(maccabipedia_games.played_before("1950-12-31"))
    logging.getLogger().removeHandler(old_games_file_handler)

    new_games_file_handler = FileHandler(f'{base_log_file_name}_after_1950.txt', encoding='utf8')
    logging.getLogger().addHandler(new_games_file_handler)
    show_errors_for_maccabi_games(maccabipedia_games.played_after("1951-01-01"))
    logging.getLogger().removeHandler(new_games_file_handler)

    logging.info('\n\nFinished to find errors from MaccabiPedia')


if __name__ == '__main__':
    show_all_errors()
