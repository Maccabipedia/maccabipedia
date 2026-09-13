"""Tests for writing a video link into a game page's template, per sport.

The page fixture is a real basketball game page pulled from the wiki, so the test
exercises the actual template shape rather than a hand-written approximation.
"""
from pathlib import Path

import mwparserfromhell as mw
import pytest

from maccabipediabot.maintenance.videos.sport_templates import (
    SPORT_TEMPLATES,
    sport_for_page,
)
from maccabipediabot.maintenance.videos.update_wiki_video_field import set_video_field

FIXTURE = (Path(__file__).resolve().parents[2]
           / "basketball" / "videos" / "fixtures" / "basketball_game_page.txt")
PAGE_TITLE = "כדורסל:03-01-2025 פרטיזן בלגרד נגד מכבי תל אביב - יורוליג"
VIDEO_URL = "https://www.youtube.com/watch?v=abc12345678"


class StubPage:
    def __init__(self, text: str):
        self.text = text
        self.saved_summary: str | None = None
        self.save_calls = 0
        self.bot_flag: bool | None = None

    def exists(self) -> bool:
        return True

    def save(self, summary: str, bot: bool = False) -> None:
        self.saved_summary = summary
        self.bot_flag = bot
        self.save_calls += 1


class MissingPage(StubPage):
    def exists(self) -> bool:
        return False


@pytest.fixture
def page(monkeypatch):
    stub = StubPage(FIXTURE.read_text(encoding="utf-8"))
    monkeypatch.setattr(
        "maccabipediabot.maintenance.videos.update_wiki_video_field.pw.Page",
        lambda site, title: stub,
    )
    return stub


def template_value(text: str, template_name: str, param: str) -> str:
    template = mw.parse(text).filter_templates(
        matches=lambda candidate: candidate.name.strip() == template_name)[0]
    return str(template.get(param).value).strip()


def test_sets_the_basketball_highlights_parameter(page):
    set_video_field(None, PAGE_TITLE, "תקציר וידאו", VIDEO_URL, sport="basketball")
    assert template_value(page.text, "משחק כדורסל", "תקציר וידאו") == VIDEO_URL
    assert page.save_calls == 1
    assert page.bot_flag is True


def test_sets_the_basketball_full_game_parameter(page):
    set_video_field(None, PAGE_TITLE, "משחק מלא2", VIDEO_URL, sport="basketball")
    assert template_value(page.text, "משחק כדורסל", "משחק מלא2") == VIDEO_URL


def test_leaves_the_rest_of_the_page_alone(page):
    before = page.text
    set_video_field(None, PAGE_TITLE, "תקציר וידאו", VIDEO_URL, sport="basketball")
    # Only the one parameter's value changes; every other line survives untouched.
    changed = [line for line in before.splitlines() if line not in page.text.splitlines()]
    assert len(changed) <= 1


def test_refuses_a_parameter_that_is_not_a_video_slot(page):
    with pytest.raises(ValueError, match="תקציר וידאו"):
        set_video_field(None, PAGE_TITLE, "שם יריבה", VIDEO_URL, sport="basketball")
    assert page.save_calls == 0


def test_refuses_a_slot_the_template_does_not_store_in_cargo(page):
    """The template renders תקציר וידאו3 but never passes it to Cargo."""
    with pytest.raises(ValueError):
        set_video_field(None, PAGE_TITLE, "תקציר וידאו3", VIDEO_URL, sport="basketball")


def test_never_overwrites_a_slot_that_already_has_a_link(page):
    set_video_field(None, PAGE_TITLE, "תקציר וידאו", VIDEO_URL, sport="basketball")
    with pytest.raises(ValueError, match="already"):
        set_video_field(None, PAGE_TITLE, "תקציר וידאו",
                        "https://www.youtube.com/watch?v=other", sport="basketball")
    assert page.save_calls == 1


def test_missing_page_is_reported(monkeypatch):
    monkeypatch.setattr(
        "maccabipediabot.maintenance.videos.update_wiki_video_field.pw.Page",
        lambda site, title: MissingPage(""),
    )
    with pytest.raises(LookupError):
        set_video_field(None, "כדורסל:nope", "תקציר וידאו", VIDEO_URL, sport="basketball")


def test_missing_template_is_reported(monkeypatch):
    monkeypatch.setattr(
        "maccabipediabot.maintenance.videos.update_wiki_video_field.pw.Page",
        lambda site, title: StubPage("no templates here"),
    )
    with pytest.raises(LookupError):
        set_video_field(None, PAGE_TITLE, "תקציר וידאו", VIDEO_URL, sport="basketball")


def test_default_summary_names_the_url(page):
    set_video_field(None, PAGE_TITLE, "תקציר וידאו", VIDEO_URL, sport="basketball")
    assert VIDEO_URL in page.saved_summary


def test_given_summary_wins(page):
    set_video_field(None, PAGE_TITLE, "תקציר וידאו", VIDEO_URL, sport="basketball",
                    summary="MaccabiBot - custom")
    assert page.saved_summary == "MaccabiBot - custom"


@pytest.mark.parametrize("sport,template_name,param_count", [
    ("football", "קטלוג משחקים", 3),
    ("basketball", "משחק כדורסל", 4),
])
def test_sport_templates_carry_each_sport_shape(sport, template_name, param_count):
    sport_template = SPORT_TEMPLATES[sport]
    assert sport_template.template_name == template_name
    assert len(sport_template.video_params) == param_count


@pytest.mark.parametrize("page_name,sport", [
    ("משחק:16-02-2009 מכבי תל אביב נגד הפועל", "football"),
    ("כדורסל:03-01-2025 פרטיזן בלגרד נגד מכבי תל אביב - יורוליג", "basketball"),
    ("כדורעף:01-01-2020 משהו", None),
    ("סתם דף", None),
])
def test_sport_for_page(page_name, sport):
    assert sport_for_page(page_name) == sport
