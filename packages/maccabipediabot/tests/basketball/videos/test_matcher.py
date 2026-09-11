"""Tests for matching channel videos to Basketball_Games rows.

The key is the season plus the final score, confirmed by the opponent. Anything the
key cannot settle goes to a review bucket rather than being guessed at.

Note the score order in the titles below: Hebrew reads right to left, so
'מכבי - אליצור נתניה 92:102' is Maccabi 102, and the English title of the same game
carries the digits the other way round.
"""
import pytest

from maccabipediabot.basketball.videos.cargo import GameRow
from maccabipediabot.basketball.videos.inventory import VideoEntry
from maccabipediabot.basketball.videos.matcher import Bucket, match_videos


def row(page, opponent, maccabi, opponent_points, *, highlights=("", ""), full_games=("", ""),
        season="2024/25", competition="ליגת העל", leg="", home_away="בית", date="01-11-2024"):
    return GameRow(page_name=page, date=date, season=season, opponent=opponent,
                   competition=competition, leg=leg, home_away=home_away,
                   maccabi_points=maccabi, opponent_points=opponent_points,
                   highlights=highlights, full_games=full_games)


def entry(video_id, title, duration=180, season="2024/25"):
    return VideoEntry(video_id=video_id, title=title, duration_seconds=duration,
                      season=season, playlist=f"{season} Season", published=None)


ROWS = [
    row("כדורסל:01-11-2024 מכבי תל אביב נגד אליצור נתניה - ליגת העל", "אליצור נתניה", 102, 92),
    row("כדורסל:08-11-2024 הפועל חולון נגד מכבי תל אביב - ליגת העל", "הפועל חולון", 80, 77, home_away="חוץ"),
    row("כדורסל:15-11-2024 מכבי תל אביב נגד הפועל תל אביב - ליגת העל", "הפועל תל אביב", 80, 77),
    row("כדורסל:22-11-2024 מכבי תל אביב נגד מילאנו - יורוליג", "ארמאני מילאנו", 102, 88,
        competition="יורוליג", leg="מחזור 9",
        highlights=("https://www.youtube.com/watch?v=dRsHKQtTRBM", "")),
]


def only_match(entries, rows=None, overrides=None):
    matches = match_videos(entries, rows if rows is not None else ROWS, overrides or {})
    assert len(matches) == 1
    return matches[0]


def test_exact_match_on_score_and_opponent():
    match = only_match([entry("2mzCdQzotnY", 'תקציר המשחק: מכבי Rapyd ת"א - אליצור נתניה 92:102')])
    assert match.bucket == Bucket.EXACT
    assert match.slot == "תקציר וידאו"
    assert match.page_name.startswith("כדורסל:01-11-2024")


def test_opponent_breaks_a_tie_between_two_games_with_the_same_score():
    match = only_match([entry("x2", "Highlights: Maccabi Playtika Tel Aviv - Hapoel Tel-Aviv 80:77")])
    assert match.bucket == Bucket.EXACT
    assert "הפועל תל אביב" in match.page_name


def test_same_score_with_an_unknown_opponent_is_ambiguous():
    match = only_match([entry("x1", "Highlights: Maccabi Playtika Tel Aviv - Unknown FC 80:77")])
    assert match.bucket == Bucket.AMBIGUOUS
    assert len(match.candidates) == 2


def test_no_game_with_that_score_is_unmatched():
    match = only_match([entry("x3", "Highlights: Maccabi Playtika Tel Aviv - Hapoel Holon 99:98")])
    assert match.bucket == Bucket.UNMATCHED
    assert match.candidates == []


def test_reversed_score_is_flagged_rather_than_matched():
    """If only the swapped score exists, the title was read the wrong way round —
    that is a parser bug worth seeing, not a match to write."""
    match = only_match([entry("x4", 'תקציר המשחק: מכבי Rapyd ת"א - אליצור נתניה 102:92')])
    assert match.bucket == Bucket.AMBIGUOUS
    assert "swapped" in match.reason


def test_both_score_orders_matching_the_same_opponent_is_refused():
    """The channel has published both "74:80" and "80:74" for one game, so when a
    season holds the mirror result against the same club, either pick would be a guess
    that lands a video on a real but different game."""
    rows = [row("כדורסל:01-12-2024 מכבי תל אביב נגד הפועל חולון - ליגת העל", "הפועל חולון", 80, 74),
            row("כדורסל:20-12-2024 הפועל חולון נגד מכבי תל אביב - ליגת העל", "הפועל חולון", 74, 80,
                home_away="חוץ")]
    match = only_match([entry("x", "Game Highlights: Maccabi Rapyd Tel Aviv vs. Hapoel Holon 80:74")],
                       rows=rows)
    assert match.bucket == Bucket.AMBIGUOUS
    assert "both score orders" in match.reason
    assert len(match.candidates) == 2


def test_a_video_already_on_the_page_is_not_written_again():
    match = only_match([entry("dRsHKQtTRBM", 'תקציר המשחק: מכבי Rapyd ת"א - מילאנו 88:102')])
    assert match.bucket == Bucket.ALREADY_PRESENT


def test_second_highlight_takes_the_second_slot_and_a_third_overflows():
    entries = [entry("a", 'תקציר המשחק: מכבי Rapyd ת"א - אליצור נתניה 92:102'),
               entry("b", "Highlights: Maccabi Rapyd Tel Aviv - Elitzur Netanya 102:92"),
               entry("c", "Game Highlights: Maccabi Rapyd Tel Aviv - Elitzur Netanya 102:92")]
    matches = {match.entry.video_id: match for match in match_videos(entries, ROWS, {})}
    assert matches["a"].slot == "תקציר וידאו"          # Hebrew ranks first
    assert matches["b"].slot == "תקציר וידאו2"
    assert matches["c"].slot is None
    assert matches["c"].bucket == Bucket.OVERFLOW


def test_full_game_and_highlight_do_not_compete_for_the_same_slot():
    entries = [entry("a", 'תקציר המשחק: מכבי Rapyd ת"א - אליצור נתניה 92:102'),
               entry("b", 'המשחק המלא: מכבי Rapyd ת"א - אליצור נתניה 92:102', duration=7000)]
    matches = {match.entry.video_id: match for match in match_videos(entries, ROWS, {})}
    assert matches["a"].slot == "תקציר וידאו"
    assert matches["b"].slot == "משחק מלא"


def test_condensed_replay_is_an_extended_highlight():
    """A תרכיז shares the תקציר slots and ranks below a real תקציר."""
    entries = [entry("c", 'תרכיז המשחק: מכבי Rapyd ת"א - אליצור נתניה 92:102', duration=900),
               entry("h", 'תקציר המשחק: מכבי Rapyd ת"א - אליצור נתניה 92:102')]
    matches = {match.entry.video_id: match for match in match_videos(entries, ROWS, {})}
    assert matches["h"].slot == "תקציר וידאו"
    assert matches["c"].slot == "תקציר וידאו2"
    assert all(match.bucket == Bucket.EXACT for match in matches.values())


def test_condensed_replay_alone_takes_the_first_highlight_slot():
    match = only_match([entry("c", 'תרכיז המשחק: מכבי Rapyd ת"א - אליצור נתניה 92:102', duration=900)])
    assert match.bucket == Bucket.EXACT
    assert match.slot == "תקציר וידאו"


def test_a_condensed_replay_never_reaches_the_full_game_slots():
    entries = [entry("a", 'תקציר המשחק: מכבי Rapyd ת"א - אליצור נתניה 92:102'),
               entry("b", "Highlights: Maccabi Rapyd Tel Aviv - Elitzur Netanya 102:92"),
               entry("c", 'תרכיז המשחק: מכבי Rapyd ת"א - אליצור נתניה 92:102', duration=900)]
    matches = {match.entry.video_id: match for match in match_videos(entries, ROWS, {})}
    assert matches["c"].bucket == Bucket.OVERFLOW
    assert matches["c"].slot is None


@pytest.mark.parametrize("duration,expected_slot", [
    (180, "תקציר וידאו"),     # a short clip is a highlight
    (900, "תקציר וידאו"),     # a condensed game shares the highlight slots
    (7000, "משחק מלא"),        # a long one is the full game
    (None, "תקציר וידאו"),    # unknown length falls back to the commonest kind
])
def test_archive_titles_take_their_kind_from_the_duration(duration, expected_slot):
    """The channel's archive uploads name no kind: "<competition> <year>, <stage>,
    <teams> <score>". Only the length can say what they are."""
    title = 'ליגה לאומית 2024,מח\' 11, מכבי ת"א - אליצור נתניה 92:102'
    match = only_match([entry("arch", title, duration=duration)])
    assert match.bucket == Bucket.EXACT
    assert match.slot == expected_slot


def test_an_archive_title_is_not_rejected_for_its_length():
    """With no stated kind there is nothing for the length to contradict."""
    title = 'ליגה לאומית 2024,מח\' 11, מכבי ת"א - אליצור נתניה 92:102'
    match = only_match([entry("arch", title, duration=3000)])
    assert match.bucket == Bucket.EXACT


def test_an_override_promotes_an_ambiguous_video():
    page = "כדורסל:08-11-2024 הפועל חולון נגד מכבי תל אביב - ליגת העל"
    match = only_match([entry("x1", "Highlights: Maccabi Playtika Tel Aviv - Unknown FC 80:77")],
                       overrides={"x1": page})
    assert match.bucket == Bucket.EXACT
    assert match.page_name == page
    assert match.reason == "override"


def test_a_full_game_that_is_too_short_is_flagged():
    match = only_match([entry("x5", 'המשחק המלא: מכבי Rapyd ת"א - אליצור נתניה 92:102', duration=200)])
    assert match.bucket == Bucket.AMBIGUOUS
    assert "duration" in match.reason


def test_a_missing_duration_does_not_block_a_match():
    """RSS feeds carry no duration, so the sanity check has to be skippable."""
    match = only_match([entry("x6", 'המשחק המלא: מכבי Rapyd ת"א - אליצור נתניה 92:102', duration=None)])
    assert match.bucket == Bucket.EXACT
    assert match.slot == "משחק מלא"


def test_videos_from_a_different_season_do_not_match():
    match = only_match([entry("x7", 'תקציר המשחק: מכבי Rapyd ת"א - אליצור נתניה 92:102', season="2019/20")])
    assert match.bucket == Bucket.UNMATCHED


def test_the_same_video_listed_in_two_playlists_is_handled_once():
    entries = [entry("dup", 'תקציר המשחק: מכבי Rapyd ת"א - אליצור נתניה 92:102'),
               entry("dup", 'תקציר המשחק: מכבי Rapyd ת"א - אליצור נתניה 92:102')]
    assert len(match_videos(entries, ROWS, {})) == 1


def test_non_game_videos_are_dropped_entirely():
    assert match_videos([entry("n", "Welcome to Maccabi Shane Hunter")], ROWS, {}) == []


@pytest.mark.parametrize("existing,expected_slot", [
    (("https://www.youtube.com/watch?v=other", ""), "תקציר וידאו2"),
    (("", "https://www.youtube.com/watch?v=other"), "תקציר וידאו"),
])
def test_an_occupied_slot_is_never_overwritten(existing, expected_slot):
    rows = [row("כדורסל:01-11-2024 מכבי תל אביב נגד אליצור נתניה - ליגת העל", "אליצור נתניה", 102, 92,
                highlights=existing)]
    match = only_match([entry("a", 'תקציר המשחק: מכבי Rapyd ת"א - אליצור נתניה 92:102')], rows=rows)
    assert match.slot == expected_slot


def test_both_slots_taken_means_overflow():
    rows = [row("כדורסל:01-11-2024 מכבי תל אביב נגד אליצור נתניה - ליגת העל", "אליצור נתניה", 102, 92,
                highlights=("https://youtu.be/a", "https://youtu.be/b"))]
    match = only_match([entry("a", 'תקציר המשחק: מכבי Rapyd ת"א - אליצור נתניה 92:102')], rows=rows)
    assert match.bucket == Bucket.OVERFLOW
    assert match.slot is None
