"""The maccabipedia Imunify360 WAF 415s the default wildcard ``Accept: */*``, so every
request to the wiki must carry a concrete Accept. Guard that the shared session sets it."""
import logging

import requests

import pytest

from maccabipediabot.common.maccabipedia_http import (
    MACCABIPEDIA_JSON_HEADERS,
    build_maccabipedia_session,
    describe_unexpected_response,
    install_response_diagnostics,
    parse_cargo_rows,
)


def _response(url, status=200, body="[]", content_type="application/json", server="nginx"):
    response = requests.Response()
    response.status_code = status
    response.url = url
    response._content = body.encode("utf-8")
    response.headers["Content-Type"] = content_type
    response.headers["Server"] = server
    response.request = requests.Request(method="GET", url=url).prepare()
    return response


CARGO_URL = "https://www.maccabipedia.co.il/index.php?title=Special:CargoExport&format=json"
API_URL = "https://www.maccabipedia.co.il/api.php"


def test_json_headers_are_not_wildcard():
    assert MACCABIPEDIA_JSON_HEADERS == {"Accept": "application/json"}


def test_session_sends_concrete_accept_header():
    session = build_maccabipedia_session()
    accept = session.headers.get("Accept")
    assert accept == "application/json"
    assert accept != "*/*"


def test_session_retries_on_edge_415():
    session = build_maccabipedia_session()
    adapter = session.get_adapter("https://www.maccabipedia.co.il")
    assert 415 in adapter.max_retries.status_forcelist


# --- unexpected-response diagnostics ---------------------------------------------------
# The WAF block that outlived the Accept fix answers 200 with a body that parses as a bare
# JSON string. Those are the responses we must notice and dump.


def test_healthy_cargo_row_array_is_not_flagged():
    assert describe_unexpected_response(_response(CARGO_URL, body='[{"_pageName": "אבי כהן"}]')) is None


def test_healthy_api_object_is_not_flagged():
    assert describe_unexpected_response(_response(API_URL, body='{"query": {"userinfo": {}}}')) is None


USERINFO_URL = API_URL + "?action=query&meta=userinfo&format=json&formatversion=2"


def test_userinfo_object_without_query_is_flagged():
    """The 39-failure shape: pywikibot asserts `'query' in uidata` and drops the body."""
    reason = describe_unexpected_response(
        _response(USERINFO_URL, body='{"error": {"code": "blocked"}}'))
    assert reason is not None
    assert "lacks 'query'" in reason
    assert "error" in reason, "the top-level keys name what came back instead"


def test_healthy_userinfo_object_is_not_flagged():
    assert describe_unexpected_response(
        _response(USERINFO_URL, body='{"query": {"userinfo": {"name": "MaccabiBot"}}}')) is None


def test_userinfo_bare_string_still_reported_as_a_string():
    """The bare-string case must keep its own wording — it is a different diagnosis to
    hand the host than 'the API answered with an error object'."""
    reason = describe_unexpected_response(_response(USERINFO_URL, body='"blocked"'))
    assert reason is not None
    assert "bare string" in reason


def test_non_userinfo_object_is_judged_by_its_opening_byte_alone():
    """The parse is confined to userinfo. A 5000-row Cargo chunk must never be re-parsed
    by a hook that runs on every single response."""
    huge = "[" + ",".join('{"_pageName": "אבי כהן"}' for _ in range(5000)) + "]"
    assert describe_unexpected_response(_response(CARGO_URL, body=huge)) is None


def test_bare_json_string_body_is_flagged():
    """The exact shape behind 'str' object has no attribute 'items'."""
    reason = describe_unexpected_response(_response(CARGO_URL, body='"blocked"'))
    assert reason is not None
    assert "bare string" in reason


def test_non_json_body_is_flagged():
    reason = describe_unexpected_response(_response(API_URL, body="<html>blocked</html>"))
    assert reason is not None
    assert "not JSON" in reason


def test_empty_body_is_flagged():
    assert describe_unexpected_response(_response(API_URL, body="")) == "body is empty"


def test_leading_whitespace_does_not_confuse_the_check():
    assert describe_unexpected_response(_response(CARGO_URL, body='\n  [{"a": 1}]')) is None


def test_large_healthy_body_is_not_parsed():
    """The hook runs on every response, so a 5000-row Cargo chunk must stay O(1):
    it is judged by its opening byte, never re-parsed."""
    huge = "[" + ",".join('{"_pageName": "אבי כהן"}' for _ in range(5000)) + "]"
    assert describe_unexpected_response(_response(CARGO_URL, body=huge)) is None


def test_error_status_is_flagged():
    assert describe_unexpected_response(_response(API_URL, status=415, body="[]")) == "HTTP 415"


def test_other_hosts_are_ignored():
    assert describe_unexpected_response(_response("https://www.iva.org.il/api.php", body='"blocked"')) is None


def test_html_article_fetch_is_not_flagged():
    """Only api.php / format=json owe us JSON; plain article HTML must not be noise."""
    article = _response("https://www.maccabipedia.co.il/מכבי_תל_אביב",
                        body="<html>...</html>", content_type="text/html")
    assert describe_unexpected_response(article) is None


def test_hook_logs_body_and_passes_response_through(caplog):
    session = install_response_diagnostics(requests.Session())
    blocked = _response(CARGO_URL, body='"imunify360 block"', server="openresty/1.29.2.3")

    with caplog.at_level(logging.ERROR):
        results = [hook(blocked) for hook in session.hooks["response"]]

    # Returning None keeps requests from replacing the real response with the hook's value.
    assert results == [None]
    assert "imunify360 block" in caplog.text
    assert "openresty/1.29.2.3" in caplog.text


def test_hook_is_installed_once_per_session():
    session = build_maccabipedia_session()
    before = len(session.hooks["response"])
    install_response_diagnostics(session)
    assert len(session.hooks["response"]) == before


def test_pywikibot_shared_session_accepts_the_hook():
    """39 of the 59 post-fix CI failures die inside pw.Site(), so the diagnostics have to
    ride pywikibot's own session. Verify that session really takes our hook."""
    from pywikibot.comms import http as pw_http
    from maccabipediabot.common.maccabipedia_http import _log_unexpected_response

    install_response_diagnostics(pw_http.session)

    assert _log_unexpected_response in pw_http.session.hooks["response"]


def test_get_site_installs_the_diagnostics():
    """conftest stubs out get_site(), so assert on its source: the hook must be installed
    before pw.Site() runs, or the blocked login response is lost again."""
    import inspect
    from maccabipediabot.common import wiki_login

    source = inspect.getsource(wiki_login)
    install_line = source.index("install_response_diagnostics(pw_http.session)")
    site_line = source.index("site = pw.Site()")
    assert install_line < site_line


def test_hook_never_leaks_response_cookies(caplog):
    """Set-Cookie carries the logged-in session token; it must stay out of the log."""
    session = install_response_diagnostics(requests.Session())
    blocked = _response(API_URL, body='"blocked"')
    blocked.headers["Set-Cookie"] = "maccabipediaSession=SUPERSECRETVALUE; path=/"

    with caplog.at_level(logging.ERROR):
        for hook in session.hooks["response"]:
            hook(blocked)

    assert "blocked" in caplog.text, "sanity: the hook did log this response"
    assert "SUPERSECRETVALUE" not in caplog.text


# --- parse_cargo_rows ------------------------------------------------------------------
# CargoExport&format=json always answers with an array of row objects, and every caller
# indexes or iterates it as one. When it answers with something else the old code died far
# from the cause — `KeyError: 0` on `rows[0]`, or `string indices must be integers` from
# `for row in rows`, with the body already discarded. Fail at the parse instead, holding it.


def test_parse_cargo_rows_returns_the_rows():
    rows = parse_cargo_rows(_response(CARGO_URL, body='[{"_pageName": "אבי כהן"}]'))
    assert rows == [{"_pageName": "אבי כהן"}]


def test_parse_cargo_rows_allows_an_empty_result():
    """No rows is a legitimate answer — a date with no game — not a broken response."""
    assert parse_cargo_rows(_response(CARGO_URL, body="[]")) == []


def test_parse_cargo_rows_rejects_an_object():
    """The shape behind the calendar's `KeyError: 0`: an object where rows were owed."""
    with pytest.raises(ValueError, match="CargoExport returned a bare dict"):
        parse_cargo_rows(_response(CARGO_URL, body='{"error": "query failed"}'))


def test_parse_cargo_rows_rejects_a_bare_string():
    with pytest.raises(ValueError, match="CargoExport returned a bare str"):
        parse_cargo_rows(_response(CARGO_URL, body='"imunify360 block"'))


def test_parse_cargo_rows_rejects_a_non_json_body():
    with pytest.raises(ValueError, match="CargoExport returned a non-JSON body"):
        parse_cargo_rows(_response(CARGO_URL, body="<html>blocked</html>"))


def test_parse_cargo_rows_logs_the_body_it_rejected(caplog):
    """The object case slips past the response hook (it opens with `{`, so it looks like
    healthy JSON), so this is the only place that body ever gets recorded."""
    with caplog.at_level(logging.ERROR):
        with pytest.raises(ValueError):
            parse_cargo_rows(_response(CARGO_URL, body='{"error": "query failed"}',
                                       server="openresty/1.29.2.3"))

    assert "query failed" in caplog.text
    assert "openresty/1.29.2.3" in caplog.text
