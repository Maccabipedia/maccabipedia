"""
Upload basketball poster images to Maccabipedia.

For each poster file in the input folder, the script:
  1. Extracts the game date from the filename (expects DD-MM-YYYY format).
  2. Queries the Maccabipedia Cargo API to find the matching basketball game page.
  3. Uploads the file to Maccabipedia with the template {{תיוג כרזת כדורסל|משחק=PAGE_NAME}}.

After processing, each file is moved to one of three sub-folders:
  - passed/    : successfully uploaded
  - duplicate/ : file already existed on Maccabipedia (skipped)
  - failed/    : any error occurred

Usage:
    source ~/.secrets && MACCABIPEDIA_UA_SCRIPT=gamesbot_basketball python upload_basketball_posters.py
    source ~/.secrets && MACCABIPEDIA_UA_SCRIPT=gamesbot_basketball python upload_basketball_posters.py --dry-run

Dependencies:
    pywikibot, requests

Configuration:
    Set POSTERS_BASE_FOLDER to the batch folder containing the 'input' sub-folder.
"""

import argparse
import logging
import re
import requests
from pathlib import Path
from datetime import datetime
import contextlib

from maccabipediabot.common.logging_setup import setup_logging
from maccabipediabot.common.maccabipedia_http import MACCABIPEDIA_JSON_HEADERS, build_maccabipedia_session, parse_cargo_rows
from maccabipediabot.common.wiki_login import get_site
import pywikibot as pw
from pywikibot.comms import http as pw_http

setup_logging(level=logging.INFO)
logger = logging.getLogger(__name__)

# Connect to maccabipedia
site = get_site()

_session = build_maccabipedia_session()

API_URL = 'https://www.maccabipedia.co.il/api.php'

# Configuration
POSTERS_BASE_FOLDER = Path("/mnt/c/maccabipedia/automations/basketball-posters-03-2026")

TEMPLATE_NAME = "תיוג כרזת כדורסל"
TEMPLATE_PARAM_GAME_NAME = "משחק="

SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png'}


def _input_folder() -> Path:
    return POSTERS_BASE_FOLDER / 'input'


def _passed_folder() -> Path:
    return POSTERS_BASE_FOLDER / 'passed'


def _failed_folder() -> Path:
    return POSTERS_BASE_FOLDER / 'failed'


def _duplicate_folder() -> Path:
    return POSTERS_BASE_FOLDER / 'duplicate'


def _ensure_folders_exist() -> None:
    for folder in [_input_folder(), _passed_folder(), _failed_folder(), _duplicate_folder()]:
        folder.mkdir(parents=True, exist_ok=True)


def _extract_date_from_filename(filename: str) -> datetime:
    """
    Extracts date from filename using common formats (DD-MM-YYYY, DD.MM.YYYY, YYYY-MM-DD).
    """
    dates_found = re.findall(r'\d{2}-\d{2}-\d{4}|\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2}', filename)
    if not dates_found:
        raise ValueError(f"Could not find any date in filename: {filename}")

    date_str = dates_found[0]
    formats = ['%d-%m-%Y', '%d.%m.%Y', '%Y-%m-%d']

    for date_format in formats:
        with contextlib.suppress(ValueError):
            return datetime.strptime(date_str, date_format)

    raise ValueError(f"Could not parse date '{date_str}' from filename: {filename}")


def _get_game_page_name(game_date: datetime) -> str:
    """
    Queries Maccabipedia Cargo API to find the basketball game matching the given date.
    Returns the page name of the game.
    """
    formatted_date = game_date.strftime('%Y-%m-%d')
    url = (
        f"https://www.maccabipedia.co.il/index.php?title=Special:CargoExport"
        f"&format=json&tables=Basketball_Games&fields=_pageName"
        f"&where=Basketball_Games.Date='{formatted_date}'"
    )

    response = _session.get(url)
    response.raise_for_status()

    data = parse_cargo_rows(response)

    if not data:
        raise ValueError(f"No basketball game found for date: {formatted_date}")
    if len(data) > 1:
        raise ValueError(
            f"Multiple basketball games found for date {formatted_date}: "
            f"{[d['_pageName'] for d in data]}"
        )

    return data[0]['_pageName']


def _upload_file_via_requests(poster_file: Path, text: str) -> None:
    """
    Uploads a file to Maccabipedia using requests directly.
    Bypasses pywikibot's MIME multipart builder which produces headers
    (MIME-Version: 1.0 per part) that Apache rejects with 400 Bad Request.
    Uses pywikibot's session cookies and CSRF token.
    """
    csrf_token = site.tokens['csrf']
    cookies = {c.name: c.value for c in pw_http.cookie_jar if 'maccabipedia' in (c.domain or '')}
    ua = site._http_session.headers.get('User-Agent', '') if hasattr(site, '_http_session') else ''
    if not ua:
        import os
        script = os.environ.get('MACCABIPEDIA_UA_SCRIPT', 'upload_basketball_posters')
        ua = f'{script} (maccabipedia:he; User:{site.user()}) Pywikibot/9.6.0'

    with open(poster_file, 'rb') as f:
        file_data = f.read()

    mime_type = 'image/jpeg' if poster_file.suffix.lower() in {'.jpg', '.jpeg'} else 'image/png'
    response = requests.post(
        API_URL,
        data={
            'action': 'upload',
            'filename': poster_file.name,
            'comment': 'העלאת כרזת משחק כדורסל',
            'text': text,
            'token': csrf_token,
            'ignorewarnings': '1',
            'format': 'json',
        },
        files={'file': ('FAKE-NAME', file_data, mime_type)},
        cookies=cookies,
        headers={'User-Agent': ua, **MACCABIPEDIA_JSON_HEADERS},
    )

    if 'application/json' not in response.headers.get('Content-Type', ''):
        raise RuntimeError(f"Upload failed with non-JSON response (status {response.status_code}): {response.text[:300]}")

    result = response.json()
    if 'error' in result:
        raise RuntimeError(f"Upload API error: {result['error']}")
    if result.get('upload', {}).get('result') != 'Success':
        raise RuntimeError(f"Unexpected upload result: {result}")


def upload_poster(poster_file: Path, dry_run: bool = False) -> None:
    """
    Uploads a single poster file to Maccabipedia and moves it to the appropriate sub-folder.
    """
    logger.info(f"Processing poster file: {poster_file.name}")

    try:
        game_date = _extract_date_from_filename(poster_file.stem)
        try:
            page_name = _get_game_page_name(game_date)
            logger.info(f"Matched game date {game_date.strftime('%d-%m-%Y')} to game page: {page_name}")
            template_text = f"{{{{{TEMPLATE_NAME}|{TEMPLATE_PARAM_GAME_NAME}{page_name}}}}}"
        except ValueError:
            logger.warning(f"No game page found for {game_date.strftime('%d-%m-%Y')} — uploading without משחק= param.")
            template_text = f"{{{{{TEMPLATE_NAME}}}}}"

        file_page = pw.FilePage(site, poster_file.name)
        if file_page.exists():
            logger.info(f"File {poster_file.name} already exists on Maccabipedia. Moving to duplicate.")
            poster_file.rename(_duplicate_folder() / poster_file.name)
            return

        if not dry_run:
            _upload_file_via_requests(poster_file, template_text)
            logger.info(f"Successfully uploaded: {poster_file.name}")
            poster_file.rename(_passed_folder() / poster_file.name)
        else:
            logger.info(f"[DRY RUN] Would upload: {poster_file.name} with template: {template_text}")

    except Exception as e:
        logger.error(f"Failed to process {poster_file.name}: {e}")
        if not dry_run:
            poster_file.rename(_failed_folder() / poster_file.name)


def upload_all_posters(dry_run: bool = False) -> None:
    """
    Processes all poster files in the input folder.
    """
    _ensure_folders_exist()

    logger.info(f"Starting to upload posters from: {_input_folder()}" + (" [DRY RUN]" if dry_run else ""))
    uploaded = 0
    for file_path in sorted(_input_folder().iterdir()):
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            upload_poster(file_path, dry_run=dry_run)
            uploaded += 1

    logger.info(f"Done. Processed {uploaded} files.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Upload basketball posters to Maccabipedia.')
    parser.add_argument('--dry-run', action='store_true', help='Preview actions without uploading.')
    args = parser.parse_args()
    upload_all_posters(dry_run=args.dry_run)
