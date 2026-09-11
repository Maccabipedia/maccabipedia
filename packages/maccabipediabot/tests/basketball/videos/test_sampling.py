"""Tests for the verification sample: 20 matches checked against an independent signal."""
import pytest

from maccabipediabot.basketball.videos.cargo import GameRow
from maccabipediabot.basketball.videos.inventory import VideoEntry
from maccabipediabot.basketball.videos.matcher import Bucket, VideoMatch
from maccabipediabot.basketball.videos.sampling import (
    Verdict,
    choose_verification_sample,
    verify_sample,
)
from maccabipediabot.basketball.videos.title_parser import ParsedTitle, VideoKind

SEASONS = ["1985/86", "1994/95", "2003/04", "2011/12", "2018/19", "2025/26"]


def build_match(video_id, season, home_away, kind, opponent, date="01-11-2024"):
    page = f"כדורסל:{date} game-{video_id}"
    entry = VideoEntry(video_id, f"title-{video_id}", 180, season, "p", None)
    parsed = ParsedTitle(kind, opponent, 90, 80, "he")
    row = GameRow(page_name=page, date=date, season=season, opponent=opponent,
                  competition="ליגת העל", leg="", home_away=home_away,
                  maccabi_points=90, opponent_points=80, highlights=("", ""), full_games=("", ""))
    match = VideoMatch(entry, parsed, Bucket.EXACT, "score and opponent agree",
                       page_name=page, slot="תקציר וידאו")
    return match, row


def build_population():
    matches, rows_by_page = [], {}
    counter = 0
    for season in SEASONS:
        for home_away in ("בית", "חוץ"):
            for kind in (VideoKind.HIGHLIGHTS, VideoKind.FULL_GAME):
                for index in range(3):
                    counter += 1
                    match, row = build_match(f"v{counter}", season, home_away, kind,
                                             f"יריבה {counter % 17}")
                    matches.append(match)
                    rows_by_page[row.page_name] = row
    return matches, rows_by_page


MATCHES, ROWS_BY_PAGE = build_population()


def test_sample_spreads_across_seasons_home_away_and_kinds():
    sample = choose_verification_sample(MATCHES, ROWS_BY_PAGE, size=20)
    assert len(sample) == 20
    assert len({match.entry.season for match in sample}) >= 5
    assert len({match.parsed.kind for match in sample}) == 2
    assert len({ROWS_BY_PAGE[match.page_name].home_away for match in sample}) == 2
    assert len({ROWS_BY_PAGE[match.page_name].opponent for match in sample}) >= 10


def test_sample_is_deterministic_for_a_seed():
    first = choose_verification_sample(MATCHES, ROWS_BY_PAGE, size=20, seed=1)
    second = choose_verification_sample(MATCHES, ROWS_BY_PAGE, size=20, seed=1)
    assert [match.entry.video_id for match in first] == [match.entry.video_id for match in second]


def test_a_different_seed_gives_a_different_sample():
    first = choose_verification_sample(MATCHES, ROWS_BY_PAGE, size=20, seed=1)
    second = choose_verification_sample(MATCHES, ROWS_BY_PAGE, size=20, seed=2)
    assert [match.entry.video_id for match in first] != [match.entry.video_id for match in second]


def test_sample_falls_back_when_a_stratum_is_empty():
    home_only = [match for match in MATCHES if ROWS_BY_PAGE[match.page_name].home_away == "בית"]
    assert len(choose_verification_sample(home_only, ROWS_BY_PAGE, size=20)) == 20


def test_sample_cannot_exceed_the_population():
    assert len(choose_verification_sample(MATCHES[:7], ROWS_BY_PAGE, size=20)) == 7


def test_only_writable_matches_are_sampled():
    matches = list(MATCHES)
    matches[0].bucket = Bucket.AMBIGUOUS
    sample = choose_verification_sample(matches, ROWS_BY_PAGE, size=20)
    assert all(match.bucket == Bucket.EXACT and match.slot for match in sample)


def sample_of_one(game_date):
    match, row = build_match("v1", "2024/25", "בית", VideoKind.HIGHLIGHTS, "יריבה", date=game_date)
    return [match], {match.page_name: row}


def test_cargo_iso_dates_are_understood():
    """Cargo returns '2024-11-22' while page titles use '22-11-2024'; both must work."""
    sample, rows = sample_of_one("2024-11-22")
    [check] = verify_sample(sample, rows, lambda video_id: "20241122")
    assert check.days_apart == 0
    assert check.verdict == Verdict.CONFIRMED


@pytest.mark.parametrize("upload_date,verdict", [
    ("20241122", Verdict.CONFIRMED),      # same day
    ("20241123", Verdict.CONFIRMED),      # next day
    ("20241125", Verdict.CONFIRMED),      # within the window
    ("20241220", Verdict.DATE_MISMATCH),  # a month later, same season
    ("20240101", Verdict.DATE_MISMATCH),  # before the game
])
def test_upload_date_verdicts(upload_date, verdict):
    sample, rows = sample_of_one("22-11-2024")
    [check] = verify_sample(sample, rows, lambda video_id: upload_date)
    assert check.verdict == verdict


def test_an_archival_upload_carries_no_date_signal():
    """A 1985 game uploaded in 2015 says nothing either way; it needs human eyes."""
    sample, rows = sample_of_one("04-03-1985")
    [check] = verify_sample(sample, rows, lambda video_id: "20150612")
    assert check.verdict == Verdict.NO_DATE_SIGNAL
    assert check.days_apart is not None


def test_a_missing_upload_date_is_reported_not_guessed():
    sample, rows = sample_of_one("22-11-2024")
    [check] = verify_sample(sample, rows, lambda video_id: None)
    assert check.verdict == Verdict.NO_DATE_SIGNAL
    assert check.days_apart is None


def test_check_carries_the_page_facts_for_the_reviewer():
    sample, rows = sample_of_one("22-11-2024")
    [check] = verify_sample(sample, rows, lambda video_id: "20241122")
    assert check.game_date == "22-11-2024"
    assert check.opponent == "יריבה"
    assert check.home_away == "בית"
    assert check.match.page_name.startswith("כדורסל:")
