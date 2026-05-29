import base64
import logging
import os
from datetime import datetime
from typing import Dict, List

import requests
from dotenv import load_dotenv

from maccabipediabot.calendar.calendar_operations import fetch_games_from_calendar, update_event, upload_event, delete_event, Event
from maccabipediabot.calendar.google_calendar_api import initialize_global_google_service_account_from_memory_json
from maccabipediabot.calendar.maccabi_tlv_site import fetch_games_from_maccabi_tlv_site

_logger = logging.getLogger(__name__)

_SHOULD_PUBLISH_TO_BROTHER_1906_SITE = False
_BROTHER_1906_API_KEY = ''

SEASON_LINK_UNFORMATTED = 'https://www.maccabi-tlv.co.il/%d7%9e%d7%a9%d7%97%d7%a7%d7%99%d7%9d-%d7%95%d7%aa%d7%95%d7%a6%d7%90%d7%95%d7%aa/%d7%94%d7%a7%d7%91%d7%95%d7%a6%d7%94-%d7%94%d7%91%d7%95%d7%92%d7%a8%d7%aa/%d7%aa%d7%95%d7%a6%d7%90%d7%95%d7%aa/?season={season_number}#content'
UPCOMING_GAMES_LINK = 'https://www.maccabi-tlv.co.il/%d7%9e%d7%a9%d7%97%d7%a7%d7%99%d7%9d-%d7%95%d7%aa%d7%95%d7%a6%d7%90%d7%95%d7%aa/%d7%94%d7%a7%d7%91%d7%95%d7%a6%d7%94-%d7%94%d7%91%d7%95%d7%92%d7%a8%d7%aa/%d7%9c%d7%95%d7%97-%d7%9e%d7%a9%d7%97%d7%a7%d7%99%d7%9d/'

BROTHER_1906_SITE_URL = 'https://brothers1906.org/_functions/addGame'


def publish_event_to_brothers_1906_site(event: Dict) -> None:
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': _BROTHER_1906_API_KEY
    }

    body = {
        "gameId": base64.b64encode(event['extendedProperties']['shared']['url'].encode()).decode(),
        "title": event['summary'],
        "date_start": event['start']['dateTime'],
        "description": event['description'].split('\n')[0], # Take the content before maccabipedia link
        "location": event['location'] or 'N/A',
    }

    response = requests.post(url=BROTHER_1906_SITE_URL, headers=headers, json=body)
    response.raise_for_status()
    _logger.info(f"Published event to brothers1906 new event: {event['start']['dateTime']}")


def publish_new_event(event: Dict, calendar_id: str) -> None:
    _logger.info(f"Publishing new event: {event['summary']}")
    upload_event(event, calendar_id)

    if _SHOULD_PUBLISH_TO_BROTHER_1906_SITE:
        publish_event_to_brothers_1906_site(event)

def update_existing_event(event: Dict, event_id: str, calendar_id: str) -> None:
    _logger.info(f"Updating existing event: {event['summary']}")
    update_event(event, event_id, calendar_id)

    if _SHOULD_PUBLISH_TO_BROTHER_1906_SITE:
        publish_event_to_brothers_1906_site(event)


def delete_all_events(calendar_id: str) -> None:
    _logger.info("--- Deleting All Events: ---")
    events = fetch_games_from_calendar(calendar_id, '2011-10-10T10:10:10.644170Z')
    for event in events:
        _logger.info(f"Deleting event {event['summary']}")
        delete_event(event['id'], calendar_id)


def search_event_in_calendar(event: Dict, events_list: List) -> Dict:
    """
    Checking if the parsed game is exists in the calendar by comparing links to game page in the official site.
    If it is, return the existing event, else return empty

    :param event: event to search
    :param events_list: list of events to compare to
    :return: event or empty object
    """

    if events_list:
        for temp_event in events_list:
            if 'extendedProperties' in temp_event and 'extendedProperties' in event:
                if event['extendedProperties']['shared']['url'] == temp_event['extendedProperties']['shared']['url']:
                    if 'id' in temp_event:
                        return temp_event
                    else:
                        return event

    return {}


def sync_future_games_to_calendar(events_list: List[Event], curr_events_list: List[Event], calendar_id: str) -> None:
    _logger.info("--- Adding & Updating Events: ---")

    for event in events_list:
        curr_event = search_event_in_calendar(event, curr_events_list)
        if curr_event != {}:
            if event['summary'] != curr_event['summary'] or event['description'] != curr_event['description'] \
                    or event['start'] != curr_event['start'] or event['location'] != curr_event['location']:
                update_existing_event(event, curr_event['id'], calendar_id)
        else:
            publish_new_event(event, calendar_id)


def delete_unnecessary_events(events_list: List[Event], future_calendars_events: List[Event], calendar_id: str) -> None:
    """
    Deleting canceled/delayed/irrelevant events.
    Event which is in the calendar but not in the events list will be deleted
    """
    _logger.info("--- Deleting Events: ---")

    for event in future_calendars_events:
        exist_event = search_event_in_calendar(event, events_list)

        if exist_event == {}:
            _logger.info(f"Deleting event {event['summary']}")
            delete_event(event['id'], calendar_id)


def update_last_game(url: str, calendar_id: str) -> None:
    """
    Updating the last game result & adding link to game page at maccabipedia
    """

    _logger.info("--- Updating Last Game: ---")
    last_game = fetch_games_from_maccabi_tlv_site(url, to_update_last_game=True)[0]

    # At the end of a season the last played game has no event at/after it in the
    # calendar, so this query comes back empty. Skip rather than index into [].
    last_events = fetch_games_from_calendar(calendar_id, last_game['start']['dateTime'] + '+02:00', 1)
    if not last_events:
        _logger.info("No matching calendar event at/after the last game; skipping last-game update.")
        return
    last_event = last_events[0]

    if 'extendedProperties' in last_game and 'extendedProperties' in last_event:
        if last_game['extendedProperties']['shared']['url'] == last_event['extendedProperties']['shared']['url']:
            if last_event['extendedProperties']['shared']['result'] == '':
                update_existing_event(last_game, last_event['id'], calendar_id)


def add_history_games(seasons: List[str], calendar_id: str) -> None:
    """
    Loop over all past seasons URLs and adding the games to the calendar
    """

    for season in seasons:
        events = fetch_games_from_maccabi_tlv_site(season, to_update_last_game=False)
        for event in events:
            publish_event_to_brothers_1906_site(event, calendar_id)


def build_maccabi_tlv_site_seasons_links() -> List[str]:
    seasons_links = []

    _logger.info("Building season links")

    current_season_number = 74  # 2013/14
    while "המשחק האחרון" in requests.get(SEASON_LINK_UNFORMATTED.format(season_number=current_season_number)).text:
        seasons_links.append(SEASON_LINK_UNFORMATTED.format(season_number=current_season_number))
        _logger.info(f"Added new season: {current_season_number - 62}/{str(current_season_number - 61)[-2:]}")

        current_season_number += 1

    _logger.info(f"Finished to build season links, total seasons: {len(seasons_links)}")
    return seasons_links


def main(google_credentials: str, calendar_id: str):
    current_time = datetime.utcnow().isoformat() + 'Z'  # current datetime - to update and add upcoming games only

    initialize_global_google_service_account_from_memory_json(google_credentials)
    seasons = build_maccabi_tlv_site_seasons_links()

    future_calendars_events = fetch_games_from_calendar(calendar_id, fetch_after_this_time=current_time)
    upcoming_games_from_maccabi_tlv_site = fetch_games_from_maccabi_tlv_site(UPCOMING_GAMES_LINK,
                                                                             to_update_last_game=False)
    sync_future_games_to_calendar(upcoming_games_from_maccabi_tlv_site, future_calendars_events, calendar_id)
    delete_unnecessary_events(upcoming_games_from_maccabi_tlv_site, future_calendars_events, calendar_id)
    update_last_game(seasons[len(seasons) - 1], calendar_id)

    # Uncomment this in case you need to old games
    # add_history_games(seasons, calendar_id)


def entry_point() -> None:
    global _SHOULD_PUBLISH_TO_BROTHER_1906_SITE
    global _BROTHER_1906_API_KEY

    # noinspection PyBroadException
    try:
        logging.info("Starting!")
        load_dotenv()

        google_credentials = os.environ['GOOGLE_CREDENTIALS']
        calendar_id = os.environ['FOOTBALL_CALENDAR_ID']

        if 'SHOULD_PUBLISH_TO_BROTHER_1906_SITE' in os.environ:
            _SHOULD_PUBLISH_TO_BROTHER_1906_SITE = os.environ['SHOULD_PUBLISH_TO_BROTHER_1906_SITE'].lower() == 'true'
            _BROTHER_1906_API_KEY = os.environ.get('BROTHER_1906_API_KEY')
        else:
            _SHOULD_PUBLISH_TO_BROTHER_1906_SITE = False

        logging.info(f"Loaded environment variables successfully! "
                     f"Should publish to brother 1906 site?: {_SHOULD_PUBLISH_TO_BROTHER_1906_SITE}")

        main(google_credentials, calendar_id)
    except Exception:
        logging.exception(f"Unhandled exception (exiting the program): ")
        exit(1)


if __name__ == '__main__':
    from maccabipediabot.common.logging_setup import setup_logging
    setup_logging(level=logging.INFO)
    entry_point()
