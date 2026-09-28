import logging

import mwparserfromhell

from maccabipediabot.basketball.livescore_table import TABLE_TEMPLATE_NAME, fetch_stage, season_of_stage
from maccabipediabot.common.wiki_login import get_site

# Filled with the season of the table livescore serves, e.g. "2026/27".
TABLE_TEMPLATE_ON_MACCABIPEDIA = 'תבנית:טבלת_יורוליג_{season}'
TABLE_STATUS_KEY = 'טבלה'

OPPONENTS_NAMES_TO_UNICODE = {"Maccabi Tel Aviv": "מכבי תל אביב",
                              "Zalgiris Kaunas": "ז'לגיריס קובנה",
                              "Crvena Zvezda Beograd": "הכוכב האדום בלגרד",
                              "Hapoel Tel Aviv": "הפועל תל אביב",
                              "Olympiacos B.C.": "אולימפיאקוס",
                              "Monaco": "מונקו",
                              "Real Madrid": "ריאל מדריד",
                              "Valencia": "ולנסיה",
                              "Panathinaikos": "פנאתינייקוס",
                              "Barcelona": "ברצלונה",
                              "FC Bayern Munchen": "באיירן מינכן",
                              "Paris Basketball": "פריז בסקטבול",
                              "Olimpia Milano": "ארמאני מילאנו",
                              "Fenerbahçe": "פנרבחצ'ה",
                              "Virtus Bologna": "וירטוס בולוניה",
                              "BC Dubai": "דובאי",
                              "Anadolu Efes": "אנאדולו אפס",
                              "Saski Baskonia": "בסקוניה",
                              "Partizan": "פרטיזן בלגרד",
                              "ASVEL Lyon-Villeurbanne": "ליון-וילרבן",
                              "Beşiktaş": "בשיקטאש",
                              }


TABLE_URL = "https://prod-cdn-public-api.livescore.com/v1/api/app/stage/basketball/euro-league/euroleague-regular-season/2"

from maccabipediabot.common.logging_setup import setup_logging
setup_logging(level=logging.DEBUG)

# We need to log before we run any of our maccabipedia (pywikibot or it's import) related code
site = get_site()

import pywikibot as pw


def fetch_table_data() -> tuple[str, str]:
    """The table rows as the template expects them, and the season they belong to."""
    stage = fetch_stage(TABLE_URL)
    stats = []
    for row in stage["LeagueTable"]["L"][0]["Tables"][0]["team"]:
        wins = int(row["winn"])
        losses = int(row["lstn"])
        points = wins * 2 + losses * 1
        stats.append(
            "^".join(
                [
                    OPPONENTS_NAMES_TO_UNICODE.get(row["Tnm"], row["Tnm"]),
                    str(row["pld"]),
                    row["winn"],
                    row["lstn"],
                    str(row["gf"]),
                    str(row["ga"]),
                    str(points),
                ]
            )
        )
    prettified_result = ",\n".join(stats)

    logging.info(f'Fetched table data: {prettified_result}')
    return prettified_result, season_of_stage(stage)


def update_table_status() -> None:
    logging.info(f'Fetching current table from: {TABLE_URL}')
    table_data, season = fetch_table_data()

    template_title = TABLE_TEMPLATE_ON_MACCABIPEDIA.format(season=season)
    table_template_page = pw.Page(site, template_title)
    if not table_template_page.exists():
        raise RuntimeError(f"{template_title} does not exist; create the {season} table template "
                           f"(copy last season's) and add it to the season page")

    parsed_mw_text = mwparserfromhell.parse(table_template_page.text)
    table_template = parsed_mw_text.filter_templates(matches=TABLE_TEMPLATE_NAME)[0]
    table_template.add(TABLE_STATUS_KEY, table_data)

    table_template_page.text = parsed_mw_text

    table_template_page.save(summary="MaccabiBot - Update euroleague table")


if __name__ == '__main__':
    update_table_status()
