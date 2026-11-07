"""The Israeli Premier League table as the league's own site, football.co.il, publishes it.

The site's stats page loads its table from the bamboo-cloud API below. Unlike livescore, it
follows IFA rulings: technical wins and points deductions are already in its numbers.
Its archive is not always sane (2025/26 shows a team with 98 games and an all-zero regular
season), so every table is checked before it is used.
"""
import json
from dataclasses import dataclass

import requests

_STANDINGS_API = "https://cdnapi.bamboo-cloud.com/api/football/standings"
_SITE_IID = "573881b7181f46ae4c8b4567"
_PREMIER_LEAGUE_TOURNAMENT_ID = 902
_USER_AGENT = "MaccabiPediaBot/1.0 (https://www.maccabipedia.co.il; league table)"

_TEAMS_IN_LEAGUE = 14
_MAX_GAMES_IN_SEASON = 36
# Once the playoffs start, the two playoff rounds hold full-season totals; until then, the
# regular season. A round with no games yet does not count as started.
_PLAYOFF_STAGES = ("ChampionshipRound", "RelegationRound")
_REGULAR_SEASON = "RegularSeason"

# By the site's team id, which stays the same across seasons while its names switch between
# English and Hebrew short forms ("מכבי ת\"א").
TEAM_ID_TO_HEBREW = {
    4524: "בית\"ר ירושלים",
    4530: "הפועל תל אביב",
    4536: "מכבי תל אביב",
    4539: "מכבי חיפה",
    4542: "הפועל פתח תקווה",
    4545: "מכבי נתניה",
    4548: "מ.ס. אשדוד",
    4551: "הפועל רמת גן",
    4554: "הפועל באר שבע",
    4563: "עירוני קריית שמונה",
    7020: "הפועל ירושלים",
    12039: "עירוני טבריה",
    14316: "הפועל חיפה",
    15006: "מכבי פתח תקווה",
    15960: "בני סכנין",
    22998: "הפועל חדרה",
    30249: "מכבי בני ריינה",
}


@dataclass(frozen=True)
class TeamRow:
    name: str
    played: int
    win: int
    draw: int
    loss: int
    goals_for: int
    goals_against: int
    points: int

    def as_template_row(self) -> str:
        """One row of תבנית:טבלת ליגת כדורגל: name^played^W^D^L^GF^GA^points."""
        return "^".join(str(value) for value in (
            self.name, self.played, self.win, self.draw, self.loss,
            self.goals_for, self.goals_against, self.points))


def fetch_standings(season_name: str) -> dict[str, list[dict]]:
    """The site's standings for a season ("26/27"), by stage name."""
    response = requests.get(_STANDINGS_API, headers={"User-Agent": _USER_AGENT}, timeout=30, params={
        "format": "json", "iid": _SITE_IID, "returnZeros": "true",
        "filter": json.dumps({"tournamentId": _PREMIER_LEAGUE_TOURNAMENT_ID, "seasonName": season_name})})
    if response.status_code != 200 or "application/json" not in response.headers.get("Content-Type", ""):
        raise RuntimeError(f"football.co.il answered {response.status_code} for {season_name}: {response.text[:500]}")
    return response.json()["data"]


def _team_row(row: dict) -> TeamRow:
    if row["id"] not in TEAM_ID_TO_HEBREW:
        raise ValueError(f"No Hebrew name for football.co.il team {row['id']} ({row['name']}, {row['hebrewName']}); "
                         f"add it to TEAM_ID_TO_HEBREW")
    team = TeamRow(TEAM_ID_TO_HEBREW[row["id"]], row["gamesCount"], row["wins"], row["draws"], row["losses"],
                   row["goalsScored"], row["goalsReceived"], row["points"])
    # A deduction can only lower the points, never raise them.
    if (team.win + team.draw + team.loss != team.played or team.played > _MAX_GAMES_IN_SEASON
            or team.points > team.win * 3 + team.draw):
        raise ValueError(f"football.co.il row does not add up: {team.as_template_row()}")
    return team


def league_table(standings: dict[str, list[dict]]) -> list[TeamRow]:
    """The table to show, in the site's order: both playoff rounds once they started, else the regular season."""
    def by_position(stage: str) -> list[dict]:
        return sorted(standings.get(stage, []), key=lambda row: row["position"])

    playoffs = [row for stage in _PLAYOFF_STAGES for row in by_position(stage)]
    started = any(row["gamesCount"] for row in playoffs)
    rows = [_team_row(row) for row in (playoffs if started else by_position(_REGULAR_SEASON))]
    names = [row.name for row in rows]
    if len(rows) != _TEAMS_IN_LEAGUE or len(set(names)) != len(names):
        raise ValueError(f"football.co.il table should list {_TEAMS_IN_LEAGUE} different teams, got {names}")
    return rows
