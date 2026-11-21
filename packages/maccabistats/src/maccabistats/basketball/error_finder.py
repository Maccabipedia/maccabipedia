"""Find data errors in the basketball games on MaccabiPedia.

The basketball counterpart of the football ``ErrorsFinder``: every public
``get_*`` method is one check, and ``find_all`` runs them all. It only reads; fixing
what it finds is a separate, sourced job per game.
"""
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date

from maccabistats.basketball.models import (
    AWAY,
    HOME,
    MACCABI_NAME,
    PLAYER_STATS,
    BasketballGameData,
)
from maccabistats.basketball.stats import BasketballGamesStats
from maccabistats.basketball.titles import basketball_title_competition

_TITLE = re.compile(r"^כדורסל:(\d\d)-(\d\d)-(\d{4}) (.+?) נגד (.+?) - (.+)$")
_SPLIT_SEASON = re.compile(r"^(\d{4})/(\d{2})$")
_CALENDAR_SEASON = re.compile(r"^\d{4}$")
_REQUIRED_FIELDS = {"date": "Date", "season": "Season", "competition": "Competition",
                    "opponent": "Opponent", "home_away": "HomeAway"}

# A split season ("1960/61") runs from this day of its first year to this day of its last.
# The early seasons were played across the summer, so the window is wide on purpose:
# a game outside it is filed under the wrong season, or its date is wrong.
_SEASON_FIRST_DAY = (6, 1)
_SEASON_LAST_DAY = (9, 30)

# From this day on every game page should list its players: box scores are published for every
# game since. Before it, most games' box scores were never published, so a page without one is
# not an error. (The old European games can be filled from Linguasport, as a backfill.)
_BOX_SCORE_EXPECTED_FROM = date(2000, 1, 1)


_SHOTS = {"two-pointers": ("two_points_scored", "two_points_attempts"),
          "three-pointers": ("three_points_scored", "three_points_attempts"),
          "free throws": ("free_throws_scored", "free_throws_attempts")}


@dataclass(frozen=True)
class Finding:
    check: str
    # None only for a box-score row that belongs to no game; page_name is then the row's page
    game: BasketballGameData | None
    detail: str
    page_name_without_game: str | None = None

    @property
    def page_name(self) -> str:
        return self.game.page_name if self.game else self.page_name_without_game

    @property
    def season(self) -> str | None:
        return self.game.season if self.game else None


def _normalize_team(name: str) -> str:
    """Drop what titles and Cargo spell differently by convention: quotes, slashes, spaces."""
    return re.sub(r"[\"'/ ״׳]", "", name)


def _filled(points: tuple[int | None, ...]) -> bool:
    return any(value for value in points)


def _complete(points: tuple[int | None, ...]) -> bool:
    """Every period filled in. Only then can a sum say how regulation ended."""
    return None not in points and _filled(points)


def _season_window(season: str) -> tuple[date, date] | None:
    if _CALENDAR_SEASON.match(season):
        year = int(season)
        return date(year, 1, 1), date(year, 12, 31)
    match = _SPLIT_SEASON.match(season)
    if not match:
        return None
    first_year = int(match.group(1))
    last_year = first_year - first_year % 100 + int(match.group(2))
    if last_year < first_year:  # 1999/00
        last_year += 100
    return date(first_year, *_SEASON_FIRST_DAY), date(last_year, *_SEASON_LAST_DAY)


class BasketballErrorsFinder:
    """Each public ``get_*`` method is one check; ``find_all`` runs every one of them."""

    def __init__(self, basketball_games_stats: BasketballGamesStats) -> None:
        self.basketball_games_stats = basketball_games_stats
        games = self.games = basketball_games_stats.games
        self.player_rows_without_game = basketball_games_stats.player_rows_without_game
        self._scored_games = [game for game in games if not game.is_technical and game.has_score]

    # --- Periods against the final score -------------------------------------------------

    def _missing_overtime(self, game: BasketballGameData, periods: str) -> bool:
        """Tied after regulation, both teams scored more than that, and no overtime points stored."""
        maccabi, opponent = getattr(game.maccabi, periods), getattr(game.opponent_team, periods)
        if not (_complete(maccabi) and _complete(opponent)):
            return False
        regulation = sum(value or 0 for value in maccabi)
        return (regulation == sum(value or 0 for value in opponent)
                and game.maccabi.overtime_points == game.opponent_team.overtime_points == 0
                and game.maccabi.score > regulation and game.opponent_team.score > regulation)

    def get_games_missing_overtime(self) -> list[Finding]:
        """Periods add up to a tie, the final score is not one, and the overtime points were never filled in."""
        findings = []
        for game in self._scored_games:
            for periods in ("quarters", "halves"):
                if self._missing_overtime(game, periods):
                    regulation = sum(value or 0 for value in getattr(game.maccabi, periods))
                    findings.append(Finding("missing_overtime", game,
                                            f"{periods} add up to {regulation}:{regulation}, "
                                            f"final {game.maccabi.score}:{game.opponent_team.score}, no overtime points"))
                    break
        return findings

    def _periods_against_total(self, periods: str) -> list[Finding]:
        findings = []
        for game in self._scored_games:
            if self._missing_overtime(game, "quarters") or self._missing_overtime(game, "halves"):
                continue  # reported once, by get_games_missing_overtime
            mismatches = []
            for side_name, side in (("Maccabi", game.maccabi), ("Opponent", game.opponent_team)):
                points = getattr(side, periods)
                if not _filled(points):
                    continue
                periods_sum = sum(value or 0 for value in points)
                if periods_sum + side.overtime_points != side.score:
                    shown = [value if value is not None else "-" for value in points]
                    mismatches.append(f"{side_name}: {periods} {shown} + overtime {side.overtime_points} "
                                      f"= {periods_sum + side.overtime_points}, total {side.score}")
            if mismatches:
                findings.append(Finding(f"{periods}_vs_total", game, "; ".join(mismatches)))
        return findings

    def get_games_with_quarters_not_matching_total(self) -> list[Finding]:
        return self._periods_against_total("quarters")

    def get_games_with_halves_not_matching_total(self) -> list[Finding]:
        return self._periods_against_total("halves")

    def get_games_with_partly_filled_periods(self) -> list[Finding]:
        """Some quarters (or halves) of a side filled in and others left empty.

        Catches a period's points typed into the wrong slot even when the total still adds up:
        Chalon 2012 has the opponent's fourth quarter empty and its 12 points in the first overtime.
        """
        findings = []
        for game in self._scored_games:
            gaps = []
            for side_name, side in (("Maccabi", game.maccabi), ("Opponent", game.opponent_team)):
                for periods in ("quarters", "halves"):
                    points = getattr(side, periods)
                    if _filled(points) and None in points:
                        gaps.append(f"{side_name}: {periods} {[v if v is not None else '-' for v in points]}")
            if gaps:
                findings.append(Finding("partly_filled_periods", game, "; ".join(gaps)))
        return findings

    def get_games_with_halves_not_matching_quarters(self) -> list[Finding]:
        """Both halves and quarters are filled in, and a half is not the sum of its two quarters."""
        findings = []
        for game in self._scored_games:
            mismatches = []
            for side_name, side in (("Maccabi", game.maccabi), ("Opponent", game.opponent_team)):
                if None in side.quarters or None in side.halves or not _filled(side.quarters):
                    continue
                from_quarters = (side.quarters[0] + side.quarters[1], side.quarters[2] + side.quarters[3])
                if from_quarters != side.halves:
                    mismatches.append(f"{side_name}: halves {list(side.halves)}, quarters give {list(from_quarters)}")
            if mismatches:
                findings.append(Finding("halves_vs_quarters", game, "; ".join(mismatches)))
        return findings

    def get_games_with_overtime_after_untied_regulation(self) -> list[Finding]:
        """Overtime points stored, but the regulation periods do not end in a tie."""
        findings = []
        for game in self._scored_games:
            if not (game.maccabi.overtime_points or game.opponent_team.overtime_points):
                continue
            for periods in ("quarters", "halves"):
                maccabi, opponent = getattr(game.maccabi, periods), getattr(game.opponent_team, periods)
                if not (_complete(maccabi) and _complete(opponent)):
                    continue
                maccabi_sum, opponent_sum = sum(v or 0 for v in maccabi), sum(v or 0 for v in opponent)
                if maccabi_sum != opponent_sum:
                    findings.append(Finding("overtime_after_untied_regulation", game,
                                            f"{periods} add up to {maccabi_sum}:{opponent_sum}, "
                                            f"overtime {game.maccabi.overtime_points}:{game.opponent_team.overtime_points}"))
                break
        return findings

    # --- The result ------------------------------------------------------------------------

    def get_games_with_tie_result(self) -> list[Finding]:
        """A basketball game cannot end in a tie (one leg of a two-legged tie once could; the Leg says which)."""
        return [Finding("tie_result", game, f"{game.maccabi.score}:{game.opponent_team.score}, leg '{game.leg or ''}'")
                for game in self._scored_games if game.maccabi.score == game.opponent_team.score]

    def get_games_without_result(self) -> list[Finding]:
        """No final score, or the 0:0 a page stores when nobody entered one."""
        return [Finding("no_result", game, f"TotalPoints {game.maccabi.score}:{game.opponent_team.score}")
                for game in self.games if not game.is_technical and not game.has_score]

    def get_games_with_result_opt_not_matching_result(self) -> list[Finding]:
        """The stored ResultOpt (1 win, 2 tie, 3 loss) against the result the game model gives."""
        findings = []
        for game in self.games:
            if not game.has_result:
                continue
            expected = 1 if game.is_maccabi_win else 3 if game.is_maccabi_loss else 2
            if game.result_opt != expected:
                findings.append(Finding("result_opt", game,
                                        f"ResultOpt {game.result_opt}, expected {expected} from "
                                        f"{game.maccabi.score}:{game.opponent_team.score}, Technical {game.technical}"))
        return findings

    # --- The competition -------------------------------------------------------------------

    def get_games_with_competition_missing_from_catalog(self) -> list[Finding]:
        """The game names a competition that has no row in Basketball_Competitions, so it has no flags."""
        return [Finding("competition_not_in_catalog", game, f"Competition '{game.competition}'")
                for game in self.games if game.competition and game.competition_flags is None]

    # --- The title against the fields ------------------------------------------------------

    def _titled_games(self):
        for game in self.games:
            match = _TITLE.match(game.page_name)
            if match:
                yield game, match.groups()

    def get_games_with_bad_title_format(self) -> list[Finding]:
        return [Finding("title_format", game, "not 'כדורסל:DD-MM-YYYY X נגד Y - competition'")
                for game in self.games if not _TITLE.match(game.page_name)]

    def get_games_with_title_date_not_matching_date(self) -> list[Finding]:
        return [Finding("title_date", game, f"title {day}-{month}-{year}, Date {game.date}")
                for game, (day, month, year, *_rest) in self._titled_games()
                if game.date and f"{year}-{month}-{day}" != game.date.isoformat()]

    def get_games_with_title_competition_not_matching_competition(self) -> list[Finding]:
        """Allows the short names titles use by convention (גביע ווינר סל → גביע ווינר)."""
        return [Finding("title_competition", game, f"title '{competition}', Competition '{game.competition or ''}'")
                for game, (*_rest, competition) in self._titled_games()
                if competition.strip() != basketball_title_competition(game.competition or "")]

    def get_games_without_maccabi_in_title(self) -> list[Finding]:
        return [Finding("title_no_maccabi", game, f"'{first}' / '{second}'")
                for game, (_d, _m, _y, first, second, _c) in self._titled_games()
                if MACCABI_NAME not in (first, second)]

    def get_games_with_title_opponent_not_matching_opponent(self) -> list[Finding]:
        findings = []
        for game, (_d, _m, _y, first, second, _c) in self._titled_games():
            if MACCABI_NAME not in (first, second) or first == second:
                continue
            title_opponent = second if first == MACCABI_NAME else first
            if _normalize_team(title_opponent) != _normalize_team(game.opponent or ""):
                findings.append(Finding("title_opponent", game,
                                        f"title '{title_opponent}', Opponent '{game.opponent or ''}'"))
        return findings

    def get_games_with_title_order_not_matching_home_away(self) -> list[Finding]:
        """Titles name the home team first: a home game starts with Maccabi, an away game ends with it."""
        findings = []
        for game, (_d, _m, _y, first, second, _c) in self._titled_games():
            if MACCABI_NAME not in (first, second):
                continue
            maccabi_first = first == MACCABI_NAME
            if (game.home_away == HOME and not maccabi_first) or (game.home_away == AWAY and maccabi_first):
                findings.append(Finding("title_order_vs_home_away", game,
                                        f"HomeAway '{game.home_away}', Maccabi named {'first' if maccabi_first else 'second'}"))
        return findings

    # --- Dates and seasons -----------------------------------------------------------------

    def get_games_with_date_outside_season(self) -> list[Finding]:
        findings = []
        for game in self.games:
            if not game.date or not game.season:
                continue
            window = _season_window(game.season)
            if window is None:
                findings.append(Finding("season_format", game, f"Season '{game.season}'"))
            elif not window[0] <= game.date <= window[1]:
                findings.append(Finding("date_outside_season", game,
                                        f"Date {game.date}, Season {game.season} ({window[0]}..{window[1]})"))
        return findings

    def get_dates_with_more_than_one_game(self) -> list[Finding]:
        games_by_date = defaultdict(list)
        for game in self.games:
            if game.date:
                games_by_date[game.date].append(game)
        return [Finding("same_date", game, f"{len(games)} games on {day}")
                for day, games in games_by_date.items() if len(games) > 1 for game in games]

    def get_games_with_empty_fields(self) -> list[Finding]:
        findings = []
        for game in self.games:
            empty = [cargo_name for attribute, cargo_name in _REQUIRED_FIELDS.items() if not getattr(game, attribute)]
            if empty:
                findings.append(Finding("empty_field", game, ", ".join(empty)))
        return findings

    # --- The players' box scores -----------------------------------------------------------

    def _sides(self):
        for game in self.games:
            for side_name, side in (("Maccabi", game.maccabi), ("Opponent", game.opponent_team)):
                if side.players:
                    yield game, side_name, side

    def get_games_with_players_points_not_matching_total(self) -> list[Finding]:
        """The players' points against the team's score.

        Old box scores often leave a player's points empty, so a side is short only when every
        player who played has points; more points than the score is wrong either way.
        """
        scored_games = {id(game) for game in self._scored_games}
        findings = []
        for game, side_name, side in self._sides():
            known_points = [player.points for player in side.players if player.points is not None]
            # A side whose points are all 0 did not record them (old box scores store 0 for that)
            if id(game) not in scored_games or not side.has_recorded("points"):
                continue
            players_points = sum(known_points)
            every_player_has_points = all(player.points is not None for player in side.played_players)
            if players_points > side.score or (every_player_has_points and players_points != side.score):
                findings.append(Finding("players_points_vs_total", game,
                                        f"{side_name}: players have {players_points}, total {side.score}"))
        return findings

    def get_players_with_more_scored_than_attempts(self) -> list[Finding]:
        findings = []
        for game, side_name, side in self._sides():
            for player in side.players:
                for shot, (scored_stat, attempts_stat) in _SHOTS.items():
                    scored, attempts = getattr(player, scored_stat), getattr(player, attempts_stat)
                    if scored is not None and attempts is not None and scored > attempts:
                        findings.append(Finding("scored_more_than_attempts", game,
                                                f"{side_name}: {player.name} {shot} {scored}/{attempts}"))
        return findings

    def get_players_with_rebounds_not_matching_total(self) -> list[Finding]:
        """Offensive and defensive rebounds recorded, and they do not add up to the total."""
        findings = []
        for game, side_name, side in self._sides():
            for player in side.players:
                offensive, defensive = player.offensive_rebounds or 0, player.defensive_rebounds or 0
                if (offensive or defensive) and offensive + defensive != player.rebounds:
                    findings.append(Finding("rebounds_vs_total", game,
                                            f"{side_name}: {player.name} {offensive} + {defensive}, total {player.rebounds}"))
        return findings

    def get_players_who_did_not_play_with_stats(self) -> list[Finding]:
        findings = []
        for game, side_name, side in self._sides():
            for player in side.players:
                stats = {stat: getattr(player, stat) for stat in PLAYER_STATS if getattr(player, stat)}
                if not player.is_played and stats:
                    findings.append(Finding("did_not_play_with_stats", game, f"{side_name}: {player.name} {stats}"))
        return findings

    def get_sides_with_starting_five_not_five(self) -> list[Finding]:
        """A side that marks starters at all should mark five of them."""
        findings = []
        for game, side_name, side in self._sides():
            starters = sum(player.is_starting_five for player in side.players)
            if starters not in (0, 5):
                findings.append(Finding("starting_five", game, f"{side_name}: {starters} starters"))
        return findings

    def get_sides_with_player_without_name(self) -> list[Finding]:
        findings = []
        for game, side_name, side in self._sides():
            nameless = sum(not player.name for player in side.players)
            if nameless:
                findings.append(Finding("player_without_name", game, f"{side_name}: {nameless} players"))
        return findings

    def get_sides_with_same_player_twice(self) -> list[Finding]:
        findings = []
        for game, side_name, side in self._sides():
            names = Counter(player.name for player in side.players if player.name)
            repeated = sorted(name for name, times in names.items() if times > 1)
            if repeated:
                findings.append(Finding("same_player_twice", game, f"{side_name}: {', '.join(repeated)}"))
        return findings

    def get_games_with_same_player_on_both_sides(self) -> list[Finding]:
        findings = []
        for game in self.games:
            on_both = sorted({player.name for player in game.maccabi.players if player.name}
                             & {player.name for player in game.opponent_team.players})
            if on_both:
                findings.append(Finding("player_on_both_sides", game, ", ".join(on_both)))
        return findings

    def get_games_without_box_score(self) -> list[Finding]:
        """A played game since 2000 with no player listed on either side."""
        return [Finding("no_box_score", game, "no players on either side")
                for game in self._scored_games
                if game.date is not None and game.date >= _BOX_SCORE_EXPECTED_FROM
                and not game.maccabi.players and not game.opponent_team.players]

    def get_player_rows_without_game(self) -> list[Finding]:
        """Box-score rows whose page has no game row, or whose Team is neither Maccabi (1) nor the opponent (0)."""
        return [Finding("player_row_without_game", None, f"{player.name}, Team {team}", page_name_without_game=page_name)
                for page_name, team, player in self.player_rows_without_game]

    # --- All of them -----------------------------------------------------------------------

    def find_all(self) -> dict[str, list[Finding]]:
        """Every check's findings, keyed by the method name."""
        checks = [name for name in dir(self) if name.startswith("get_") and callable(getattr(self, name))]
        return {name: getattr(self, name)() for name in sorted(checks)}

    def __repr__(self) -> str:
        return f"BasketballErrorsFinder({len(self.games)} games)"
