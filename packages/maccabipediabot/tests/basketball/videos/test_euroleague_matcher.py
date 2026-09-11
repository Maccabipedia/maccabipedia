"""Tests for matching EuroLeague-channel videos, which carry a round instead of a score."""
from maccabipediabot.basketball.videos.cargo import GameRow
from maccabipediabot.basketball.videos.inventory import VideoEntry
from maccabipediabot.basketball.videos.matcher import (
    Bucket,
    EUROLEAGUE_CHANNEL,
    match_euroleague_videos,
    match_videos,
)


def euroleague_row(page, opponent, leg, season="2025/26", maccabi=85, opponent_points=99,
                   highlights=("", ""), full_games=("", "")):
    return GameRow(page_name=page, date="28-02-2026", season=season, opponent=opponent,
                   competition="יורוליג", leg=leg, home_away="בית",
                   maccabi_points=maccabi, opponent_points=opponent_points,
                   highlights=highlights, full_games=full_games)


def entry(video_id, title):
    return VideoEntry(video_id=video_id, title=title, duration_seconds=None,
                      season="", playlist="euroleague-search", published=None)


PANATHINAIKOS_R24 = euroleague_row(
    "כדורסל:28-02-2026 מכבי תל אביב נגד פנאתינייקוס - יורוליג", "פנאתינייקוס", "מחזור 24")
PARTIZAN_R26 = euroleague_row(
    "כדורסל:06-03-2026 מכבי תל אביב נגד פרטיזן בלגרד - יורוליג", "פרטיזן בלגרד", "מחזור 26")
LEAGUE_ROW = GameRow(page_name="כדורסל:01-11-2025 מכבי תל אביב נגד הפועל חולון - ליגת העל",
                     date="01-11-2025", season="2025/26", opponent="הפועל חולון",
                     competition="ליגת העל", leg="מחזור 24", home_away="בית",
                     maccabi_points=80, opponent_points=77, highlights=("", ""), full_games=("", ""))

ROWS = [PANATHINAIKOS_R24, PARTIZAN_R26, LEAGUE_ROW]


def only_match(entries, rows=None, overrides=None):
    matches = match_euroleague_videos(entries, rows if rows is not None else ROWS, overrides or {})
    assert len(matches) == 1
    return matches[0]


def test_matches_on_season_round_and_opponent():
    match = only_match([entry("euDEQVzwbM0",
                              "Down to the FINAL SHOT | Maccabi - Panathinaikos | R24 BASKETBALL HIGHLIGHTS 2025-26")])
    assert match.bucket == Bucket.EXACT
    assert match.page_name == PANATHINAIKOS_R24.page_name
    assert match.slot == "תקציר וידאו"
    assert match.source == EUROLEAGUE_CHANNEL


def test_a_league_game_with_the_same_round_number_is_not_matched():
    """Round 24 exists in both competitions; only the EuroLeague row may be considered."""
    match = only_match([entry("x", "Maccabi - Panathinaikos | R24 BASKETBALL HIGHLIGHTS 2025-26")])
    assert match.page_name == PANATHINAIKOS_R24.page_name


def test_a_round_with_no_matching_game_is_unmatched():
    match = only_match([entry("x", "Maccabi - Panathinaikos | R30 BASKETBALL HIGHLIGHTS 2025-26")])
    assert match.bucket == Bucket.UNMATCHED


def test_the_opponent_must_agree_with_the_round():
    match = only_match([entry("x", "Maccabi - Partizan | R24 BASKETBALL HIGHLIGHTS 2025-26")])
    assert match.bucket == Bucket.AMBIGUOUS
    assert "opponent" in match.reason


def test_a_classic_game_without_a_round_matches_on_the_opponent_alone():
    match = only_match([entry("x", "EUROLEAGUE CLASSIC GAMES: Maccabi Tel Aviv - Partizan 2025-26")])
    assert match.bucket == Bucket.EXACT
    assert match.page_name == PARTIZAN_R26.page_name
    assert match.slot == "משחק מלא"


def test_a_classic_game_is_ambiguous_when_the_season_has_two_games_against_that_club():
    rows = [PARTIZAN_R26,
            euroleague_row("כדורסל:20-03-2026 פרטיזן בלגרד נגד מכבי תל אביב - יורוליג",
                           "פרטיזן בלגרד", "מחזור 30")]
    match = only_match([entry("x", "EUROLEAGUE CLASSIC GAMES: Maccabi Tel Aviv - Partizan 2025-26")],
                       rows=rows)
    assert match.bucket == Bucket.AMBIGUOUS
    assert len(match.candidates) == 2


def test_a_row_without_a_leg_cannot_be_claimed_by_a_round():
    rows = [euroleague_row("כדורסל:01-01-2006 מכבי תל אביב נגד פנאתינייקוס - יורוליג",
                           "פנאתינייקוס", "", season="2005/06")]
    match = only_match([entry("x", "Maccabi - Panathinaikos | R24 BASKETBALL HIGHLIGHTS 2005-06")],
                       rows=rows)
    assert match.bucket in (Bucket.AMBIGUOUS, Bucket.UNMATCHED)


def test_the_club_channel_keeps_the_first_slot():
    """Both matchers run over the same rows, the club's own video first."""
    # Hebrew reads right to left: this is Maccabi 85, Panathinaikos 99.
    club_entry = VideoEntry("club1", 'תקציר המשחק: מכבי Rapyd ת"א - פנאתינייקוס 99:85',
                            180, "2025/26", "2025/26 Season", None)
    club_matches = match_videos([club_entry], ROWS, {})
    euroleague_matches = match_euroleague_videos(
        [entry("el1", "Maccabi - Panathinaikos | R24 BASKETBALL HIGHLIGHTS 2025-26")],
        ROWS, {}, already_assigned=club_matches,
    )
    assert club_matches[0].slot == "תקציר וידאו"
    assert euroleague_matches[0].slot == "תקציר וידאו2"


def test_an_occupied_slot_pushes_the_euroleague_video_to_the_second():
    rows = [euroleague_row(PANATHINAIKOS_R24.page_name, "פנאתינייקוס", "מחזור 24",
                           highlights=("https://www.youtube.com/watch?v=already", ""))]
    match = only_match([entry("x", "Maccabi - Panathinaikos | R24 BASKETBALL HIGHLIGHTS 2025-26")],
                       rows=rows)
    assert match.slot == "תקציר וידאו2"


def test_non_maccabi_videos_are_dropped():
    assert match_euroleague_videos(
        [entry("x", "Real Madrid - Olympiacos | R12 BASKETBALL HIGHLIGHTS 2025-26")], ROWS, {}) == []
