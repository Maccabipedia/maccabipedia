"""Tests for the 1-10 confidence score attached to every proposed match.

The score exists so a human can review the weakest matches first and trust the top of
the list. It is built from independent pieces of evidence, and the strongest piece —
the upload date — is the one the matcher never reads from the title.
"""
import pytest

from maccabipediabot.basketball.videos.cargo import GameRow
from maccabipediabot.basketball.videos.confidence import (
    Evidence,
    MAX_SCORE,
    MIN_SCORE,
    collect_evidence,
    score_all,
    score_match,
    title_year_agrees,
)
from maccabipediabot.basketball.videos.inventory import VideoEntry
from maccabipediabot.basketball.videos.matcher import Bucket, VideoMatch
from maccabipediabot.basketball.videos.title_parser import ParsedTitle, VideoKind


def row(opponent="אליצור נתניה", date="2024-11-22"):
    return GameRow(page_name="כדורסל:22-11-2024 x", date=date, season="2024/25",
                   opponent=opponent, competition="ליגת העל", leg="", home_away="בית",
                   maccabi_points=102, opponent_points=92, highlights=("", ""), full_games=("", ""))


def match(*, published=None, opponent_raw="אליצור נתניה", kind=VideoKind.HIGHLIGHTS,
          kind_override=None):
    entry = VideoEntry("v1", "title", 180, "2024/25", "p", published)
    parsed = ParsedTitle(kind, opponent_raw, 102, 92, "he")
    return VideoMatch(entry, parsed, Bucket.EXACT, "score and opponent agree",
                      page_name="כדורסל:22-11-2024 x", slot="תקציר וידאו",
                      kind_override=kind_override)


def test_the_best_possible_match_scores_ten():
    """Unique score, opponent recognised outright, uploaded the day of the game."""
    evidence = Evidence(score_unique_in_season=True, opponent_agrees=True,
                        )
    assert score_match(match(published="20241122"), row(), evidence) == MAX_SCORE


def test_no_date_costs_points_but_stays_respectable():
    evidence = Evidence(score_unique_in_season=True, opponent_agrees=True,
                        )
    scored = score_match(match(published=None), row(), evidence)
    assert MIN_SCORE < scored < MAX_SCORE


def test_an_archive_upload_scores_below_a_date_confirmed_one():
    """The archive upload must be LATER than the game. An earlier one takes the
    "uploaded before the game" branch instead, which would make this pass while leaving
    the archive path untested."""
    evidence = Evidence(score_unique_in_season=True, opponent_agrees=True)
    confirmed = score_match(match(published="20241122"), row(), evidence)
    archival = score_match(match(published=ARCHIVE_UPLOAD), row(date=ARCHIVE_GAME), evidence)
    assert MIN_SCORE < archival < confirmed


def test_a_date_that_contradicts_scores_the_minimum():
    """Uploaded before the game: whatever else agrees, this pairing cannot be right."""
    evidence = Evidence(score_unique_in_season=True, opponent_agrees=True,
                        )
    assert score_match(match(published="20200101"), row(), evidence) == MIN_SCORE


def test_a_shared_score_costs_points_only_when_the_name_was_loose():
    """Two games that season ended with this score and the opponent name only matched
    loosely, so nothing firmly picked between them."""
    strong = Evidence(score_unique_in_season=True, opponent_agrees=True,
                      opponent_exact=True, title_year_agrees=True)
    weak = Evidence(score_unique_in_season=False, opponent_agrees=True,
                    opponent_exact=False, title_year_agrees=True)
    game = row(date=ARCHIVE_GAME)
    assert score_match(match(published=ARCHIVE_UPLOAD), game, weak) < \
        score_match(match(published=ARCHIVE_UPLOAD), game, strong)


def test_a_shared_score_costs_nothing_when_the_opponent_matched_exactly():
    """1984/85 holds two games ending 88:87 — against Cibona Zagreb and against Hapoel
    Tel Aviv. A title naming Cibona has identified its game as firmly as a unique score
    would, five months and a different competition away from the other."""
    evidence = Evidence(score_unique_in_season=False, opponent_agrees=True,
                        opponent_exact=True, title_year_agrees=True)
    assert score_match(match(published=ARCHIVE_UPLOAD), row(date=ARCHIVE_GAME), evidence) == 9


def test_collect_evidence_marks_an_exact_name_as_exact():
    game = row(opponent="ציבונה זאגרב")
    exact = match(published=None, opponent_raw="ציבונה זאגרב")
    assert collect_evidence(exact, game, season_rows(game)).opponent_exact is True


def test_collect_evidence_marks_a_containment_name_as_not_exact():
    game = row(opponent="אליצור עירוני נתניה")
    loose = match(published=None, opponent_raw="נתניה")
    evidence = collect_evidence(loose, game, season_rows(game))
    assert evidence.opponent_agrees is True
    assert evidence.opponent_exact is False


def test_a_shared_score_costs_nothing_once_the_date_confirms():
    """The opponent picked between two same-score games, and an upload dated to the game
    itself confirms that pick from a direction the title cannot reach."""
    weak = Evidence(score_unique_in_season=False, opponent_agrees=True)
    assert score_match(match(published="20241122"), row(), weak) == MAX_SCORE


def test_an_opponent_that_does_not_agree_costs_points():
    recognised = Evidence(score_unique_in_season=True, opponent_agrees=True,
                          )
    passthrough = Evidence(score_unique_in_season=True, opponent_agrees=False,
                           )
    assert score_match(match(published="20241122"), row(), passthrough) < \
        score_match(match(published="20241122"), row(), recognised)


def season_rows(*rows):
    return list(rows)


def test_a_guessed_kind_does_not_change_the_score():
    """Whether the title stated the kind decides which parameter the link goes in, not
    whether the link belongs to this game. It used to cost a point, which held 655
    otherwise-perfect archive matches a rung below their real confidence.

    Goes through collect_evidence, so reintroducing a kind penalty there would fail this
    — asserting it against a hand-built Evidence would not."""
    game = row()
    stated = match(published="20241122", kind=VideoKind.HIGHLIGHTS)
    guessed = match(published="20241122", kind=None, kind_override=VideoKind.CONDENSED)
    stated_score = score_match(stated, game, collect_evidence(stated, game, season_rows(game)))
    guessed_score = score_match(guessed, game, collect_evidence(guessed, game, season_rows(game)))
    assert stated_score == guessed_score == MAX_SCORE


def test_an_era_variant_opponent_name_does_not_change_the_score():
    """Cargo spells the same club differently by era, so the alias table maps to the
    distinctive part of the name on purpose; matching by containment is the designed
    path, not a near miss. This exercises the real containment logic through
    collect_evidence rather than asserting a hand-set flag."""
    exact_game = row(opponent="אליצור נתניה")
    variant_game = row(opponent="אליצור עירוני נתניה")
    exact_match = match(published="20241122", opponent_raw="אליצור נתניה")
    variant_match = match(published="20241122", opponent_raw="נתניה")
    exact = score_match(exact_match, exact_game,
                        collect_evidence(exact_match, exact_game, season_rows(exact_game)))
    contained = score_match(variant_match, variant_game,
                            collect_evidence(variant_match, variant_game, season_rows(variant_game)))
    assert contained == exact == MAX_SCORE


def test_collect_evidence_reads_the_opponent_off_the_chosen_page():
    """Not merely whether the name parsed: a match made on the upload date alone can name
    a club the page does not, and that has to show up as evidence against."""
    game = row(opponent="הפועל חולון")
    disagreeing = match(published="20241122", opponent_raw="הפועל ירושלים")
    evidence = collect_evidence(disagreeing, game, season_rows(game))
    assert evidence.opponent_agrees is False


def test_a_contradicted_opponent_cannot_reach_the_unattended_write_floor():
    """The scheduled job writes at 9 with no human in the loop. A match whose title names
    a different club than the page must land below that however well the date lines up."""
    game = row(opponent="הפועל חולון")
    disagreeing = match(published="20241122", opponent_raw="הפועל ירושלים")
    scored = score_match(disagreeing, game, collect_evidence(disagreeing, game, season_rows(game)))
    assert scored < 9


def test_score_all_attaches_a_score_and_the_day_gap():
    game = row()
    scored_match = match(published="20241122")
    score_all([scored_match], [game])
    assert scored_match.confidence == MAX_SCORE
    assert scored_match.days_after_game == 0


@pytest.mark.parametrize("evidence", [
    Evidence(score_unique_in_season=False, opponent_agrees=False,
             ),
    Evidence(score_unique_in_season=True, opponent_agrees=True,
             ),
])
def test_the_score_always_stays_in_range(evidence):
    for published in (None, "20241122", "20150101", "20200101"):
        scored = score_match(match(published=published), row(), evidence)
        assert MIN_SCORE <= scored <= MAX_SCORE


def archive_evidence(year_agrees):
    return Evidence(score_unique_in_season=True, opponent_agrees=True,
                    title_year_agrees=year_agrees)


# A 1998 game put online in 2011: the upload is years late, which is the archive case.
ARCHIVE_GAME = "1998-10-01"
ARCHIVE_UPLOAD = "20110628"


def test_an_archive_match_is_lifted_when_the_title_year_agrees():
    """Archive uploads have no usable date, but their titles name the year, and the
    season used for matching came from the playlist rather than the title — so the year
    is independent evidence. Measured over the real channel: 494 archive matches carry a
    year and every one of them agrees."""
    game = row(date=ARCHIVE_GAME)
    without = score_match(match(published=ARCHIVE_UPLOAD), game, archive_evidence(None))
    with_year = score_match(match(published=ARCHIVE_UPLOAD), game, archive_evidence(True))
    assert with_year > without
    assert with_year == 9  # short of 10: a year is coarser than a date


def test_a_title_year_that_disagrees_sinks_the_score():
    scored = score_match(match(published=ARCHIVE_UPLOAD), row(date=ARCHIVE_GAME),
                         archive_evidence(False))
    assert scored <= MIN_SCORE + 1


def test_the_year_does_not_add_to_a_date_confirmed_match():
    """The date already pins the day; the year adds nothing on top of it."""
    evidence = archive_evidence(True)
    assert score_match(match(published="20241122"), row(), evidence) == MAX_SCORE


@pytest.mark.parametrize("title,game_date,expected", [
    ("גביע אירופה 1985,בית הגמר, מכבי - באנקו רומא 86:95", "1985-03-14", True),
    ("National League 1985, Round 15, Hapoel Holon - Maccabi 82:83", "1984-12-02", True),
    ("EuroLeague 1997, Group Stage, Maccabi vs CSKA 78:77", "1998-01-15", True),
    ("גביע המדינה 2010, משחק הגמר: מכבי - בני השרון 70:77", "2010-02-18", True),
    ("גביע אירופה 1985, מכבי - באנקו רומא 86:95", "1992-03-14", False),
    ("תקציר המשחק: מכבי - אליצור נתניה 92:102", "2024-11-22", None),
    # The channel writes the season in two digits too. Eighteen archive matches scored 7
    # instead of 9 purely because this form was not read.
    ("ליגת העל 08/09, מח' 6: מכבי תל אביב - אשקלון 96:95", "2008-11-17", True),
    ("ליגת העל 08/09, מח' 6: מכבי תל אביב - אשקלון 96:95", "2009-03-01", True),
    ("ליגת העל 08/09, מח' 6: מכבי תל אביב - אשקלון 96:95", "2015-03-01", False),
    ("יורוליג 08/09, בית א', מח' 6: מכבי תל אביב - ציבונה זאגרב 83:88", "2008-11-27", True),
    # A score is not a season, and neither is a day/month pair.
    ("תקציר: מכבי - הפועל 96:95", "2008-11-17", None),
    ("תקציר מ-16/02: מכבי - הפועל 96:95", "2008-11-17", None),
])
def test_title_year_agreement(title, game_date, expected):
    assert title_year_agrees(title, game_date) is expected


def test_a_match_with_no_page_scores_the_minimum():
    unmatched = VideoMatch(VideoEntry("v", "t", 180, "2024/25", "p", None), None,
                           Bucket.UNMATCHED, "no game", page_name=None)
    evidence = Evidence(score_unique_in_season=False, opponent_agrees=False,
                        )
    assert score_match(unmatched, None, evidence) == MIN_SCORE
