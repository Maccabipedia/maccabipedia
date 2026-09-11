import logging
import os

from maccabistats import run_maccabitlv_site_source
from maccabistats.config import MaccabiStatsConfigSingleton

from maccabipediabot.common.logging_setup import setup_logging
setup_logging(level=logging.DEBUG)


def fetch_games_from_maccabi_tlv_site() -> None:
    # Season 2026/27
    os.environ['START_SEASON_TO_CRAWL'] = '87'
    logging.info(f"Fetching maccabi tlv site games with start season: {os.environ['START_SEASON_TO_CRAWL']}")

    # The crawler iterates range(START_SEASON_TO_CRAWL, max_seasons_to_crawl), so the
    # ceiling is an *exclusive* upper bound and must sit one past the newest season page
    # or that season is silently skipped. Bump both together every season rollover.
    MaccabiStatsConfigSingleton.maccabi_site.max_seasons_to_crawl = 88

    MaccabiStatsConfigSingleton.maccabi_site.use_multiprocess_crawling = False
    logging.info(
        f"Changed use multi process to be: {MaccabiStatsConfigSingleton.maccabi_site.use_multiprocess_crawling}")

    # The most recent game might still be live; with disk caching on we'd pin the
    # crawler to the live HTML and keep skipping the match on every retry until
    # the cache is wiped by hand. Force every fetch to hit the network.
    MaccabiStatsConfigSingleton.maccabi_site.use_disk_as_cache_when_crawling = False

    run_maccabitlv_site_source()


if __name__ == '__main__':
    logging.info('Fetching last season games from maccabi tlv site')
    fetch_games_from_maccabi_tlv_site()
    logging.info('Fetched last season games from maccabi tlv site!')
