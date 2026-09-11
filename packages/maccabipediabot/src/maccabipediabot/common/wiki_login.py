import logging
from functools import lru_cache
from pathlib import Path

import pywikibot as pw
from pywikibot import config
from pywikibot.comms import http as pw_http

from maccabipediabot.common.maccabipedia_http import install_response_diagnostics

MACCABIPEDIA_FAMILY_FILE = Path(__file__).absolute().parent.parent / 'pywikibot_configs' / 'maccabipedia_family.py'


@lru_cache(maxsize=1)
def get_site() -> pw.Site:
    logging.info('Logging in to MaccabiPedia')
    config.family_files['maccabipedia'] = str(MACCABIPEDIA_FAMILY_FILE)

    # pywikibot swallows the raw body, so a WAF block page surfaces only as
    # "API userinfo response lacks 'query' key" from inside pw.Site(). Hook its shared
    # session first so the blocked response itself gets logged.
    install_response_diagnostics(pw_http.session)

    site = pw.Site()
    site.login()

    return site
