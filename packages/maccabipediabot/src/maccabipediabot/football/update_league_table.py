import logging
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import mwparserfromhell
import requests

from maccabipediabot.basketball.livescore_table import games_in_play
from maccabipediabot.common.wiki_login import get_site
from maccabipediabot.football.wikipedia_league_table import TeamRow, fetch_season_wikitext, parse_league_tables

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

# The numbers come from English Wikipedia, which follows IFA rulings (technical wins, points
# deductions) that livescore never applies; see wikipedia_league_table. Bump the page each season.
WIKIPEDIA_SEASON_PAGE = "2026–27 Israeli Premier League"
# Which of the page's league tables, by position: [0] is the regular season. Once the playoffs
# begin, switch to [1, 2] (championship round, relegation round), together with the URLs below.
WIKIPEDIA_TABLES = [0]

# livescore only guards the timing: no table while a game is being played, none while Wikipedia
# is still behind on games played. A game still missing from Wikipedia this long after kickoff
# (worst lag measured: 29 h) is no longer a lag, and fails the run instead of freezing the table.
_WIKIPEDIA_MAX_LAG = timedelta(days=3)
_ISRAEL = ZoneInfo("Asia/Jerusalem")
_LIVESCORE_GAME_OVER = 2

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


def fetch_livescore_rows() -> tuple[dict[str, TeamRow], dict[str, datetime]] | None:
    """livescore's row per team and the kickoff of its last finished game, by Hebrew name.

    None while a game is being played.
    """
    rows, last_kickoffs = {}, {}
    for url in LINKS_TO_FETCH_LEAGUE_TABLE_FROM:
        stage = requests.get(url, timeout=30).json()["Stages"][0]
        if in_play := games_in_play(stage):
            logging.warning(f'Not updating the league table, games in play: {in_play}')
            return None
        for row in stage["LeagueTable"]["L"][0]["Tables"][0]["team"]:
            name = OPPONENTS_NAMES_TO_UNICODE.get(row["Tnm"], row["Tnm"])
            rows[name] = TeamRow(name, row["win"], row["drw"], row["lst"], row["gf"], row["ga"], row["win"] * 3 + row["drw"])
        for event in stage.get("Events", []):
            if event.get("Epr") != _LIVESCORE_GAME_OVER or not event.get("Esd"):
                continue
            kickoff = datetime.strptime(str(event["Esd"]), "%Y%m%d%H%M%S").replace(tzinfo=_ISRAEL)
            for side in ("T1", "T2"):
                name = OPPONENTS_NAMES_TO_UNICODE.get(event[side][0]["Nm"], event[side][0]["Nm"])
                last_kickoffs[name] = max(kickoff, last_kickoffs.get(name, kickoff))
    return rows, last_kickoffs


def merge_tables(wikipedia_rows: list[TeamRow], livescore_rows: dict[str, TeamRow],
                 last_kickoffs: dict[str, datetime], now: datetime) -> list[TeamRow] | None:
    """Wikipedia's table, or None while Wikipedia has not caught up with livescore's games.

    Where both agree on a team's wins, draws and losses no ruling touched it, and livescore's
    goals win: Wikipedia's editors once left a 3:0 technical win out of the goal totals
    (Maccabi Tel Aviv 2025-26: 72 for, where the IFA had 75) while getting every result right.
    """
    wikipedia_names = {row.name for row in wikipedia_rows}
    if wikipedia_names != set(livescore_rows):
        raise ValueError(f'Wikipedia and livescore list different teams: only on Wikipedia '
                         f'{sorted(wikipedia_names - set(livescore_rows))}, only on livescore '
                         f'{sorted(set(livescore_rows) - wikipedia_names)}')

    behind = [row.name for row in wikipedia_rows if row.played < livescore_rows[row.name].played]
    if stale := [name for name in behind if name not in last_kickoffs or now - last_kickoffs[name] > _WIKIPEDIA_MAX_LAG]:
        raise RuntimeError(f'Wikipedia still misses a game of {stale} played over {_WIKIPEDIA_MAX_LAG} ago; '
                           f'is {WIKIPEDIA_SEASON_PAGE!r} still updated, or does livescore count an annulled game?')
    if behind:
        logging.warning(f'Not updating the league table, Wikipedia has not caught up yet: {behind}')
        return None

    merged = []
    for row in wikipedia_rows:
        livescore = livescore_rows[row.name]
        if (row.win, row.draw, row.loss) == (livescore.win, livescore.draw, livescore.loss):
            row = replace(row, goals_for=livescore.goals_for, goals_against=livescore.goals_against)
        else:
            # A ruling, or a Wikipedia mistake: the run log is where to tell them apart.
            logging.warning(f'{row.name}: Wikipedia {row.as_template_row()} and livescore '
                            f'{livescore.as_template_row()} disagree on results; saving Wikipedia\'s')
        merged.append(row)
    return merged


def fetch_league_table_data() -> str | None:
    """The table rows as the template expects them, or None when this run should not save."""
    livescore = fetch_livescore_rows()
    if livescore is None:
        return None
    livescore_rows, last_kickoffs = livescore
    wikipedia_rows = parse_league_tables(fetch_season_wikitext(WIKIPEDIA_SEASON_PAGE), WIKIPEDIA_TABLES)
    merged = merge_tables(wikipedia_rows, livescore_rows, last_kickoffs, datetime.now(_ISRAEL))
    if merged is None:
        return None

    prettified_result = ",\n".join(row.as_template_row() for row in merged)
    logging.info(f'Fetched league table data: {prettified_result}')
    return prettified_result


def update_league_table_status() -> None:
    logging.info(f'Fetching current league table from: {LINKS_TO_FETCH_LEAGUE_TABLE_FROM}')
    league_table_data = fetch_league_table_data()
    if league_table_data is None:
        return

    league_table_template_page = pw.Page(site, _LEAGUE_TABLE_TEMPLATE_ON_MACCABIPEDIA)

    parsed_mw_text = mwparserfromhell.parse(league_table_template_page.text)
    table_template = parsed_mw_text.filter_templates(_LEAGUE_TABLE_TEMPLATE_ON_MACCABIPEDIA)[0]
    table_template.add(_TABLE_STATUS_KEY, league_table_data)

    league_table_template_page.text = parsed_mw_text

    league_table_template_page.save(summary="MaccabiBot - Update league table")


if __name__ == '__main__':
    update_league_table_status()
