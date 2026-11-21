"""How the job calls a wiki's API: `api(**params)` returns the decoded JSON object.

Two implementations with one shape, so everything above them runs unchanged against
production (through pywikibot's logged-in session) and against the local test wiki.
"""
from __future__ import annotations

import time
from collections.abc import Callable

import pywikibot
import requests
from pywikibot.exceptions import APIError

from maccabipediabot.common.wiki_login import get_site

Api = Callable[..., dict]

WRITE_ACTIONS = frozenset({"edit"})

# Production allows about one request a second from a script, and a save needs a longer
# gap: the shared host answers 508 when saves come faster.
READ_PAUSE_SECONDS = 1
WRITE_PAUSE_SECONDS = 3

# Saving the data page stores every row again and takes far longer than pywikibot's
# default 45 s read timeout allows.
CONNECT_TIMEOUT_SECONDS = 6.05
WRITE_TIMEOUT_SECONDS = 300

_ERROR_SNIPPET_LIMIT = 500


class ApiError(RuntimeError):
    """The wiki refused the request, or answered with something that is not its API."""

    def __init__(self, code: str, info: str):
        super().__init__(f"{code}: {info}")
        self.code = code
        self.info = info


def production_api(site: pywikibot.Site | None = None, pause: Callable[[float], None] = time.sleep) -> Api:
    """The production wiki, through pywikibot's logged-in session.

    A write is sent once. pywikibot would otherwise send a timed-out save again while the
    first one may still be storing rows; the caller reads the page back instead.
    """
    if site is None:
        pywikibot.config.socket_timeout = (CONNECT_TIMEOUT_SECONDS, WRITE_TIMEOUT_SECONDS)
        site = get_site()

    def call(**params) -> dict:
        is_write = params.get("action") in WRITE_ACTIONS
        if is_write:
            params["token"] = site.tokens["csrf"]
        request = site.simple_request(**params)
        if is_write:
            request.max_retries = 0
        try:
            return request.submit()
        except APIError as error:
            raise ApiError(error.code, error.info) from error
        finally:
            pause(WRITE_PAUSE_SECONDS if is_write else READ_PAUSE_SECONDS)

    return call


def local_api(api_url: str, user: str, password: str, session: requests.Session | None = None) -> Api:
    """The local test wiki, logged in with its admin account."""
    session = session or requests.Session()

    def post(**params) -> dict:
        response = session.post(api_url, data={"format": "json", **params}, timeout=WRITE_TIMEOUT_SECONDS)
        content_type = response.headers.get("Content-Type", "")
        if response.status_code != 200 or "application/json" not in content_type:
            raise ApiError(
                f"http-{response.status_code}",
                f"not an API answer ({content_type}): {response.text[:_ERROR_SNIPPET_LIMIT]}",
            )
        payload = response.json()
        if "error" in payload:
            raise ApiError(payload["error"].get("code", "unknown"), payload["error"].get("info", ""))
        return payload

    login_token = post(action="query", meta="tokens", type="login")["query"]["tokens"]["logintoken"]
    login = post(action="login", lgname=user, lgpassword=password, lgtoken=login_token)["login"]
    if login["result"] != "Success":
        raise ApiError("login", f"the local wiki answered {login['result']}")

    def call(**params) -> dict:
        if params.get("action") in WRITE_ACTIONS:
            params["token"] = post(action="query", meta="tokens")["query"]["tokens"]["csrftoken"]
        return post(**params)

    return call
