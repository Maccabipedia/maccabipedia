import logging
from dataclasses import dataclass

import mwparserfromhell
import pandas as pd
import requests

import sys, requests, ssl

print("Python version:", sys.version)
print("Requests version:", requests.__version__)
print("SSL version:", ssl.OPENSSL_VERSION)

from maccabipediabot.common.wiki_login import get_site
from maccabipediabot.volleyball.volleyball_common import TEAM_NAMES_REPLACER

# Local overrides for team names mapping. Use the original team name string from the IVA
# table as the key and the desired modified name as the value. If a team name is not
# present in either this local dict or the imported TEAM_NAMES_REPLACER, the original
# name will be used unchanged.
# Example:
# LOCAL_TEAM_NAMES_REPLACER = {
#     'מכבי תל אביב': 'מכבי ת"א',
# }
LOCAL_TEAM_NAMES_REPLACER = {
    # put entries here as 'original_team_name': 'modified_team_name'
}

LEAGUE_TABLE_TEMPLATE_ON_MACCABIPEDIA = 'תבנית:טבלת ליגת כדורעף 2026/27'
_TABLE_STATUS_KEY = 'טבלה'

IVA_LEAGUE_TABLE_URL = 'https://iva.org.il/league/?LeagueId=eaOcdd&cYear=2027'

from maccabipediabot.common.logging_setup import setup_logging
setup_logging(level=logging.DEBUG)

# We need to log before we run any of our maccabipedia (pywikibot or it's import) related code
site = get_site()

import pywikibot as pw


@dataclass
class VolleyballTableTeamRecord:
    name: str
    games: int
    wins: int
    losses: int
    points_in_game_for: int
    points_in_game_against: int
    sets_for: int
    sets_against: int
    points: int

    def adapt_to_mediawiki_code(self) -> str:
        return '^'.join(
            str(o) for o in
            [self.name, self.games, self.wins, self.losses, self.points_in_game_for, self.points_in_game_against,
             self.sets_for, self.sets_against, self.points])


def parse_team_record(raw_team_record: pd.Series) -> VolleyballTableTeamRecord:
    # Try to find the correct column names - they may vary depending on how the HTML table is formatted
    # Looking for columns that contain these patterns
    def find_column(series, patterns):
        """Find a column by checking if column name matches any of the patterns.
        Prefer exact match, then substring match."""
        # First try exact matches
        for pattern in patterns:
            for col in series.index:
                if str(col).strip() == pattern:
                    return series[col]
        # Then try substring matches
        for pattern in patterns:
            for col in series.index:
                if pattern in str(col):
                    return series[col]
        # If still not found, log all available columns and raise error
        logging.error(f"Column not found. Patterns sought: {patterns}")
        logging.error(f"Available columns: {list(series.index)}")
        raise KeyError(f"Column not found. Patterns: {patterns}, Available: {list(series.index)}")
    
    team_name = raw_team_record['קבוצה']  # This should be consistent
    # Be more flexible with column name patterns - handle different quote types
    games = find_column(raw_team_record, ["מש", "משחקים", "games"])
    wins = find_column(raw_team_record, ["נצ", "נצחונות", "wins"])
    losses = find_column(raw_team_record, ["הפ", "הפסדים", "losses"])
    points_str = find_column(raw_team_record, ["סה", "סה כ נקודות", "סה כ נקודות"])
    
    # Handle splitting with better error handling
    points_parts = str(points_str).split("-")
    if len(points_parts) == 2:
        points_in_game_against, points_in_game_for = points_parts
    else:
        logging.warning(f"Points string '{points_str}' doesn't have expected format (expected 'X-Y'). Available: {points_parts}")
        points_in_game_against = points_parts[0] if points_parts else 0
        points_in_game_for = points_parts[1] if len(points_parts) > 1 else 0
    
    sets_str = find_column(raw_team_record, ["סטים", "sets"])
    logging.debug(f"Sets string value: '{sets_str}'")
    
    sets_parts = str(sets_str).split("-")
    if len(sets_parts) == 2:
        sets_against, sets_for = sets_parts
    else:
        logging.warning(f"Sets string '{sets_str}' doesn't have expected format (expected 'X-Y'). Available: {sets_parts}")
        sets_against = sets_parts[0] if sets_parts else 0
        sets_for = sets_parts[1] if len(sets_parts) > 1 else 0
    
    points = raw_team_record["נקודות"]
    return VolleyballTableTeamRecord(name=team_name, games=games, wins=wins, losses=losses,
                                     points_in_game_for=points_in_game_for,
                                     points_in_game_against=points_in_game_against, sets_for=sets_for,
                                     sets_against=sets_against, points=points)


def fetch_league_data_from_iva():
    iva_league_table_page_response = requests.get(IVA_LEAGUE_TABLE_URL, verify=False)

    tables = pd.read_html(iva_league_table_page_response.content)
    volleyball_league_table = tables[0]

    # Debug: Log the actual columns for troubleshooting
    logging.info(f"Fetched table columns: {list(volleyball_league_table.columns)}")
    logging.info(f"Table shape: {volleyball_league_table.shape}")

    parsed_team_records = []
    for raw_table_team_record in volleyball_league_table.iterrows():
        parsed_team_records.append(parse_team_record(raw_table_team_record[1]))

    # Merge the global replacer with local overrides; local overrides take precedence.
    merged_replacer = {**TEAM_NAMES_REPLACER, **LOCAL_TEAM_NAMES_REPLACER}

    for team_record in parsed_team_records:
        team_record.name = merged_replacer.get(team_record.name, team_record.name)

    aggregated_record_to_be_filled_in_table_template_key = ",\n".join(
        team_record.adapt_to_mediawiki_code() for team_record in parsed_team_records)

    logging.info(
        f'Finished to build wikicode for volleyball league table: {aggregated_record_to_be_filled_in_table_template_key}')
    return aggregated_record_to_be_filled_in_table_template_key


def update_volleyball_league_table_template() -> None:
    logging.info(f'Fetching league table template page: {LEAGUE_TABLE_TEMPLATE_ON_MACCABIPEDIA} '
                 f'from url: {IVA_LEAGUE_TABLE_URL}')
    league_table_data = fetch_league_data_from_iva()

    league_table_template_page = pw.Page(site, LEAGUE_TABLE_TEMPLATE_ON_MACCABIPEDIA)

    parsed_mw_text = mwparserfromhell.parse(league_table_template_page.text)
    table_template = parsed_mw_text.filter_templates(LEAGUE_TABLE_TEMPLATE_ON_MACCABIPEDIA)[0]
    table_template.add(_TABLE_STATUS_KEY, league_table_data)

    league_table_template_page.text = parsed_mw_text

    league_table_template_page.save(summary="MaccabiBot - Update Volleyball league table")

    logging.info('Finished to save league table!')


if __name__ == '__main__':
    update_volleyball_league_table_template()
