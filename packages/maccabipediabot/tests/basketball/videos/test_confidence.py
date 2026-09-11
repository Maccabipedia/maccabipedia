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
                        opponent_exact=True, kind_stated=True)
    assert score_match(match(published="20241122"), row(), evidence) == MAX_SCORE


def test_no_date_costs_points_but_stays_respectable():
    evidence = Evidence(score_unique_in_season=True, opponent_recognised=True,
                        opponent_exact=True, kind_stated=True)
    scored = score_match(match(published=None), row(), evidence)
    assert MIN_SCORE < scored < MAX_SCORE


def test_an_archive_upload_scores_below_a_date_confirmed_one():
    evidence = Evidence(score_unique_in_season=True, opponent_recognised=True,
                        opponent_exact=True, kind_stated=True)
    confirmed = score_match(match(published="20241122"), row(), evidence)
    archival = score_match(match(published="20150101"), row(), evidence)
    assert archival < confirmed


def test_a_date_that_contradicts_scores_the_minimum():
    """Uploaded before the game: whatever else agrees, this pairing cannot be right."""
    evidence = Evidence(score_unique_in_season=True, opponent_recognised=True,
                        opponent_exact=True, kind_stated=True)
    assert score_match(match(published="20200101"), row(), evidence) == MIN_SCORE


def test_a_shared_score_costs_points():
    strong = Evidence(score_unique_in_season=True, opponent_recognised=True,
                      opponent_exact=True, kind_stated=True)
    weak = Evidence(score_unique_in_season=False, opponent_recognised=True,
                    opponent_exact=True, kind_stated=True)
    assert score_match(match(published="20241122"), row(), weak) < \
        score_match(match(published="20241122"), row(), strong)


def test_an_unrecognised_opponent_costs_points():
    recognised = Evidence(score_unique_in_season=True, opponent_recognised=True,
                          opponent_exact=True, kind_stated=True)
    passthrough = Evidence(score_unique_in_season=True, opponent_recognised=False,
                           opponent_exact=False, kind_stated=True)
    assert score_match(match(published="20241122"), row(), passthrough) < \
        score_match(match(published="20241122"), row(), recognised)


def test_a_guessed_kind_costs_a_point():
    stated = Evidence(score_unique_in_season=True, opponent_recognised=True,
                      opponent_exact=True, kind_stated=True)
    guessed = Evidence(score_unique_in_season=True, opponent_recognised=True,
                       opponent_exact=True, kind_stated=False)
    assert score_match(match(published=None), row(), guessed) < \
        score_match(match(published=None), row(), stated)


@pytest.mark.parametrize("evidence", [
    Evidence(score_unique_in_season=False, opponent_recognised=False,
             opponent_exact=False, kind_stated=False),
    Evidence(score_unique_in_season=True, opponent_recognised=True,
             opponent_exact=True, kind_stated=True),
])
def test_the_score_always_stays_in_range(evidence):
    for published in (None, "20241122", "20150101", "20200101"):
        scored = score_match(match(published=published), row(), evidence)
        assert MIN_SCORE <= scored <= MAX_SCORE


def test_a_match_with_no_page_scores_the_minimum():
    unmatched = VideoMatch(VideoEntry("v", "t", 180, "2024/25", "p", None), None,
                           Bucket.UNMATCHED, "no game", page_name=None)
    evidence = Evidence(score_unique_in_season=False, opponent_recognised=False,
                        opponent_exact=False, kind_stated=False)
    assert score_match(unmatched, None, evidence) == MIN_SCORE
