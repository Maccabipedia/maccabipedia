"""The two ways the job reaches a wiki: production through pywikibot, the local wiki through requests."""
from unittest.mock import MagicMock

import pytest
import requests
from pywikibot.exceptions import APIError

from maccabipediabot.maintenance.football.player_titles.api import ApiError, local_api, production_api


class FakeResponse:
    def __init__(self, payload=None, status_code=200, content_type="application/json; charset=utf-8", text=""):
        self.payload, self.status_code, self.text = payload, status_code, text
        self.headers = {"Content-Type": content_type}

    def json(self):
        return self.payload


class FakeSession:
    """Answers the login handshake and token requests; `answer` handles everything else."""

    def __init__(self, answer):
        self.answer = answer
        self.posts: list[dict] = []

    def post(self, url, data, timeout):
        self.posts.append(data)
        if data.get("meta") == "tokens":
            token_name = "logintoken" if data.get("type") == "login" else "csrftoken"
            return FakeResponse({"query": {"tokens": {token_name: "TOKEN+\\"}}})
        if data["action"] == "login":
            return FakeResponse({"login": {"result": "Success"}})
        return self.answer(data)


def test_local_api_logs_in_and_returns_the_decoded_answer():
    session = FakeSession(lambda data: FakeResponse({"cargoquery": []}))

    api = local_api("http://localhost:8080/api.php", "user", "password", session=session)

    assert api(action="cargoquery", tables="Achievements") == {"cargoquery": []}
    assert session.posts[1]["lgname"] == "user"
    assert session.posts[-1]["format"] == "json"


def test_local_api_adds_a_token_to_an_edit():
    session = FakeSession(lambda data: FakeResponse({"edit": {"result": "Success"}}))
    api = local_api("http://localhost:8080/api.php", "user", "password", session=session)

    api(action="edit", title="עמוד", text="טקסט")

    assert session.posts[-1]["token"] == "TOKEN+\\"


def test_local_api_raises_on_an_html_error_page():
    session = FakeSession(lambda data: FakeResponse(content_type="text/html", text="<html>Internal error</html>"))
    api = local_api("http://localhost:8080/api.php", "user", "password", session=session)

    with pytest.raises(ApiError, match="Internal error"):
        api(action="cargoquery", tables="Achievements")


def test_local_api_raises_on_an_api_error_with_its_code():
    session = FakeSession(lambda data: FakeResponse({"error": {"code": "editconflict", "info": "Edit conflict."}}))
    api = local_api("http://localhost:8080/api.php", "user", "password", session=session)

    with pytest.raises(ApiError) as raised:
        api(action="edit", title="עמוד", text="טקסט")

    assert raised.value.code == "editconflict"


def test_local_api_refuses_a_failed_login():
    session = FakeSession(lambda data: FakeResponse({}))
    session.post = lambda url, data, timeout: FakeResponse(
        {"query": {"tokens": {"logintoken": "T"}}} if data.get("meta") == "tokens" else {"login": {"result": "Failed"}}
    )

    with pytest.raises(ApiError, match="Failed"):
        local_api("http://localhost:8080/api.php", "user", "wrong", session=session)




def production_site(submit_result=None, submit_error=None):
    site = MagicMock()
    site.tokens = {"csrf": "TOKEN+\\"}
    site.base_url.return_value = "https://wiki.example/api.php"
    request = site.simple_request.return_value
    if submit_error:
        request.submit.side_effect = submit_error
    else:
        request.submit.return_value = submit_result
    return site, request


class RecordingPost:
    """Stands in for the logged-in session's `post`."""

    def __init__(self, response=None, error=None):
        self.response, self.error = response, error
        self.calls: list[dict] = []

    def __call__(self, url, files, headers, timeout):
        self.calls.append({"url": url, "files": files, "headers": headers, "timeout": timeout})
        if self.error:
            raise self.error
        return self.response


def test_production_edit_goes_out_once_as_multipart_with_a_token():
    """Not through pywikibot's request: its urlencoded edits have been refused by the host's
    firewall, its own multipart encoding gets HTTP 400, and it re-sends what it cannot read."""
    site, _ = production_site()
    post = RecordingPost(FakeResponse({"edit": {"result": "Success", "newrevid": 7}}))
    api = production_api(site=site, pause=lambda seconds: None, post=post)

    assert api(action="edit", title="עמוד", text="טקסט", baserevid=4201) == {"edit": {"result": "Success", "newrevid": 7}}

    site.simple_request.assert_not_called()
    assert len(post.calls) == 1
    sent = post.calls[0]
    assert sent["url"] == "https://wiki.example/api.php"
    assert sent["files"] == {
        "action": (None, "edit"), "title": (None, "עמוד"), "text": (None, "טקסט"), "baserevid": (None, "4201"),
        "token": (None, "TOKEN+\\"), "format": (None, "json"),
    }
    assert sent["headers"] == {"Accept": "application/json"}


def test_production_read_goes_through_pywikibot_and_pauses_less_than_a_write():
    site, _ = production_site({"cargoquery": []})
    post = RecordingPost(FakeResponse({"edit": {"result": "Success"}}))
    pauses = []
    api = production_api(site=site, pause=pauses.append, post=post)

    assert api(action="cargoquery", tables="Achievements") == {"cargoquery": []}
    api(action="edit", title="עמוד", text="טקסט")

    assert site.simple_request.call_args.kwargs == {"action": "cargoquery", "tables": "Achievements"}
    assert pauses == [1, 3]


@pytest.mark.parametrize("response", [
    FakeResponse(status_code=400, content_type="text/html", text="<h1>Bad Request</h1>"),
    FakeResponse(status_code=302, content_type="text/html", text="abuse page"),
    FakeResponse(status_code=200, content_type="text/html", text="<b>Notice</b>: PHP"),
], ids=["400", "a firewall redirect", "a PHP notice instead of JSON"])
def test_production_save_with_an_unreadable_answer_is_reported_as_unknown(response):
    """The save may have gone through; the caller has to read the page back."""
    site, _ = production_site()
    api = production_api(site=site, pause=lambda seconds: None, post=RecordingPost(response))

    with pytest.raises(ApiError) as raised:
        api(action="edit", title="עמוד", text="טקסט")

    assert raised.value.code == "no-answer"


def test_production_save_that_times_out_is_reported_as_unknown():
    site, _ = production_site()
    post = RecordingPost(error=requests.exceptions.ReadTimeout("read timed out"))
    api = production_api(site=site, pause=lambda seconds: None, post=post)

    with pytest.raises(ApiError) as raised:
        api(action="edit", title="עמוד", text="טקסט")

    assert raised.value.code == "no-answer"


def test_production_save_the_wiki_refuses_carries_the_wikis_code():
    site, _ = production_site()
    post = RecordingPost(FakeResponse({"error": {"code": "editconflict", "info": "Edit conflict."}}))
    api = production_api(site=site, pause=lambda seconds: None, post=post)

    with pytest.raises(ApiError) as raised:
        api(action="edit", title="עמוד", text="טקסט")

    assert raised.value.code == "editconflict"


def test_production_read_error_becomes_an_api_error_with_its_code():
    site, _ = production_site(submit_error=APIError("internal_api_error_MWException", "Caught exception"))
    api = production_api(site=site, pause=lambda seconds: None, post=RecordingPost())

    with pytest.raises(ApiError) as raised:
        api(action="cargoquery", tables="Football_Player_Titles")

    assert raised.value.code == "internal_api_error_MWException"
