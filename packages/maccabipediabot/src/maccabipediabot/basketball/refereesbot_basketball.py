"""
Basketball Referees Bot
=======================
Creates a Maccabipedia page for each basketball referee who appears in the
Basketball_Games Cargo table (fields: MainReferee, AssistantReferees).

Page title format : כדורסל:NAME (שופט)
Template used     : {{שופט כדורסל |שם להצגה=NAME}}

How to run
----------
    source ~/.secrets && MACCABIPEDIA_UA_SCRIPT=gamesbot_basketball python -m maccabipediabot.basketball.refereesbot_basketball

Dependencies
------------
    pywikibot, requests  (see pyproject.toml)
"""

import logging
import sys

from maccabipediabot.common.maccabipedia_http import build_maccabipedia_session, parse_cargo_rows
from maccabipediabot.common.wiki_login import get_site

from maccabipediabot.common.logging_setup import setup_logging
setup_logging(level=logging.INFO)
logger = logging.getLogger(__name__)

CARGO_EXPORT_URL = (
    'https://www.maccabipedia.co.il/index.php'
    '?title=Special:CargoExport'
    '&tables=Basketball_Games'
    '&fields=MainReferee,AssistantReferees'
    '&format=json'
    '&limit=5000'
)

BASKETBALL_REFEREE_TEMPLATE = '{{{{שופט כדורסל |שם להצגה={name}}}}}'

SHOULD_SAVE = True

_session = build_maccabipedia_session()


def fetch_all_referee_names():
    """Query Cargo and return a sorted list of unique non-empty referee names."""
    resp = _session.get(CARGO_EXPORT_URL)

    resp.raise_for_status()

    rows = parse_cargo_rows(resp)
    names = set()

    for row in rows:
        main = row.get('MainReferee') or ''
        if main.strip():
            names.add(main.strip())

        assistants = row.get('AssistantReferees') or []
        if isinstance(assistants, str):
            assistants = [assistants]
        for name in assistants:
            if name and name.strip():
                names.add(name.strip())

    return sorted(names)


def page_title(referee_name):
    return f'כדורסל:{referee_name} (שופט)'


def create_referee_page(site, referee_name):
    import pywikibot as pw

    title = page_title(referee_name)
    page = pw.Page(site, title)

    if page.exists():
        logger.info('EXISTS   %s', title)
        return

    page.text = BASKETBALL_REFEREE_TEMPLATE.format(name=referee_name)
    logger.info('CREATING %s', title)

    if SHOULD_SAVE:
        page.save(summary='MaccabiBot - Add basketball referee page')
    else:
        logger.info('DRY RUN  — page text would be:\n%s', page.text)


def main():
    site = get_site()

    logger.info('Fetching referee names from Cargo...')
    referee_names = fetch_all_referee_names()
    logger.info('Found %d unique referee names', len(referee_names))

    for name in referee_names:
        create_referee_page(site, name)

    logger.info('Done.')


if __name__ == '__main__':
    main()
