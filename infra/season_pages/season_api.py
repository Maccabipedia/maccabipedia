"""One API call to the local wiki or to production, paced for production.

Production is shared hosting and answers HTTP 508 when its resource limit is
reached - a sweep of multi-second season-page parses sent back to back did
exactly that on 2026-09-19. So every production call is followed by a pause,
a 508 backs off and retries, and a third 508 in a row stops the script rather
than pushing on.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

WIKIS = {'local': 'http://localhost:8080/api.php',
         'prod': 'https://www.maccabipedia.co.il/api.php'}
UA = {'User-Agent': 'MaccabipediaBot/season-pages (infra/season_pages)'}
PROD_PAUSE_SECONDS = 3.0
PROD_508_ATTEMPTS = 3
PROD_508_BACKOFF_SECONDS = 60


def call(wiki: str, params: dict, post: bool = False) -> dict:
    params = dict(params, format='json', formatversion='2')
    body = urllib.parse.urlencode(params).encode('utf-8')
    url = WIKIS[wiki]
    for attempt in range(1, PROD_508_ATTEMPTS + 1):
        request = (urllib.request.Request(url, data=body, headers=UA) if post else
                   urllib.request.Request(f'{url}?{body.decode()}', headers=UA))
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                data = json.loads(response.read().decode('utf-8'))
            break
        except urllib.error.HTTPError as error:
            if wiki != 'prod' or error.code != 508 or attempt == PROD_508_ATTEMPTS:
                raise
            print(f'  production at its resource limit (508) - waiting '
                  f'{PROD_508_BACKOFF_SECONDS}s', flush=True)
            time.sleep(PROD_508_BACKOFF_SECONDS)
    if 'error' in data:
        raise SystemExit(f'{wiki} API error: {data["error"]}')
    if wiki == 'prod':
        time.sleep(PROD_PAUSE_SECONDS)
    return data
