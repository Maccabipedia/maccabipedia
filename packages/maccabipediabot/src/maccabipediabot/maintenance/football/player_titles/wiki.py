"""The data page and its table on a wiki: read the page, save it, read the rows back."""
from __future__ import annotations

import time
from collections import Counter
from datetime import datetime
from typing import NamedTuple

from maccabipediabot.maintenance.football.player_titles.api import Api
from maccabipediabot.maintenance.football.player_titles.exports import ExportError, cargo_rows
from maccabipediabot.maintenance.football.player_titles.page import PAGE_TITLE
from maccabipediabot.maintenance.football.player_titles.rule import Credit

TABLE = "Football_Player_Titles"


class PageState(NamedTuple):
    """The page as it was read: what a later save is bound to."""
    exists: bool
    is_redirect: bool
    text: str
    revision_id: int | None
    last_editor: str | None
    last_edit: datetime | None


class SaveResult(NamedTuple):
    changed: bool
    revision_id: int | None
    seconds: float


def logged_in_user(api: Api) -> str:
    """The account this session writes as, spelled the way the wiki records an editor."""
    user = api(action="query", meta="userinfo")["query"]["userinfo"]
    if "anon" in user:
        raise RuntimeError("the session is not logged in")
    return user["name"]


def read_page(api: Api, title: str = PAGE_TITLE) -> PageState:
    response = api(
        action="query", prop="revisions|info", titles=title,
        rvprop="content|ids|timestamp|user", rvslots="main",
    )
    page = next(iter(response["query"]["pages"].values()))
    if "missing" in page:
        return PageState(exists=False, is_redirect=False, text="", revision_id=None, last_editor=None, last_edit=None)

    revision = page["revisions"][0]
    return PageState(
        exists=True,
        is_redirect="redirect" in page,
        text=revision["slots"]["main"]["*"],
        revision_id=revision["revid"],
        last_editor=revision["user"],
        last_edit=datetime.fromisoformat(revision["timestamp"].replace("Z", "+00:00")),
    )


def save_page(api: Api, text: str, state: PageState, summary: str, title: str = PAGE_TITLE) -> SaveResult:
    """Save `text` over exactly the revision that was read.

    A page that did not exist may only be created; a page that existed may only be edited
    on top of `state.revision_id`. Anything that happened in between surfaces as an API
    error (`articleexists`, `missingtitle`, `editconflict`) instead of being overwritten.
    """
    if state.exists:
        binding = {"nocreate": "1", "baserevid": state.revision_id}
    else:
        binding = {"createonly": "1"}

    started = time.monotonic()
    edit = api(action="edit", title=title, text=text, summary=summary, bot="1", **binding)["edit"]
    seconds = time.monotonic() - started

    if edit.get("result") != "Success":
        raise RuntimeError(f"the wiki did not accept the save of {title}: {edit}")
    return SaveResult(changed="nochange" not in edit, revision_id=edit.get("newrevid"), seconds=seconds)


def table_credits(api: Api, title: str = PAGE_TITLE) -> Counter[Credit]:
    """Every row of the table, counted, so a row stored twice shows as a count of 2.

    Only the data page may store rows; a row from any other page is an error.
    """
    rows = cargo_rows(
        api, key=("RowId",), count_field="COUNT(*)=n",
        tables=TABLE, fields="Player, Season, Competition, _pageName=Page, _ID=RowId", order_by="_ID",
    )
    other_pages = sorted({row["Page"] for row in rows if row["Page"] != title})
    if other_pages:
        raise ExportError(f"{TABLE} holds rows stored by other pages: {', '.join(other_pages)}")
    return Counter(Credit(row["Player"], row["Season"], row["Competition"]) for row in rows)
