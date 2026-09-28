import logging

import mwparserfromhell

from maccabipediabot.basketball.livescore_table import TABLE_TEMPLATE_NAME, fetch_stage, season_of_stage
from maccabipediabot.common.wiki_login import get_site

# Filled with the season of the table livescore serves, e.g. "2026/27".
_LEAGUE_TABLE_TEMPLATE_ON_MACCABIPEDIA = 'תבנית:טבלת_ליגת_כדורסל_{season}'
_TABLE_STATUS_KEY = 'טבלה'

OPPONENTS_NAMES_TO_UNICODE = {"Maccabi Tel Aviv": "מכבי תל אביב",
                              "Hapoel Tel Aviv": "הפועל תל אביב",
                              "Hapoel Gilboa/Galil": "הפועל העמק",
                              "Maccabi Raanana": "מכבי עירוני רעננה",
                              "Maccabi Ironi Ramat Gan": "מכבי עירוני רמת גן",
                              "Hapoel Holon": "הפועל חולון",
                              "Hapoel Galil Elyon": "הפועל גליל עליון",
                              "Hapoel Jerusalem": "הפועל ירושלים",
                              "Maccabi Rishon LeZion": "מכבי ראשון לציון",
                              "Hapoel Beer Sheva": "הפועל באר שבע",
                              "Elitzur Netanya": "אליצור עירוני נתניה",
                              "Ironi Nes Ziona": "עירוני נס ציונה",
                              "Bnei Herzliya": "בני הרצליה",
                              "Ironi Kiryat Ata": "עירוני קרית אתא",
                              "Hapoel Eilat": "הפועל אילת",
                              "Maccabi Ashdod": "מכבי אשדוד",
                              }


LEAGUE_TABLE_URL = "https://prod-cdn-public-api.livescore.com/v1/api/app/stage/basketball/israel/super-league/2"

from maccabipediabot.common.logging_setup import setup_logging
setup_logging(level=logging.DEBUG)

# We need to log before we run any of our maccabipedia (pywikibot or it's import) related code
site = get_site()

import pywikibot as pw


def fetch_league_table_data() -> tuple[str, str]:
    """The table rows as the template expects them, and the season they belong to."""
    stage = fetch_stage(LEAGUE_TABLE_URL)
    stats = []
    for row in stage["LeagueTable"]["L"][0]["Tables"][0]["team"]:
        stats.append(
            "^".join(
                [
                    OPPONENTS_NAMES_TO_UNICODE.get(row["Tnm"], row["Tnm"]),
                    str(row["pld"]),
                    row["winn"],
                    row["lstn"],
                    str(row["gf"]),
                    str(row["ga"]),
                    row["ptsn"],
                ]
            )
        )
    prettified_result = ",\n".join(stats)

    logging.info(f'Fetched league table data: {prettified_result}')
    return prettified_result, season_of_stage(stage)


def update_league_table_status() -> None:
    logging.info(f'Fetching current league table from: {LEAGUE_TABLE_URL}')
    league_table_data, season = fetch_league_table_data()

    template_title = _LEAGUE_TABLE_TEMPLATE_ON_MACCABIPEDIA.format(season=season)
    league_table_template_page = pw.Page(site, template_title)
    if not league_table_template_page.exists():
        raise RuntimeError(f"{template_title} does not exist; create the {season} table template "
                           f"(copy last season's) and add it to the season page")

    parsed_mw_text = mwparserfromhell.parse(league_table_template_page.text)
    table_template = parsed_mw_text.filter_templates(matches=TABLE_TEMPLATE_NAME)[0]
    table_template.add(_TABLE_STATUS_KEY, league_table_data)

    league_table_template_page.text = parsed_mw_text

    league_table_template_page.save(summary="MaccabiBot - Update league table")


if __name__ == '__main__':
    update_league_table_status()
