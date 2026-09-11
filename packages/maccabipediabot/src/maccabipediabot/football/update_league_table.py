import logging

import mwparserfromhell
import requests

from maccabipediabot.common.wiki_login import get_site

_LEAGUE_TABLE_TEMPLATE_ON_MACCABIPEDIA = 'תבנית:טבלת_ליגת_כדורגל_2026/27'
_TABLE_STATUS_KEY = 'טבלה'

OPPONENTS_NAMES_TO_UNICODE = {"FC Ashdod": "\u05de.\u05e1. \u05d0\u05e9\u05d3\u05d5\u05d3",
                              "Bnei Sakhnin": "\u05d1\u05e0\u05d9 \u05e1\u05db\u05e0\u05d9\u05df",
                              "Hapoel Hadera": "\u05d4\u05e4\u05d5\u05e2\u05dc \u05d7\u05d3\u05e8\u05d4",
                              "Beitar Jerusalem": "\u05d1\u05d9\u05ea\"\u05e8 \u05d9\u05e8\u05d5\u05e9\u05dc\u05d9\u05dd",
                              "Hapoel Tel Aviv": "\u05d4\u05e4\u05d5\u05e2\u05dc \u05ea\u05dc \u05d0\u05d1\u05d9\u05d1",
                              "Maccabi Bnei Reineh": "\u05de\u05db\u05d1\u05d9 \u05d1\u05e0\u05d9 \u05e8\u05d9\u05d9\u05e0\u05d4",
                              "Hapoel Jerusalem": "\u05d4\u05e4\u05d5\u05e2\u05dc \u05d9\u05e8\u05d5\u05e9\u05dc\u05d9\u05dd",
                              "Ironi Kiryat Shmona": "\u05e2\u05d9\u05e8\u05d5\u05e0\u05d9 \u05e7\u05e8\u05d9\u05ea \u05e9\u05de\u05d5\u05e0\u05d4",
                              "Sektzia Nes Tziona": "\u05e1\u05e7\u05e6\u05d9\u05d4 \u05e0\u05e1 \u05e6\u05d9\u05d5\u05e0\u05d4",
                              "Hapoel Beer Sheva": "\u05d4\u05e4\u05d5\u05e2\u05dc \u05d1\u05d0\u05e8 \u05e9\u05d1\u05e2",
                              "Maccabi Haifa": "\u05de\u05db\u05d1\u05d9 \u05d7\u05d9\u05e4\u05d4",
                              "Maccabi Netanya": "\u05de\u05db\u05d1\u05d9 \u05e0\u05ea\u05e0\u05d9\u05d4",
                              "Hapoel Haifa": "\u05d4\u05e4\u05d5\u05e2\u05dc \u05d7\u05d9\u05e4\u05d4",
                              "Maccabi Tel Aviv": "\u05de\u05db\u05d1\u05d9 \u05ea\u05dc \u05d0\u05d1\u05d9\u05d1",
                              "Maccabi Petach Tikva": "מכבי פתח תקווה", "Hapoel Petah Tikva": "הפועל פתח תקווה",
                              "Ironi Tiberias": "עירוני טבריה", "Hapoel Ironi Kiryat Shmona": "עירוני קריית שמונה",
                              "Hapoel Ramat Gan": "הפועל רמת גן"}

# The source site (livescore.com) does not follow Israeli Football Association
# disciplinary rulings, so points deductions must be applied here explicitly -
# keyed by the source's English team name (row["Tnm"]), same as OPPONENTS_NAMES_TO_UNICODE.
# Update this each season to match the "הערות" section of the league table template.
POINTS_DEDUCTIONS = {
    "Ironi Tiberias": 6,
}

LINKS_TO_FETCH_LEAGUE_TABLE_FROM = [
    # Playoff stages (top 6 + bottom 8). Swap with the regular-season URL below
    # at the start of each season, then back once playoffs begin.
    #"https://prod-public-api.livescore.com/v1/api/app/stage/soccer/israel/premier-league-championship-group/3",
    #"https://prod-public-api.livescore.com/v1/api/app/stage/soccer/israel/premier-league-relegation-group/3",

    "https://prod-public-api.livescore.com/v1/api/app/stage/soccer/israel/premier-league/3?locale=en&MD=1"
]

from maccabipediabot.common.logging_setup import setup_logging
setup_logging(level=logging.DEBUG)

# We need to log before we run any of our maccabipedia (pywikibot or it's import) related code
site = get_site()

import pywikibot as pw


def fetch_league_table_data():
    stats = []

    for url in LINKS_TO_FETCH_LEAGUE_TABLE_FROM:
        resp = requests.get(url)
        table = resp.json()["Stages"][0]["LeagueTable"]["L"][0]["Tables"][0]["team"]
        table_rows = []
        for row in table:
            points = row["win"] * 3 + row["drw"] - POINTS_DEDUCTIONS.get(row["Tnm"], 0)
            row_line = "^".join(
                [
                    OPPONENTS_NAMES_TO_UNICODE.get(row["Tnm"], row["Tnm"]),
                    str(row["pld"]),
                    row["winn"],
                    row["drwn"],
                    row["lstn"],
                    str(row["gf"]),
                    str(row["ga"]),
                    str(points),
                ]
            )
            table_rows.append((points, row_line))

        # Deductions can drop a team's real points below the source's own
        # (undeducted) sort order, so re-sort within this stage rather than
        # trusting the fetched row order for standings position.
        table_rows.sort(key=lambda item: item[0], reverse=True)
        stats.extend(row_line for _, row_line in table_rows)
    prettified_result = ",\n".join(stats)

    logging.info(f'Fetched league table data: {prettified_result}')
    return prettified_result


def update_league_table_status() -> None:
    logging.info(f'Fetching current league table from: {LINKS_TO_FETCH_LEAGUE_TABLE_FROM}')
    league_table_data = fetch_league_table_data()

    league_table_template_page = pw.Page(site, _LEAGUE_TABLE_TEMPLATE_ON_MACCABIPEDIA)

    parsed_mw_text = mwparserfromhell.parse(league_table_template_page.text)
    table_template = parsed_mw_text.filter_templates(_LEAGUE_TABLE_TEMPLATE_ON_MACCABIPEDIA)[0]
    table_template.add(_TABLE_STATUS_KEY, league_table_data)

    league_table_template_page.text = parsed_mw_text

    league_table_template_page.save(summary="MaccabiBot - Update league table")


if __name__ == '__main__':
    update_league_table_status()
