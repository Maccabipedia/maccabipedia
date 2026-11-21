"""How the job calls a wiki's API: `api(**params)` returns the decoded JSON object.

Two implementations with one shape, so everything above them runs unchanged against
production (through pywikibot's logged-in session) and against the local test wiki.
"""
from __future__ import annotations

import time
from collections.abc import Callable

import pywikibot
import requests
from pywikibot.comms import http as pywikibot_http
from pywikibot.exceptions import APIError

from maccabipediabot.common.maccabipedia_http import MACCABIPEDIA_JSON_HEADERS
from maccabipediabot.common.wiki_login import get_site

Api = Callable[..., dict]

WRITE_ACTIONS = frozenset({"edit"})

# Production allows about one request a second from a script, and a save needs a longer
# gap: the shared host answers 508 when saves come faster.
READ_PAUSE_SECONDS = 1
WRITE_PAUSE_SECONDS = 3

# Saving the data page stores every row again and takes far longer than pywikibot's
# default 45 s read timeout allows.
WRITE_TIMEOUT_SECONDS = 300

_ERROR_SNIPPET_LIMIT = 500


class ApiError(RuntimeError):
    """The wiki refused the request, or answered with something that is not its API.

    The code `no-answer` on a write means "unknown": the save may have gone through, and
    the page has to be read back before anything is sent again.
    """

    def __init__(self, code: str, info: str):
        super().__init__(f"{code}: {info}")
        self.code = code
        self.info = info


def _decoded(response: requests.Response) -> dict:
    """The API's JSON object, or an ApiError for anything else."""
    content_type = response.headers.get("Content-Type", "")
    if response.status_code != 200 or "application/json" not in content_type:
        raise ApiError(
            "no-answer",
            f"HTTP {response.status_code} ({content_type}): {response.text[:_ERROR_SNIPPET_LIMIT]}",
        )
    payload = response.json()
    if "error" in payload:
        raise ApiError(payload["error"].get("code", "unknown"), payload["error"].get("info", ""))
    return payload


def production_api(
    site: pywikibot.Site | None = None,
    pause: Callable[[float], None] = time.sleep,
    post: Callable[..., requests.Response] | None = None,
) -> Api:
    """The production wiki. Reads go through pywikibot; a write is one multipart POST.

    A write does not go through pywikibot's request. Its urlencoded edit bodies have been
    refused by the host's firewall, its own multipart encoding is answered with HTTP 400,
    and it re-sends a request whose answer it could not read - while the first save may
    still be storing rows. So the edit is posted once, over pywikibot's logged-in session,
    with `files=`, which makes requests encode it as multipart/form-data.
    """
    site = site or get_site()
    post = post or pywikibot_http.session.post

    def write(params: dict) -> dict:
        fields = {**params, "token": site.tokens["csrf"], "format": "json"}
        try:
            response = post(
                site.base_url("/api.php"),
                files={name: (None, str(value)) for name, value in fields.items()},
                headers=MACCABIPEDIA_JSON_HEADERS,
                timeout=WRITE_TIMEOUT_SECONDS,
            )
        except requests.RequestException as error:
            raise ApiError("no-answer", f"{type(error).__name__}: {error}") from error
        return _decoded(response)

    def call(**params) -> dict:
        is_write = params.get("action") in WRITE_ACTIONS
        try:
            if is_write:
                return write(params)
            return site.simple_request(**params).submit()
        except APIError as error:
            raise ApiError(error.code, error.info) from error
        finally:
            pause(WRITE_PAUSE_SECONDS if is_write else READ_PAUSE_SECONDS)

    return call


def local_api(api_url: str, user: str, password: str, session: requests.Session | None = None) -> Api:
    """The local test wiki, logged in with its admin account."""
    session = session or requests.Session()

    def post(**params) -> dict:
        return _decoded(session.post(api_url, data={"format": "json", **params}, timeout=WRITE_TIMEOUT_SECONDS))

    login_token = post(action="query", meta="tokens", type="login")["query"]["tokens"]["logintoken"]
    login = post(action="login", lgname=user, lgpassword=password, lgtoken=login_token)["login"]
    if login["result"] != "Success":
        raise ApiError("login", f"the local wiki answered {login['result']}")

    def call(**params) -> dict:
        if params.get("action") in WRITE_ACTIONS:
            params["token"] = post(action="query", meta="tokens")["query"]["tokens"]["csrftoken"]
        return post(**params)

    return call
