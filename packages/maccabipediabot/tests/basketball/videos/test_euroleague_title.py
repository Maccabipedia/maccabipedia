"""Tests for parsing EuroLeague-channel titles.

Their titles carry no score, so the game key is the season plus the round number,
which lines up with the Leg column ("מחזור 24"). Titles are real, from one
channel-search listing of videos mentioning Maccabi.
"""
import pytest

from maccabipediabot.basketball.videos.euroleague_title import parse_euroleague_title
from maccabipediabot.basketball.videos.title_parser import VideoKind


@pytest.mark.parametrize("title,season,round_number,opponent", [
    ("Down to the FINAL SHOT | Maccabi - Panathinaikos | R24 BASKETBALL HIGHLIGHTS 2025-26",
     "2025/26", 24, "Panathinaikos"),
    ("Final Seconds COLLAPSE | Crvena Zvezda - Maccabi | R27 BASKETBALL HIGHLIGHTS 2025-26",
     "2025/26", 27, "Crvena Zvezda"),
    ("FOUR Seconds. Clark Wins | Maccabi Tel Aviv - Partizan | R26 BASKETBALL HIGHLIGHTS 2025-26",
     "2025/26", 26, "Partizan"),
    ("OT Decides The SHOOTOUT | Maccabi - FC Bayern Munich | R28 BASKETBALL HIGHLIGHTS 2025-26",
     "2025/26", 28, "FC Bayern Munich"),
    ("Play-in hopes STILL alive | Maccabi - Efes | R35 BASKETBALL HIGHLIGHTS 2025-26",
     "2025/26", 35, "Efes"),
    ("A COMPLETE team EFFORT | Maccabi - Fenerbahçe | R33 BASKETBALL HIGHLIGHTS 2025-26",
     "2025/26", 33, "Fenerbahçe"),
])
def test_parses_round_highlights(title, season, round_number, opponent):
    parsed = parse_euroleague_title(title)
    assert parsed is not None, f"expected a parse for: {title}"
    assert parsed.season == season
    assert parsed.round_number == round_number
    assert parsed.opponent_raw == opponent
    assert parsed.kind == VideoKind.HIGHLIGHTS


def test_classic_game_is_a_full_game_without_a_round():
    parsed = parse_euroleague_title("EUROLEAGUE CLASSIC GAMES: Maccabi Tel Aviv - Panathinaikos 2013-14")
    assert parsed is not None
    assert parsed.kind == VideoKind.FULL_GAME
    assert parsed.round_number is None
    assert parsed.season == "2013/14"
    assert parsed.opponent_raw == "Panathinaikos"


@pytest.mark.parametrize("title", [
    # No season, so nothing anchors it to a game.
    "FINAL MINUTES: Incredible Game-Winning Three Pointer by Laprovittola | Barca vs Maccabi",
    # Not about one game at all.
    "Top 10 Plays of the Season 2025-26",
    # Another club's game entirely.
    "Real Madrid - Olympiacos | R12 BASKETBALL HIGHLIGHTS 2025-26",
])
def test_rejects_titles_without_a_usable_game_key(title):
    assert parse_euroleague_title(title) is None
