import argparse
import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path

import aiohttp
import requests
from aiohttp import ClientSession
from bs4 import BeautifulSoup, Tag

from maccabipediabot.basketball._crawler_utils import (
    UnknownTeamNameError,
    season_from_date,
    to_int_or_none,
    write_unknown_teams_report,
)
from maccabipediabot.basketball.basketball_game import BasketballGame, PlayerSummary
from maccabipediabot.basketball.translations import (
    basket_co_il_competition_name,
    is_known_team_name,
    normalize_player_name,
    team_name_to_hebrew,
)
from maccabipediabot.common.json_io import write_pydantic_list_as_json

logger = logging.getLogger(__name__)

SEASON_23_24_TEAM_ID = 1096
BASKET_CO_IL_SITE_MACCABI_BASE_PAGE = "https://basket.co.il/team.asp?TeamId={team_id}"
COMPETITION_NAME = "ליגת Winner סל"
BASKET_CO_IL_SITE_PREFIX = "https://basket.co.il/"
GAMES_ALL_FEED_URL = "https://basket.co.il/pbp/json/games_all.json"
GAME_PAGE_URL_TEMPLATE = "https://basket.co.il/game-zone.asp?GameId={game_id}"
MACCABI_TEAM_NAME_ENG = "Maccabi Tel-Aviv"
MAX_CONNECTIONS = 100


# basket.co.il labels a playoff leg with varying wording per round — e.g.
# "- רבע הגמר משחק מספר 1" (QF), "- סדרת חצי גמר משחק מספר 1" (SF),
# "- סדרת הגמר משחק 1" (final). The wiki convention is "<round> - משחק N"
# (see existing ליגת העל playoff pages). We classify the round by keyword and
# rebuild the label, so new phrasings ("סדרת", with/without ה, "מספר") still map.
_PLAYOFF_GAME_NUMBER_RE = re.compile(r"משחק(?:\s+מספר)?\s+(\d+)")


def _competition_from_game_page(html: str) -> str | None:
    """Recover the competition from a game-zone page header when the feed's
    game_type code isn't mapped (e.g. a playoff round, which gets a fresh code
    each stage). The top-league header reads "ליגת <sponsor logo> סל ..." — once
    the logo <img> is dropped, the tokens "ליגת סל" sit adjacent, which positively
    identifies the top division across every round and excludes both cups
    ("גביע ... סל") and the second tier ("ליגת לאומית בכדורסל"). Anything else
    returns None so the caller fails loud rather than mislabeling a page."""
    soup = BeautifulSoup(html, "html.parser")
    header = soup.select_one("#wrap_inner_3 h4")
    h4_text = re.sub(r"\s+", " ", header.get_text(" ", strip=True)) if header else ""
    if "ליגת סל" in h4_text:
        return "ליגת העל"
    return None


def _normalize_fixture(fixture: str) -> str:
    """Map a basket.co.il playoff leg to the wiki convention "<round> - משחק N".
    Only legs that name a round (...גמר) *and* a game number are rewritten;
    regular-season "מחזור N" and anything else are returned unchanged."""
    number_match = _PLAYOFF_GAME_NUMBER_RE.search(fixture)
    if "גמר" not in fixture or number_match is None:
        return fixture
    if "רבע" in fixture:
        round_name = "רבע גמר"
    elif "חצי" in fixture:
        round_name = "חצי גמר"
    else:
        # ליגת העל playoffs are an 8-team bracket: רבע גמר -> חצי גמר -> גמר.
        # Any other ...גמר leg is the final.
        round_name = "גמר"
    return f"{round_name} - משחק {number_match.group(1)}"


def parse_game_page(html: str, partial_game: BasketballGame) -> BasketballGame:
    """Enrich a partially-built BasketballGame (from discovery) with per-game data.

    Discovery sets: home/away team names + scores, date, competition, game URL.
    This function adds: fixture (round/series), arena, crowd, referees,
    coaches, per-quarter and per-OT scores, full player rosters per team.

    Returns a new BasketballGame; does not mutate the input.
    """
    soup = BeautifulSoup(html, "html.parser")

    is_maccabi_home = partial_game.home_team_name == "מכבי תל אביב"
    header = _parse_header(soup)
    quarter_scores = _parse_quarter_scores(soup, is_maccabi_home)
    box_score = _parse_box_score(soup, is_maccabi_home)

    return partial_game.model_copy(update=dict(
        fixture=header["fixture"],
        arena=header["stadium"],
        crowd=header["crowd"],
        referee=header["main_referee"],
        referee_assistants=header["assistant_referees"],
        first_quarter_maccabi_points=quarter_scores["maccabi"][0],
        second_quarter_maccabi_points=quarter_scores["maccabi"][1],
        third_quarter_maccabi_points=quarter_scores["maccabi"][2],
        fourth_quarter_maccabi_points=quarter_scores["maccabi"][3],
        first_overtime_maccabi_points=quarter_scores["maccabi"][4],
        second_overtime_maccabi_points=quarter_scores["maccabi"][5],
        third_overtime_maccabi_points=quarter_scores["maccabi"][6],
        fourth_overtime_maccabi_points=quarter_scores["maccabi"][7],
        first_quarter_opponent_points=quarter_scores["opponent"][0],
        second_quarter_opponent_points=quarter_scores["opponent"][1],
        third_quarter_opponent_points=quarter_scores["opponent"][2],
        fourth_quarter_opponent_points=quarter_scores["opponent"][3],
        first_overtime_opponent_points=quarter_scores["opponent"][4],
        second_overtime_opponent_points=quarter_scores["opponent"][5],
        third_overtime_opponent_points=quarter_scores["opponent"][6],
        fourth_overtime_opponent_points=quarter_scores["opponent"][7],
        maccabi_coach=box_score["maccabi_coach"],
        opponent_coach=box_score["opponent_coach"],
        maccabi_players=box_score["maccabi_players"],
        opponent_players=box_score["opponent_players"],
        season=season_from_date(partial_game.game_date),
    ))


def _parse_header(soup: BeautifulSoup) -> dict:
    """Extract fixture, stadium, referees, crowd from #wrap_inner_3."""
    container = soup.select_one("#wrap_inner_3")
    if not container:
        raise RuntimeError("game-zone page missing #wrap_inner_3")

    h4 = container.select_one("h4")
    fixture = ""
    if h4:
        img = h4.find("img")
        if img and img.next_sibling:
            sibling_text = (img.next_sibling.get_text() if hasattr(img.next_sibling, "get_text")
                            else str(img.next_sibling))
            fixture = _normalize_fixture(sibling_text.strip().replace("סל", "").strip())

    h5 = container.select_one("h5")
    stadium = ""
    if h5:
        stadium = h5.get_text(",", strip=True).split(",")[0].strip()

    # Crowd ('צופים: NNNN') lives somewhere inside #wrap_inner_3 — exact selector
    # has shifted over time, so just search the container text.
    crowd: int | None = None
    container_text = container.get_text(" ", strip=True).replace("\xa0", " ")
    crowd_match = re.search(r"צופים:\s*(\d[\d,]*)", container_text)
    if crowd_match:
        crowd = int(crowd_match.group(1).replace(",", ""))

    h6 = container.select_one("h6")
    main_referee = ""
    assistant_referees: list[str] = []
    if h6:
        text = re.sub(r"\s+", " ", h6.get_text()).strip()
        if "שופטים:" in text:
            after = text.split("שופטים:", 1)[1]
            if "משקיף:" in after:
                after = after.split("משקיף:", 1)[0]
            refs = [ref.strip() for ref in after.split(",") if ref.strip()]
            if refs:
                main_referee = refs[0]
                assistant_referees = refs[1:]

    return {
        "fixture": fixture,
        "stadium": stadium,
        "main_referee": main_referee,
        "assistant_referees": assistant_referees,
        "crowd": crowd,
    }


def _parse_quarter_scores(soup: BeautifulSoup, is_maccabi_home: bool) -> dict:
    """Returns {maccabi: list, opponent: list}; each list is 8 entries
    [Q1,Q2,Q3,Q4,OT1,OT2,OT3,OT4] with None for absent periods."""
    cats = soup.select("table.stats_tbl.categories")
    if not cats:
        raise RuntimeError("game-zone page missing table.stats_tbl.categories")
    rows = cats[0].select("tr")
    if len(rows) < 3:
        raise RuntimeError("score table has fewer than 3 rows")

    # row 0 = header (period labels), row 1 = home team scores, row 2 = away team scores
    home_cells = [td.get_text(strip=True) for td in rows[1].select("td")][1:]
    away_cells = [td.get_text(strip=True) for td in rows[2].select("td")][1:]

    def _to_quarters(cells: list[str]) -> list[int | None]:
        out: list[int | None] = []
        for cell in cells:
            try:
                out.append(int(cell))
            except (ValueError, TypeError):
                out.append(None)
        return out[:8] + [None] * max(0, 8 - len(out))

    home_scores = _to_quarters(home_cells)
    away_scores = _to_quarters(away_cells)

    if is_maccabi_home:
        return {"maccabi": home_scores, "opponent": away_scores}
    return {"maccabi": away_scores, "opponent": home_scores}


def _parse_box_score(soup: BeautifulSoup, is_maccabi_home: bool) -> dict:
    tables = soup.select("table.stats_tbl")
    if len(tables) < 4:
        raise RuntimeError(
            f"game-zone page has fewer than 4 stats_tbl tables (got {len(tables)}); "
            "site layout likely changed"
        )
    home_table, away_table = tables[2], tables[3]

    home_coach = _coach_from_table(home_table)
    away_coach = _coach_from_table(away_table)
    home_players = _parse_player_rows(home_table)
    away_players = _parse_player_rows(away_table)

    if is_maccabi_home:
        return {
            "maccabi_coach": home_coach,
            "opponent_coach": away_coach,
            "maccabi_players": home_players,
            "opponent_players": away_players,
        }
    return {
        "maccabi_coach": away_coach,
        "opponent_coach": home_coach,
        "maccabi_players": away_players,
        "opponent_players": home_players,
    }


def _coach_from_table(table: Tag) -> str:
    """The coach is the second link in the team's table header (`<a>...:NAME</a>`)."""
    links = table.select("tr td a")
    if len(links) < 2:
        return ""
    text = links[1].get_text() or ""
    parts = text.split(":")
    return parts[1].strip() if len(parts) > 1 else ""


def _parse_player_rows(table: Tag) -> list[PlayerSummary]:
    """Layout: header rows first, then `<tr class="row">` per player. The first
    `tr.row` is the column header; players start at the second."""
    rows = table.select("tr")
    if not rows:
        return []

    start_index = -1
    seen = 0
    for i, row in enumerate(rows):
        if "row" in row.get("class", []):
            seen += 1
            if seen == 2:
                start_index = i
                break
    if start_index == -1:
        return []

    players: list[PlayerSummary] = []
    for row in rows[start_index:-1]:  # last row is totals
        tds = row.select("td")
        if len(tds) < 21:
            continue

        def _to_int(text: str | None) -> int:
            try:
                return int((text or "").strip())
            except (ValueError, TypeError):
                return 0

        def _split_stat(text: str | None) -> tuple[int, int]:
            if not text:
                return (0, 0)
            parts = text.split("/")
            return (_to_int(parts[0]), _to_int(parts[1]) if len(parts) > 1 else 0)

        fg_scored, fg_attempts = _split_stat(tds[5].get_text())
        tg_scored, tg_attempts = _split_stat(tds[7].get_text())
        ft_scored, ft_attempts = _split_stat(tds[9].get_text())

        number_link = tds[0].select_one("a")
        name_link = tds[1].select_one("a")
        raw_name = name_link.get_text(strip=True) if name_link else ""

        players.append(PlayerSummary(
            number=to_int_or_none(number_link.get_text(strip=True) if number_link else None),
            name=normalize_player_name(raw_name),
            is_starting_five=tds[2].get_text(strip=True) == "*",
            minutes_played=_to_int(tds[3].get_text()),
            total_points=_to_int(tds[4].get_text()),
            field_goals_attempts=fg_attempts,
            field_goals_scored=fg_scored,
            three_scores_attempts=tg_attempts,
            three_scores_scored=tg_scored,
            free_throws_attempts=ft_attempts,
            free_throws_scored=ft_scored,
            defensive_rebounds=_to_int(tds[11].get_text()),
            offensive_rebounds=_to_int(tds[12].get_text()),
            personal_total_fouls=_to_int(tds[14].get_text()),
            steals=_to_int(tds[16].get_text()),
            turnovers=_to_int(tds[17].get_text()),
            assists=_to_int(tds[18].get_text()),
            blocks=_to_int(tds[19].get_text()),
        ))
    return players




async def enrich_game(session: ClientSession, game: BasketballGame) -> BasketballGame:
    """Fetch the per-game page and return an enriched BasketballGame."""
    url = game.game_url[0] if isinstance(game.game_url, list) else game.game_url
    async with session.get(url) as response:
        logging.info("Fetching per-game data: %s", url)
        content = await response.text()
    return parse_game_page(content, game)

async def build_seasons_games_metadata_from_season_url(session: ClientSession, season_url: str, season: str) -> list[
    BasketballGame]:
    async with (session.get(season_url) as response):
        logging.info(f"Fetching all games from season: {season}")

        content = await response.text()
        soup = BeautifulSoup(content, "html.parser")
        rows = soup.find(lambda tag: tag.name == "h2" and "לוח משחקים" in tag.get_text()) \
            .find_next("table", class_="stats_tbl") \
            .select("tr.row")

        games = []
        for row in rows:
            cells = row.find_all("td")

            date_td = cells[0]
            time_td = cells[1]

            raw_game_date = date_td.contents[0].strip()
            game_date = datetime.strptime(raw_game_date, "%d/%m/%Y")  # Convert to datetime object
            hour = time_td.get_text(strip=True)

            raw_stage = cells[2].get_text(strip=True)
            # We skip problematic game dates in here, these rows doesn't contain competition in basket site
            # Many games of חצאי גמר are written w/o competition
            if not COMPETITION_NAME in raw_stage and raw_stage != 'פיינל פור - חצאי הגמר' and 'ליגת העל - בית הגמר' not in raw_stage:
                raise RuntimeError(f'Could not find {COMPETITION_NAME} in {raw_stage}, can not parse this game page')

            # Patch for game from '14/10/2012'
            if raw_stage == 'גמר ליגת Winner סל':
                raw_stage = 'ליגת Winner סל, גמר'

            if raw_stage == 'פיינל פור - חצאי הגמר':
                raw_stage = 'ליגת Winner סל, פיינל פור - חצאי הגמר'

            fixture = raw_stage.split(',')[1].strip()

            home_team = cells[3].get_text(strip=True)
            away_team = cells[4].get_text(strip=True)

            score_cell = cells[5]

            # Get game URL, raise if not found
            a_tag = score_cell.find("a")
            if not a_tag or "href" not in a_tag.attrs:
                raise RuntimeError(f"Game URL not found for {home_team} vs {away_team}")
            game_url = a_tag["href"]

            # Parse score and URL
            if 'img/icon_news.png' in str(score_cell):
                logging.info(f'Skipping future game: {game_url}')
                continue

            score_text = score_cell.get_text(strip=True)

            # Validate and parse score
            score_text = score_text.split('(')[0].strip()  # Remove the part inside parentheses (e.g., (1))

            try:
                home_score, away_score = map(int, score_text.split('-'))
            except (ValueError, IndexError):
                raise ValueError(f"Invalid score format: '{score_text}' for {home_team} vs {away_team}")

            basketball_game = BasketballGame(
                home_team_name=home_team,
                away_team_name=away_team,
                home_team_score=home_score,
                away_team_score=away_score,
                competition=COMPETITION_NAME,
                fixture=fixture,
                game_date=game_date,
                game_url=f'{BASKET_CO_IL_SITE_PREFIX}{game_url}',
                season=season,
                hour=hour,
                maccabi_players=[],
                opponent_players=[])

            games.append(basketball_game)
    return games


async def extract_games_links_from_seasons_pages(session: ClientSession, season: str, team_id: str) -> list[
    BasketballGame]:
    season_games = await build_seasons_games_metadata_from_season_url(
        session,
        BASKET_CO_IL_SITE_MACCABI_BASE_PAGE.format(team_id=team_id),
        season)

    for game in season_games:
        await enrich_game(session, game)
    return season_games


async def get_team_ids_for_all_seasons(session: ClientSession) -> dict[str, str]:
    async with session.get(BASKET_CO_IL_SITE_MACCABI_BASE_PAGE.format(team_id=SEASON_23_24_TEAM_ID)) as response:
        logging.info("Fetching all seasons team id")

        content = await response.text()
        soup = BeautifulSoup(content, 'html.parser')

        # Select all <option> elements inside the <select> inside <form id="seasons">
        options = soup.select("form#seasons select#TeamId option")

        # Create a dict form season str to team id
        seasons_to_team_ids = {opt.text.strip().replace('-', '/'): opt["value"] for opt in options if opt.get("value")}

        return seasons_to_team_ids


def discover_games_latest_season(limit: int | None = None) -> list[BasketballGame]:
    """Fetch basket.co.il's current-season feed; return partial BasketballGame objects
    for Maccabi's finished games (per-game scrape fields filled later by parse_game_page)."""
    resp = requests.get(GAMES_ALL_FEED_URL, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Unexpected games_all response: status={resp.status_code} "
            f"ctype={resp.headers.get('Content-Type')}\n{resp.text[:300]}"
        )

    # The feed is served as text/html and starts with a UTF-8 BOM, so json() fails.
    payload = json.loads(resp.content.decode("utf-8-sig"))
    games = payload[0]["games"]

    maccabi_games = [game for game in games
                     if game.get("team_name_eng_1") == MACCABI_TEAM_NAME_ENG
                     or game.get("team_name_eng_2") == MACCABI_TEAM_NAME_ENG]

    def _is_finished(game: dict) -> bool:
        # Both scores must be present (not None / not empty string) AND at least one
        # team must have scored. basket.co.il's feed marks unplayed-but-scheduled games
        # with 0-0 as a placeholder; in basketball a real result of 0-0 doesn't happen.
        score_team_1 = game.get("score_team1")
        score_team_2 = game.get("score_team2")
        if score_team_1 in (None, "") or score_team_2 in (None, ""):
            return False
        try:
            return int(score_team_1) + int(score_team_2) > 0
        except (TypeError, ValueError):
            return False

    finished = [game for game in maccabi_games if _is_finished(game)]

    def _sort_key(game: dict) -> datetime:
        d, m, y = game["game_date_txt"].split("/")
        return datetime(int(y), int(m), int(d))

    finished.sort(key=_sort_key, reverse=True)
    if limit:
        finished = finished[:limit]

    discovered: list[BasketballGame] = []
    unknown_competition_games: list[dict] = []
    unmapped_team_games: list[dict] = []
    for game in finished:
        day, month, year = game["game_date_txt"].split("/")
        time_str = game.get("game_time") or "00:00"
        hour, minute = time_str.split(":") if ":" in time_str else ("0", "0")
        game_dt = datetime(int(year), int(month), int(day), int(hour), int(minute))

        raw_home, raw_away = game["team_name_eng_1"], game["team_name_eng_2"]
        unmapped = [name for name in (raw_home, raw_away) if not is_known_team_name(name)]
        if unmapped:
            unmapped_team_games.append(
                {"id": game.get("id"), "teams": unmapped,
                 "date": game.get("game_date_txt")}
            )
            continue

        home_team = team_name_to_hebrew(raw_home)
        away_team = team_name_to_hebrew(raw_away)

        game_page_url = GAME_PAGE_URL_TEMPLATE.format(game_id=game["id"])
        # Stable codes resolve from the map; playoff rounds (each a different code)
        # fall back to the competition named in the game page header.
        competition = (basket_co_il_competition_name(game["game_type"])
                       or _competition_from_game_page(fetch_game_html(game_page_url)))
        if not competition:
            unknown_competition_games.append(
                {"id": game.get("id"), "game_type": game.get("game_type"),
                 "date": game.get("game_date_txt")}
            )
            continue

        discovered.append(BasketballGame(
            home_team_name=home_team,
            away_team_name=away_team,
            competition=competition,
            fixture="",  # filled by parse_game_page
            game_date=game_dt,
            home_team_score=int(game["score_team1"]),
            away_team_score=int(game["score_team2"]),
            game_url=[game_page_url],
        ))
    if unknown_competition_games:
        raise RuntimeError(
            "basket.co.il discovery could not resolve competition for some games "
            "(unknown game_type and unrecognised page header). Extend "
            "translations._BASKET_GAME_TYPE or _competition_from_game_page before "
            f"re-running. Affected games: {unknown_competition_games}"
        )
    if unmapped_team_games:
        raise UnknownTeamNameError(unmapped_team_games)
    return discovered


def fetch_game_html(scrape_url: str) -> str:
    """Fetch a basket.co.il game-zone.asp page as UTF-8 HTML."""
    resp = requests.get(scrape_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"  # basket.co.il sends bytes without a declared charset
    return resp.text


def _run_latest_season(limit: int | None) -> list[BasketballGame]:
    discovered = discover_games_latest_season(limit=limit)
    logging.info("Discovered %d Maccabi games for latest season", len(discovered))
    return [parse_game_page(fetch_game_html(partial_game.game_url[0]), partial_game)
            for partial_game in discovered]


async def _run_all_seasons() -> list[BasketballGame]:
    connector = aiohttp.TCPConnector(limit=MAX_CONNECTIONS)
    async with aiohttp.ClientSession(connector=connector) as session:
        seasons_to_team_ids = await get_team_ids_for_all_seasons(session)
        logging.info("Seasons to team ids: %s", seasons_to_team_ids)
        season_tasks = [
            extract_games_links_from_seasons_pages(session, season, team_id)
            for season, team_id in seasons_to_team_ids.items()
        ]
        results_per_season = await asyncio.gather(*season_tasks)
    return [game for season_games in results_per_season for game in season_games]


def main() -> None:
    logging.basicConfig(format="%(asctime)s : %(levelname)s : %(message)s", level=logging.INFO)
    parser = argparse.ArgumentParser(description="Crawl basket.co.il for Maccabi games.")
    parser.add_argument("--season", choices=("latest", "all"), default="latest")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap the number of most-recent games (latest mode only).")
    parser.add_argument("--output", type=Path, required=True, help="Path to write JSON output.")
    parser.add_argument("--unknown-teams-report", type=Path, default=None,
                        help="On unmapped team names, write the affected games as JSON here "
                             "(consumed by CI to alert the error channel).")
    args = parser.parse_args()

    try:
        if args.season == "latest":
            games = _run_latest_season(args.limit)
        else:
            games = asyncio.run(_run_all_seasons())
    except UnknownTeamNameError as error:
        write_unknown_teams_report(args.unknown_teams_report, error.affected_games)
        raise

    write_pydantic_list_as_json(games, args.output)


if __name__ == "__main__":
    main()
