"""The two ways the job reaches a wiki: production through pywikibot, the local wiki through requests."""
from unittest.mock import MagicMock

import pytest
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
    request = site.simple_request.return_value
    if submit_error:
        request.submit.side_effect = submit_error
    else:
        request.submit.return_value = submit_result
    return site, request


def test_production_edit_carries_a_token_and_is_never_retried():
    site, request = production_site({"edit": {"result": "Success"}})
    api = production_api(site=site, pause=lambda seconds: None)

    assert api(action="edit", title="עמוד", text="טקסט") == {"edit": {"result": "Success"}}
    assert site.simple_request.call_args.kwargs["token"] == "TOKEN+\\"
    assert request.max_retries == 0


def test_production_read_keeps_pywikibot_retries_and_pauses_less_than_a_write():
    site, request = production_site({"cargoquery": []})
    pauses = []
    api = production_api(site=site, pause=pauses.append)
    retries_before = request.max_retries

    api(action="cargoquery", tables="Achievements")
    api(action="edit", title="עמוד", text="טקסט")

    assert "token" not in site.simple_request.call_args_list[0].kwargs
    assert request.max_retries == 0 and retries_before != 0
    assert pauses == [1, 3]


def test_production_api_error_becomes_an_api_error_with_its_code():
    site, _ = production_site(submit_error=APIError("editconflict", "Edit conflict."))
    api = production_api(site=site, pause=lambda seconds: None)

    with pytest.raises(ApiError) as raised:
        api(action="edit", title="עמוד", text="טקסט")

    assert raised.value.code == "editconflict"
