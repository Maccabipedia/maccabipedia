from maccabistats.parse.maccabi_tlv_site.european_stages import fix_european_stages
from maccabistats.parse.maccabi_tlv_site.fix_specific_games import fix_specific_games
from maccabistats.parse.maccabi_tlv_site.main_parser import get_parsed_maccabi_games_from_maccabi_site
from maccabistats.parse.maccabistats_source import MaccabiStatsSource
from maccabistats.parse.sources import SourcesNames

import logging

logger = logging.getLogger(__name__)

"""
Implement MaccabiStatsSource that crawl maccabi-tlv site.
"""


class MaccabiTlvSiteSource(MaccabiStatsSource):

    def __init__(self):
        super().__init__(name=SourcesNames.MaccabiTlvSite.value)

    def _rerun_source(self):
        """
        Parse the raw data and saves it on self.maccabi_games_stats
        """

        return get_parsed_maccabi_games_from_maccabi_site()

    def run_specific_fixes(self):
        """
        Run any specific fixes for this source (such as error within the raw data).
        """

        if self.maccabi_games_stats is None:
            raise RuntimeError("You should run parse_maccabi_games first")

        logger.info("Running fix specific games for maccabi-tlv site source")
        self.maccabi_games_stats = fix_specific_games(self.maccabi_games_stats)

        logger.info("Writing European stages the way the wiki writes them")
        self.maccabi_games_stats = fix_european_stages(self.maccabi_games_stats)



