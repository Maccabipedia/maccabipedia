"""rebuild, verify and restore: what gets saved, and everything that must stop a save."""
from collections import Counter
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from maccabipediabot.maintenance.football.player_titles import job
from maccabipediabot.maintenance.football.player_titles.api import ApiError
from maccabipediabot.maintenance.football.player_titles.page import parse_page, render_page, stored_credits
from maccabipediabot.maintenance.football.player_titles.rule import Credit, SeasonPlayed, Title
from maccabipediabot.maintenance.football.player_titles.wiki import PageState, SaveResult

MODULE = "maccabipediabot.maintenance.football.player_titles.job"
BOT = "MaccabiBot"
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
TITLES = [Title("1995/96", "ליגה לאומית"), Title("2000/01", "גביע המדינה")]
PLAYED = [SeasonPlayed("אבי נמני", "1995/96"), SeasonPlayed("אבי נמני", "2000/01"), SeasonPlayed("כפיר אדרי", "2000/01")]
FULL_TEXT = render_page(
    {TITLES[0]: ["אבי נמני"], TITLES[1]: ["אבי נמני", "כפיר אדרי"]}, removed={},
)
MISSING = PageState(exists=False, is_redirect=False, text="", revision_id=None, last_editor=None, last_edit=None)


def existing(text: str = "", editor: str = BOT, minutes_old: float = 60, is_redirect: bool = False) -> PageState:
    return PageState(
        exists=True, is_redirect=is_redirect, text=text, revision_id=4201, last_editor=editor,
        last_edit=NOW - timedelta(minutes=minutes_old),
    )


@pytest.fixture
def wiki():
    """The job with its wiki calls replaced; the table answers with what the page stores."""
    with patch(f"{MODULE}.won_titles", return_value=TITLES), \
            patch(f"{MODULE}.seasons_played", return_value=PLAYED), \
            patch(f"{MODULE}.PROFILE_REMOVALS", {}), \
            patch(f"{MODULE}.read_page") as read_page, \
            patch(f"{MODULE}.save_page", return_value=SaveResult(True, 4300, 13.2)) as save_page, \
            patch(f"{MODULE}.table_credits") as table_credits:
        read_page.return_value = MISSING
        table_credits.return_value = stored_credits(parse_page(FULL_TEXT))
        yield MagicMock(read_page=read_page, save_page=save_page, table_credits=table_credits)


def run_rebuild(live: bool = True, only_season: str | None = None) -> int:
    return job.rebuild(
        MagicMock(), MagicMock(), live=live, only_season=only_season, bot_user=BOT,
        now=NOW, verify_wait_seconds=0, sleep=lambda seconds: None,
    )


def test_dry_run_saves_nothing(wiki):
    assert run_rebuild(live=False) == 0
    wiki.save_page.assert_not_called()


def test_live_rebuild_saves_the_rendered_page_and_verifies(wiki):
    wiki.read_page.side_effect = [MISSING, existing(FULL_TEXT)]

    assert run_rebuild() == 0

    saved_text, saved_state = wiki.save_page.call_args.args[1:3]
    assert saved_text == FULL_TEXT and saved_state == MISSING
    wiki.table_credits.assert_called_once()


def test_live_rebuild_fails_when_the_table_does_not_match_the_saved_page(wiki):
    wiki.read_page.side_effect = [MISSING, existing(FULL_TEXT), existing(FULL_TEXT)]
    wiki.table_credits.return_value = Counter([Credit("אבי נמני", "1995/96", "ליגה לאומית")])

    assert run_rebuild() == 1


def test_a_page_already_up_to_date_is_not_saved_again(wiki):
    wiki.read_page.return_value = existing(FULL_TEXT)

    assert run_rebuild() == 0
    wiki.save_page.assert_not_called()


@pytest.mark.parametrize("state", [
    existing(FULL_TEXT + "\nעריכה", editor="Someone"),
    existing("טקסט בלי סימון הכותרת"),
    existing("#הפניה [[עמוד אחר]]", is_redirect=True),
    existing(FULL_TEXT + "\nישן", minutes_old=2),
], ids=["a person edited it", "no header marker", "a redirect", "a revision two minutes old"])
def test_rebuild_refuses_to_overwrite(wiki, state):
    wiki.read_page.return_value = state

    assert run_rebuild() == 1
    wiki.save_page.assert_not_called()


def test_an_edit_conflict_stops_the_run_before_any_verify(wiki):
    wiki.read_page.return_value = existing(FULL_TEXT + "\nישן")
    wiki.save_page.side_effect = ApiError("editconflict", "Edit conflict.")

    assert run_rebuild() == 1
    wiki.table_credits.assert_not_called()


def test_only_season_renders_one_season(wiki):
    run_rebuild(only_season="1995/96")

    saved = parse_page(wiki.save_page.call_args.args[1])
    assert saved.blocks == [Title("1995/96", "ליגה לאומית")]


def test_only_season_with_no_title_in_it_saves_nothing(wiki):
    assert run_rebuild(only_season="1900/01") == 1
    wiki.save_page.assert_not_called()


def test_profile_removals_are_written_as_removed_lines(wiki):
    removal = {Credit("כפיר אדרי", "2000/01", "גביע המדינה"): "עזב לפני הגביע"}
    with patch(f"{MODULE}.PROFILE_REMOVALS", removal):
        run_rebuild()

    saved = parse_page(wiki.save_page.call_args.args[1])
    assert [(line.credit.player, line.removed) for line in saved.lines if line.removed] == [("כפיר אדרי", "עזב לפני הגביע")]


def run_verify() -> int:
    return job.verify(MagicMock(), wait_seconds=0, sleep=lambda seconds: None)


def test_verify_passes_when_the_table_equals_the_page(wiki):
    wiki.read_page.return_value = existing(FULL_TEXT)

    assert run_verify() == 0


def test_verify_reads_twice_before_failing(wiki):
    wiki.read_page.return_value = existing(FULL_TEXT)
    short = Counter([Credit("אבי נמני", "1995/96", "ליגה לאומית")])

    wiki.table_credits.side_effect = [short, stored_credits(parse_page(FULL_TEXT))]
    assert run_verify() == 0

    wiki.table_credits.side_effect = [short, short]
    assert run_verify() == 1


def test_verify_fails_on_a_row_stored_twice(wiki):
    wiki.read_page.return_value = existing(FULL_TEXT)
    wiki.table_credits.return_value = stored_credits(parse_page(FULL_TEXT)) + Counter([Credit("אבי נמני", "1995/96", "ליגה לאומית")])

    assert run_verify() == 1


def test_verify_fails_on_a_missing_page(wiki):
    assert run_verify() == 1


def test_restore_saves_the_page_text_unchanged_then_verifies(wiki):
    state = existing(FULL_TEXT)
    wiki.read_page.return_value = state
    wiki.save_page.return_value = SaveResult(False, None, 13.0)

    assert job.restore(MagicMock(), now=NOW, verify_wait_seconds=0, sleep=lambda seconds: None) == 0
    assert wiki.save_page.call_args.args[1:3] == (FULL_TEXT, state)


def test_restore_refuses_while_the_last_save_may_still_be_storing(wiki):
    wiki.read_page.return_value = existing(FULL_TEXT, minutes_old=1)

    assert job.restore(MagicMock(), now=NOW, verify_wait_seconds=0, sleep=lambda seconds: None) == 1
    wiki.save_page.assert_not_called()
