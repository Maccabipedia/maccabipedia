"""Does pywikibot actually SEND through the session we hooked?

PR #173 attached the unexpected-response logger to ``pywikibot.comms.http.session`` so the
next failing CI run would capture the body behind ``API userinfo response lacks 'query'
key``. Four failures have landed since; none logged anything. Two candidate causes:

  (a) the hook ran and judged the body healthy — it opened with ``{``, so it was a JSON
      *object* lacking ``query``, not the bare string we assumed;
  (b) the hook never ran, because pywikibot sends through some other session.

The existing suite only asserts the hook *attaches* to that session object. This module
asserts pywikibot's HTTP layer really drives it, which is what separates (a) from (b).
"""
import logging

import requests
from requests.adapters import HTTPAdapter

from maccabipediabot.common.maccabipedia_http import install_response_diagnostics

USERINFO_URL = (
    "https://www.maccabipedia.co.il/api.php"
    "?action=query&meta=userinfo&format=json&formatversion=2"
)


class _CannedAdapter(HTTPAdapter):
    """Answers every request with a fixed body, so nothing leaves the machine."""

    def __init__(self, body: str, content_type: str = "application/json"):
        super().__init__()
        self._body = body
        self._content_type = content_type

    def send(self, request, **kwargs):
        response = requests.Response()
        response.status_code = 200
        response.url = request.url
        response.request = request
        response._content = self._body.encode("utf-8")
        response.headers["Content-Type"] = self._content_type
        response.headers["Server"] = "openresty/1.29.2.3"
        response.raw = None
        return response


def _fetch_through_pywikibot(body: str, caplog):
    """Drive pywikibot's own HTTP layer against a canned body; return the captured log."""
    from pywikibot.comms import http as pw_http

    install_response_diagnostics(pw_http.session)
    original = dict(pw_http.session.adapters)
    pw_http.session.mount("https://www.maccabipedia.co.il", _CannedAdapter(body))
    try:
        with caplog.at_level(logging.ERROR):
            pw_http.fetch(USERINFO_URL)
    finally:
        pw_http.session.adapters.clear()
        pw_http.session.adapters.update(original)
    return caplog.text


def test_pywikibot_fetch_triggers_our_response_hook(caplog):
    """The load-bearing one. If this fails, cause (b) holds and #173 never had a chance."""
    captured = _fetch_through_pywikibot('"imunify360 block"', caplog)

    assert "Unexpected response from maccabipedia" in captured
    assert "imunify360 block" in captured
    assert "openresty/1.29.2.3" in captured


def test_the_userinfo_call_really_reaches_the_layer_this_module_drives():
    """The test above drives ``http.fetch``; the failure we care about starts at
    ``api.Request.submit``. Pin the chain between them, so an upstream restructure fails
    here loudly instead of quietly making this module prove nothing."""
    import inspect
    from pywikibot.comms import http as pw_http
    from pywikibot.data.api import _requests

    assert "http.request(" in inspect.getsource(_requests.Request._http_request)
    assert "fetch(" in inspect.getsource(pw_http.request)
    assert "session.request(" in inspect.getsource(pw_http.fetch)


def test_object_body_lacking_query_is_captured(caplog):
    """Cause (a) itself: an object opens with `{`, so the opening-byte check used to pass
    it while pywikibot still asserted on the missing 'query'. This is the body those 39
    failures threw away — it must now reach the log."""
    captured = _fetch_through_pywikibot('{"error": {"code": "blocked"}}', caplog)

    assert "userinfo response lacks 'query'" in captured
    assert "blocked" in captured
    assert "openresty/1.29.2.3" in captured


def test_healthy_userinfo_object_stays_quiet(caplog):
    captured = _fetch_through_pywikibot(
        '{"query": {"userinfo": {"name": "MaccabiBot", "groups": ["sysop"]}}}', caplog)

    assert "Unexpected response from maccabipedia" not in captured
