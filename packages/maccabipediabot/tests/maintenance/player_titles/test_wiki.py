"""Reading the data page, saving it bound to the revision that was read, reading the table."""
from collections import Counter
from datetime import datetime, timezone

import pytest

from maccabipediabot.maintenance.football.player_titles.exports import ExportError
from maccabipediabot.maintenance.football.player_titles.rule import Credit
from maccabipediabot.maintenance.football.player_titles.wiki import PageState, read_page, save_page, table_credits

from .fakes import FakeCargoApi

MISSING = PageState(exists=False, is_redirect=False, text="", revision_id=None, last_editor=None, last_edit=None)
EXISTING = PageState(
    exists=True, is_redirect=False, text="ישן", revision_id=4201, last_editor="MaccabiBot",
    last_edit=datetime(2026, 11, 21, 11, 36, 5, tzinfo=timezone.utc),
)


class RecordingApi:
    def __init__(self, answer: dict):
        self.answer = answer
        self.calls: list[dict] = []

    def __call__(self, **params) -> dict:
        self.calls.append(params)
        return self.answer


def test_read_page_missing():
    api = RecordingApi({"query": {"pages": {"-1": {"title": "הזנת תארי שחקני כדורגל", "missing": ""}}}})

    assert read_page(api) == MISSING


def test_read_page_returns_text_revision_and_editor():
    api = RecordingApi({"query": {"pages": {"2825": {
        "pageid": 2825, "title": "הזנת תארי שחקני כדורגל",
        "revisions": [{
            "revid": 4201, "user": "MaccabiBot", "timestamp": "2026-11-21T11:36:05Z",
            "slots": {"main": {"contentmodel": "wikitext", "*": "ישן"}},
        }],
    }}}})

    assert read_page(api) == EXISTING
    assert api.calls[0]["titles"] == "הזנת תארי שחקני כדורגל"


def test_read_page_sees_a_redirect():
    api = RecordingApi({"query": {"pages": {"2825": {
        "pageid": 2825, "title": "הזנת תארי שחקני כדורגל", "redirect": "",
        "revisions": [{"revid": 7, "user": "Someone", "timestamp": "2026-11-21T11:36:05Z",
                       "slots": {"main": {"*": "#הפניה [[עמוד אחר]]"}}}],
    }}}})

    assert read_page(api).is_redirect is True


def test_save_creates_only_when_the_page_was_missing():
    api = RecordingApi({"edit": {"result": "Success", "newrevid": 4300}})

    result = save_page(api, "חדש", MISSING, summary="בנייה")

    sent = api.calls[0]
    assert sent["action"] == "edit" and sent["text"] == "חדש" and sent["summary"] == "בנייה"
    assert sent["createonly"] == "1" and "baserevid" not in sent and "nocreate" not in sent
    assert result.changed is True and result.revision_id == 4300


def test_save_is_bound_to_the_revision_read():
    api = RecordingApi({"edit": {"result": "Success", "newrevid": 4300}})

    save_page(api, "חדש", EXISTING, summary="בנייה")

    sent = api.calls[0]
    assert sent["nocreate"] == "1" and sent["baserevid"] == 4201 and "createonly" not in sent


def test_save_reports_nochange():
    api = RecordingApi({"edit": {"result": "Success", "nochange": ""}})

    result = save_page(api, "ישן", EXISTING, summary="אחסון מחדש")

    assert result.changed is False and result.revision_id is None


def test_a_save_the_wiki_did_not_accept_raises():
    api = RecordingApi({"edit": {"result": "Failure", "abusefilter": {}}})

    with pytest.raises(RuntimeError, match="Failure"):
        save_page(api, "חדש", EXISTING, summary="בנייה")


def test_table_credits_counts_every_row():
    row = {"Player": "אבי נמני", "Season": "2000/01", "Competition": "גביע המדינה", "Page": "הזנת תארי שחקני כדורגל"}
    api = FakeCargoApi({"Football_Player_Titles": [dict(row, RowId="1"), dict(row, RowId="2")]})

    assert table_credits(api) == Counter({Credit("אבי נמני", "2000/01", "גביע המדינה"): 2})


def test_table_rows_of_another_page_raise():
    api = FakeCargoApi({"Football_Player_Titles": [{
        "Player": "אבי נמני", "Season": "2000/01", "Competition": "גביע המדינה",
        "Page": "תארי שחקני כדורגל - עמוד זמני", "RowId": "1",
    }]})

    with pytest.raises(ExportError, match="עמוד זמני"):
        table_credits(api)
