"""The basketball error finder, on games the 2026-11 audit of the wiki found (and some it got wrong)."""
from datetime import date

from maccabipediabot.basketball.error_finder import BasketballErrorsFinder
from maccabipediabot.basketball.error_finder.games import record_from_cargo

_PERIODS = ("First", "Second", "Third", "Fourth")


def _side(raw: dict, side: str, total=None, quarters=(), halves=(), overtimes=()) -> None:
    raw[f"TotalPoints{side}"] = total
    for period, points in zip(_PERIODS, quarters):
        raw[f"{period}QuarterPoints{side}"] = points
    for period, points in zip(_PERIODS, halves):
        raw[f"{period}HalfPoints{side}"] = points
    for period, points in zip(_PERIODS, overtimes):
        raw[f"{period}OvertimePoints{side}"] = points


def _game(page: str, *, season: str, opponent: str, home_away: str, competition: str | None = None,
          maccabi: dict | None = None, rival: dict | None = None, technical=None, leg="", day: str | None = None):
    """A Cargo row as Special:CargoExport returns it. Date and competition come from the title unless given."""
    title_day, rest = page.removeprefix("כדורסל:").split(" ", 1)
    dd, mm, yyyy = title_day.split("-")
    raw = {"_pageName": page, "Date": day if day is not None else f"{yyyy}-{mm}-{dd}", "Season": season,
           "Competition": competition if competition is not None else rest.rsplit(" - ", 1)[1],
           "Leg": leg, "Opponent": opponent, "HomeAway": home_away, "Technical": technical}
    _side(raw, "Maccabi", **(maccabi or {"total": 80}))
    _side(raw, "Opponent", **(rival or {"total": 70}))
    return record_from_cargo(raw)


def _found(games, check: str) -> list[str]:
    return [finding.game.page_name for finding in getattr(BasketballErrorsFinder(games), check)()]


# 1969: tied 60:60 after the halves, 65:67 at the end, overtime never filled in.
HAPOEL_1969 = _game("כדורסל:01-04-1969 הפועל תל אביב נגד מכבי תל אביב - הליגה הלאומית", season="1968/69",
                    opponent="הפועל תל אביב", home_away="חוץ",
                    maccabi={"total": 65, "halves": (22, 38)}, rival={"total": 67, "halves": (29, 31)})
# 1955: two overtimes stored (4:4, then 5:0). The audit flagged it for ignoring them.
HAIFA_1955 = _game("כדורסל:21-10-1955 מכבי תל אביב נגד הפועל חיפה - הליגה הארצית", season="1955",
                   opponent="הפועל חיפה", home_away="בית",
                   maccabi={"total": 73, "halves": (32, 32), "overtimes": (4, 5)},
                   rival={"total": 68, "halves": (28, 36), "overtimes": (4, 0)})
# 2006: quarters tie 90:90, final 106:101, no overtime stored.
UNICAJA_2006 = _game("כדורסל:26-10-2006 מכבי תל אביב נגד אוניקאחה מאלגה - יורוליג", season="2006/07",
                     opponent="אוניקאחה מאלגה", home_away="בית",
                     maccabi={"total": 106, "quarters": (34, 15, 25, 16)},
                     rival={"total": 101, "quarters": (16, 33, 24, 17)})
# 1984: Maccabi's halves give 91, the total is 89 — one side off, not an overtime.
GAN_SHMUEL_1984 = _game("כדורסל:01-10-1984 הפועל גן שמואל נגד מכבי תל אביב - הליגה הלאומית", season="1984/85",
                        opponent="הפועל גן שמואל", home_away="חוץ",
                        maccabi={"total": 89, "halves": (47, 44)}, rival={"total": 70, "halves": (35, 35)})


class TestPeriodsAgainstTotal:
    def test_tied_regulation_without_overtime_points_is_missing_overtime(self):
        assert _found([HAPOEL_1969, UNICAJA_2006], "get_games_missing_overtime") == [
            HAPOEL_1969.page_name, UNICAJA_2006.page_name]

    def test_missing_overtime_is_not_reported_again_as_a_mismatch(self):
        games = [HAPOEL_1969, UNICAJA_2006]
        assert _found(games, "get_games_with_halves_not_matching_total") == []
        assert _found(games, "get_games_with_quarters_not_matching_total") == []

    def test_stored_overtimes_count_towards_the_total(self):
        finder = BasketballErrorsFinder([HAIFA_1955])
        assert finder.get_games_missing_overtime() == []
        assert finder.get_games_with_halves_not_matching_total() == []
        assert finder.get_games_with_overtime_after_untied_regulation() == []

    def test_one_side_off_is_a_halves_mismatch(self):
        findings = BasketballErrorsFinder([GAN_SHMUEL_1984]).get_games_with_halves_not_matching_total()
        assert [finding.detail for finding in findings] == ["Maccabi: halves [47, 44] + overtime 0 = 91, total 89"]

    def test_a_half_left_empty_is_a_mismatch(self):
        givat_shmuel = _game("כדורסל:25-10-1998 מכבי תל אביב נגד גבעת שמואל - ליגה לאומית א", season="1998/99",
                             opponent="גבעת שמואל", home_away="בית",
                             maccabi={"total": 90, "halves": (45, 45)}, rival={"total": 58, "halves": (None, 27)})
        assert _found([givat_shmuel], "get_games_with_halves_not_matching_total") == [givat_shmuel.page_name]

    def test_games_without_periods_are_not_checked(self):
        no_periods = _game("כדורסל:14-08-1953 מכבי דרום תל אביב נגד מכבי תל אביב - הליגה הארצית", season="1953/54",
                           opponent="מכבי דרום תל אביב", home_away="חוץ")
        finder = BasketballErrorsFinder([no_periods])
        assert finder.get_games_with_halves_not_matching_total() == []
        assert finder.get_games_with_quarters_not_matching_total() == []
        assert finder.get_games_missing_overtime() == []

    def test_halves_must_be_the_sum_of_their_quarters(self):
        game = _game("כדורסל:22-11-2007 מכבי תל אביב נגד ציבונה זאגרב - יורוליג", season="2007/08",
                     opponent="ציבונה זאגרב", home_away="בית",
                     maccabi={"total": 82, "quarters": (21, 19, 30, 12), "halves": (41, 41)},
                     rival={"total": 70, "quarters": (20, 15, 20, 15), "halves": (35, 35)})
        findings = BasketballErrorsFinder([game, HAIFA_1955]).get_games_with_halves_not_matching_quarters()
        assert [finding.detail for finding in findings] == ["Maccabi: halves [41, 41], quarters give [40, 42]"]

    def test_overtime_after_an_untied_regulation(self):
        haifa = _game("כדורסל:11-06-2014 מכבי תל אביב נגד מכבי חיפה - ליגת העל", season="2013/14",
                      opponent="מכבי חיפה", home_away="בית",
                      maccabi={"total": 82, "quarters": (20, 20, 20, 15), "overtimes": (7,)},
                      rival={"total": 84, "quarters": (20, 20, 20, 19), "overtimes": (5,)})
        assert _found([haifa], "get_games_with_overtime_after_untied_regulation") == [haifa.page_name]


class TestResult:
    CUP_1991 = _game("כדורסל:09-12-1991 מכבי תל אביב נגד הפועל תל אביב - גביע המדינה", season="1991/92",
                     opponent="הפועל תל אביב", home_away="בית", leg="רבע גמר - משחק 1",
                     maccabi={"total": 85}, rival={"total": 85})

    def test_a_tie_is_reported_with_its_leg(self):
        findings = BasketballErrorsFinder([self.CUP_1991, HAPOEL_1969]).get_games_with_tie_result()
        assert [finding.detail for finding in findings] == ["85:85, leg 'רבע גמר - משחק 1'"]

    def test_technical_games_are_skipped(self):
        technical = _game("כדורסל:28-09-2023 הפועל תל אביב נגד מכבי תל אביב - גביע ווינר", season="2023/24",
                          competition="גביע ווינר סל", opponent="הפועל תל אביב", home_away="חוץ", technical=1,
                          maccabi={"total": None}, rival={"total": None})
        finder = BasketballErrorsFinder([technical])
        assert finder.get_games_with_tie_result() == []
        assert finder.get_games_without_result() == []

    def test_a_game_without_a_total_has_no_result(self):
        no_score = _game("כדורסל:16-03-1971 מכבי תל אביב נגד הפועל ניר דוד - הליגה הלאומית", season="1970/71",
                         opponent="הפועל ניר דוד", home_away="בית", maccabi={"total": None})
        assert _found([no_score], "get_games_without_result") == [no_score.page_name]


class TestTitle:
    def test_a_differently_spelled_opponent_is_reported(self):
        beitar = _game("כדורסל:15-10-1971 ביתר י-ם נגד מכבי תל אביב - הליגה הלאומית", season="1971/72",
                       opponent="בית&quot;ר ירושלים", home_away="חוץ")
        findings = BasketballErrorsFinder([beitar]).get_games_with_title_opponent_not_matching_opponent()
        assert [finding.detail for finding in findings] == ["title 'ביתר י-ם', Opponent 'בית\"ר ירושלים'"]

    def test_quotes_and_their_html_escapes_are_the_same_name(self):
        cska = _game("כדורסל:21-02-2008 צסק\"א מוסקבה נגד מכבי תל אביב - יורוליג", season="2007/08",
                     opponent="צסק&quot;א מוסקבה", home_away="חוץ")
        assert _found([cska], "get_games_with_title_opponent_not_matching_opponent") == []

    def test_the_winner_cup_title_convention_is_not_an_error(self):
        winner = _game("כדורסל:15-10-2007 מכבי תל אביב נגד הפועל ירושלים - גביע ווינר", season="2007/08",
                       competition="גביע ווינר סל", opponent="הפועל ירושלים", home_away="בית")
        league_cup = _game("כדורסל:11-10-2010 מכבי תל אביב נגד מכבי ראשון לציון - גביע ווינר", season="2010/11",
                           competition="גביע הליגה", opponent="מכבי ראשון לציון", home_away="נייטרלי")
        assert _found([winner, league_cup], "get_games_with_title_competition_not_matching_competition") == [
            league_cup.page_name]

    def test_title_names_the_home_team_first(self):
        named_first_away = _game("כדורסל:14-08-1953 מכבי תל אביב נגד מכבי דרום תל אביב - הליגה הארצית",
                                 season="1953/54", opponent="מכבי דרום תל אביב", home_away="חוץ")
        neutral = _game("כדורסל:11-10-2010 מכבי תל אביב נגד מכבי ראשון לציון - גביע ווינר", season="2010/11",
                        competition="גביע ווינר סל", opponent="מכבי ראשון לציון", home_away="נייטרלי")
        assert _found([named_first_away, neutral, HAPOEL_1969],
                      "get_games_with_title_order_not_matching_home_away") == [named_first_away.page_name]

    def test_title_date_against_the_date_field(self):
        wrong_day = _game("כדורסל:21-10-1955 מכבי תל אביב נגד הפועל חיפה - הליגה הארצית", season="1955",
                          opponent="הפועל חיפה", home_away="בית", day="1955-10-22")
        assert _found([wrong_day, HAIFA_1955], "get_games_with_title_date_not_matching_date") == [wrong_day.page_name]

    def test_titles_that_do_not_parse_or_lack_maccabi(self):
        no_maccabi = _game("כדורסל:21-10-1955 מכבי ת\"א נגד הפועל חיפה - הליגה הארצית", season="1955",
                           opponent="הפועל חיפה", home_away="בית")
        finder = BasketballErrorsFinder([no_maccabi])
        assert [f.game for f in finder.get_games_without_maccabi_in_title()] == [no_maccabi]
        assert finder.get_games_with_bad_title_format() == []
        broken = record_from_cargo({"_pageName": "כדורסל:מכבי תל אביב נגד הפועל חיפה", "Date": "1955-10-21",
                                    "Season": "1955"})
        assert _found([broken], "get_games_with_bad_title_format") == [broken.page_name]


class TestDatesAndSeasons:
    def _in_season(self, day: str, season: str):
        return _game(f"כדורסל:{day} מכבי תל אביב נגד הפועל חולון - הליגה הלאומית", season=season,
                     opponent="הפועל חולון", home_away="בית")

    def test_a_game_before_its_season_started(self):
        early = self._in_season("24-04-1953", "1953/54")
        assert _found([early], "get_games_with_date_outside_season") == [early.page_name]

    def test_summer_seasons_and_two_year_seasons_are_in_season(self):
        games = [self._in_season("01-08-1961", "1960/61"),  # the early leagues ran over the summer
                 self._in_season("06-11-1959", "1958/60"),  # one season over two years
                 self._in_season("05-01-2000", "1999/00"),
                 self._in_season("21-10-1955", "1955")]
        assert _found(games, "get_games_with_date_outside_season") == []

    def test_a_cup_game_months_after_its_season_ended(self):
        late = self._in_season("15-11-1961", "1960/61")
        assert _found([late], "get_games_with_date_outside_season") == [late.page_name]

    def test_an_unreadable_season(self):
        odd = self._in_season("21-10-1955", "1955-56")
        assert [f.check for f in BasketballErrorsFinder([odd]).get_games_with_date_outside_season()] == ["season_format"]

    def test_two_games_on_one_date(self):
        games = [_game("כדורסל:16-03-1971 מכבי תל אביב נגד הפועל ניר דוד - הליגה הלאומית", season="1970/71",
                       opponent="הפועל ניר דוד", home_away="בית"),
                 _game("כדורסל:16-03-1971 מכבי תל אביב נגד הפועל תל אביב - הליגה הלאומית", season="1970/71",
                       opponent="הפועל תל אביב", home_away="בית"),
                 HAPOEL_1969]
        assert len(_found(games, "get_dates_with_more_than_one_game")) == 2

    def test_empty_fields(self):
        game = _game("כדורסל:16-03-1971 מכבי תל אביב נגד הפועל ניר דוד - הליגה הלאומית", season="",
                     opponent="", home_away="בית")
        findings = BasketballErrorsFinder([game]).get_games_with_empty_fields()
        assert [finding.detail for finding in findings] == ["Season, Opponent"]
        assert game.date == date(1971, 3, 16)


def test_find_all_runs_every_check():
    results = BasketballErrorsFinder([HAPOEL_1969]).find_all()
    checks = {name for name in dir(BasketballErrorsFinder) if name.startswith("get_")}
    assert set(results) == checks
    assert len(results["get_games_missing_overtime"]) == 1
