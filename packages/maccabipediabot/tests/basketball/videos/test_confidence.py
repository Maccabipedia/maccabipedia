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
    evidence = Evidence(score_unique_in_season=True, opponent_recognised=True,
                        )
    assert score_match(match(published="20241122"), row(), evidence) == MAX_SCORE


def test_no_date_costs_points_but_stays_respectable():
    evidence = Evidence(score_unique_in_season=True, opponent_recognised=True,
                        )
    scored = score_match(match(published=None), row(), evidence)
    assert MIN_SCORE < scored < MAX_SCORE


def test_an_archive_upload_scores_below_a_date_confirmed_one():
    evidence = Evidence(score_unique_in_season=True, opponent_recognised=True,
                        )
    confirmed = score_match(match(published="20241122"), row(), evidence)
    archival = score_match(match(published="20150101"), row(), evidence)
    assert archival < confirmed


def test_a_date_that_contradicts_scores_the_minimum():
    """Uploaded before the game: whatever else agrees, this pairing cannot be right."""
    evidence = Evidence(score_unique_in_season=True, opponent_recognised=True,
                        )
    assert score_match(match(published="20200101"), row(), evidence) == MIN_SCORE


def test_a_shared_score_costs_points_when_the_date_cannot_confirm():
    """Two games that season ended with this score, so the opponent alone chose between
    them, and the archive upload cannot corroborate the choice."""
    strong = Evidence(score_unique_in_season=True, opponent_recognised=True,
                      title_year_agrees=True)
    weak = Evidence(score_unique_in_season=False, opponent_recognised=True,
                    title_year_agrees=True)
    game = row(date=ARCHIVE_GAME)
    assert score_match(match(published=ARCHIVE_UPLOAD), game, weak) < \
        score_match(match(published=ARCHIVE_UPLOAD), game, strong)


def test_a_shared_score_costs_nothing_once_the_date_confirms():
    """The opponent picked between two same-score games, and an upload dated to the game
    itself confirms that pick from a direction the title cannot reach."""
    weak = Evidence(score_unique_in_season=False, opponent_recognised=True)
    assert score_match(match(published="20241122"), row(), weak) == MAX_SCORE


def test_an_unrecognised_opponent_costs_points():
    recognised = Evidence(score_unique_in_season=True, opponent_recognised=True,
                          )
    passthrough = Evidence(score_unique_in_season=True, opponent_recognised=False,
                           )
    assert score_match(match(published="20241122"), row(), passthrough) < \
        score_match(match(published="20241122"), row(), recognised)


def test_a_guessed_kind_does_not_change_the_score():
    """Whether the title stated the kind decides which parameter the link goes in, not
    whether the link belongs to this game. It used to cost a point, which held 655
    otherwise-perfect archive matches a rung below their real confidence."""
    evidence = Evidence(score_unique_in_season=True, opponent_recognised=True)
    stated = match(published="20241122", kind=VideoKind.HIGHLIGHTS)
    guessed = match(published="20241122", kind=None, kind_override=VideoKind.CONDENSED)
    assert score_match(guessed, row(), evidence) == score_match(stated, row(), evidence)


def test_an_era_variant_opponent_name_does_not_change_the_score():
    """Cargo spells the same club differently by era, so the alias table maps to the
    distinctive part of the name on purpose; matching by containment is the designed
    path, not a near miss."""
    evidence = Evidence(score_unique_in_season=True, opponent_recognised=True)
    exact = score_match(match(published="20241122", opponent_raw="אליצור נתניה"),
                        row(opponent="אליצור נתניה"), evidence)
    contained = score_match(match(published="20241122", opponent_raw="נתניה"),
                            row(opponent="אליצור עירוני נתניה"), evidence)
    assert contained == exact == MAX_SCORE


@pytest.mark.parametrize("evidence", [
    Evidence(score_unique_in_season=False, opponent_recognised=False,
             ),
    Evidence(score_unique_in_season=True, opponent_recognised=True,
             ),
])
def test_the_score_always_stays_in_range(evidence):
    for published in (None, "20241122", "20150101", "20200101"):
        scored = score_match(match(published=published), row(), evidence)
        assert MIN_SCORE <= scored <= MAX_SCORE


def archive_evidence(year_agrees):
    return Evidence(score_unique_in_season=True, opponent_recognised=True,
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
])
def test_title_year_agreement(title, game_date, expected):
    assert title_year_agrees(title, game_date) is expected


def test_a_match_with_no_page_scores_the_minimum():
    unmatched = VideoMatch(VideoEntry("v", "t", 180, "2024/25", "p", None), None,
                           Bucket.UNMATCHED, "no game", page_name=None)
    evidence = Evidence(score_unique_in_season=False, opponent_recognised=False,
                        )
    assert score_match(unmatched, None, evidence) == MIN_SCORE
