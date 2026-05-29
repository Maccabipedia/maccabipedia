"""Fixtures for the local-wiki integration suite.

Hits the running docker stack (default http://localhost:8080) and exposes
anonymous / admin / regular-user Maccabipedia-skin HTML bodies of the
Hebrew main page. All fixtures are session-scoped so the suite makes
minimal HTTP calls.

Shared constants (`MENU_LABELS`, `PHP_ERROR_RE`) live in
`skin_test_constants.py` (a uniquely-named module that doesn't collide
with the monorepo's other `conftest.py`s).
"""
from __future__ import annotations

import os
import re
from urllib.parse import quote

import pytest
import requests

# "עמוד ראשי" — Hebrew main page title, used by the local stack's MW config.
# MediaWiki canonicalises spaces to underscores in titles before percent-encoding,
# so we mirror that here (otherwise the URL hits a 404 instead of the article).
_MAIN_PAGE_TITLE = "עמוד_ראשי"
_ADMIN_USERNAME = "admin"
_ADMIN_PASSWORD = "devadminpass"  # see infra/local-wiki/docker-compose.yml
_REGULAR_USERNAME = "regular"
_REGULAR_PASSWORD = "regularpass"  # created via:
# docker exec local-wiki-mediawiki-1 php maintenance/createAndPromote.php regular regularpass --force


@pytest.fixture(scope="session")
def base_url() -> str:
    """Base URL of the wiki under test; override via MACCABIPEDIA_LOCAL_URL."""
    return os.environ.get("MACCABIPEDIA_LOCAL_URL", "http://localhost:8080").rstrip("/")


@pytest.fixture(scope="session")
def main_url(base_url: str) -> str:
    """Percent-encoded URL of the Hebrew main page.

    Local stack now serves pretty URLs ($wgArticlePath = /$1) to match prod,
    so the /index.php/ segment is gone.
    """
    return f"{base_url}/{quote(_MAIN_PAGE_TITLE)}"


@pytest.fixture(scope="session")
def admin_session(base_url: str) -> requests.Session:
    """A requests.Session logged in as the local admin via action=login.

    Skips cleanly when the API is unreachable or the credentials are rejected,
    so the test suite stays useful even on a partially-up stack.
    """
    session = requests.Session()
    api_url = f"{base_url}/api.php"

    try:
        token_response = session.get(
            api_url,
            params={
                "action": "query",
                "meta": "tokens",
                "type": "login",
                "format": "json",
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        pytest.skip(f"login token request failed: {exc}")

    login_token = token_response.json().get("query", {}).get("tokens", {}).get("logintoken")
    if not login_token:
        pytest.skip(f"couldn't fetch login token (response: {token_response.text})")

    login_response = session.post(
        api_url,
        data={
            "action": "login",
            "lgname": _ADMIN_USERNAME,
            "lgpassword": _ADMIN_PASSWORD,
            "lgtoken": login_token,
            "format": "json",
        },
        timeout=15,
    )
    result = login_response.json().get("login", {}).get("result")
    if result != "Success":
        pytest.skip(f"admin login failed (API result: {login_response.text})")

    return session


@pytest.fixture(scope="session")
def regular_session(base_url: str) -> requests.Session:
    """A logged-in session for a non-admin user.

    The user 'regular' / 'regularpass' is created by:
        docker exec local-wiki-mediawiki-1 php /var/www/html/maintenance/createAndPromote.php regular regularpass --force
    Skips cleanly if the account doesn't exist yet — run that command once
    when bootstrapping the local stack.
    """
    session = requests.Session()
    api_url = f"{base_url}/api.php"
    try:
        token_response = session.get(
            api_url,
            params={"action": "query", "meta": "tokens", "type": "login", "format": "json"},
            timeout=15,
        )
    except requests.RequestException as exc:
        pytest.skip(f"login token request failed: {exc}")
    login_token = token_response.json().get("query", {}).get("tokens", {}).get("logintoken")
    if not login_token:
        pytest.skip(f"couldn't fetch login token (response: {token_response.text})")
    login_response = session.post(
        api_url,
        data={
            "action": "login",
            "lgname": _REGULAR_USERNAME,
            "lgpassword": _REGULAR_PASSWORD,
            "lgtoken": login_token,
            "format": "json",
        },
        timeout=15,
    )
    result = login_response.json().get("login", {}).get("result")
    if result != "Success":
        pytest.skip(
            f"regular-user login failed (run createAndPromote.php first?): "
            f"{login_response.text}"
        )
    return session


@pytest.fixture(scope="session")
def maccabipedia_anon_html(main_url: str) -> str:
    """GET the main page with ?useskin=maccabipedia and return the body.

    Maccabipedia is the default skin, so the parameter is redundant here, but
    we pass it explicitly to keep the fixture pinned to Maccabipedia even if
    the default changes again.
    """
    response = requests.get(main_url, params={"useskin": "maccabipedia"}, timeout=15)
    assert response.status_code == 200, (
        f"useskin=maccabipedia GET {main_url} returned HTTP {response.status_code}"
    )
    return response.text


@pytest.fixture(scope="session")
def maccabipedia_special_recentchanges_html(base_url: str) -> str:
    """Special:Recentchanges, anon, ?useskin=maccabipedia. Special: pages
    take a different code path (no edit dropdown, no talk page) — regressions
    there don't surface on the main-page fixture."""
    url = f"{base_url}/index.php?title=Special:Recentchanges&useskin=maccabipedia"
    response = requests.get(url, timeout=15)
    assert response.status_code == 200, (
        f"useskin=maccabipedia GET {url} returned HTTP {response.status_code}"
    )
    return response.text


@pytest.fixture(scope="session")
def maccabipedia_admin_html(admin_session: requests.Session, main_url: str) -> str:
    """Main page, admin-logged-in, ?useskin=maccabipedia. Verifies admin-only
    items (delete/move/protect) + user dropdown shows logout/preferences."""
    response = admin_session.get(main_url, params={"useskin": "maccabipedia"}, timeout=15)
    assert response.status_code == 200
    return response.text


@pytest.fixture(scope="session")
def maccabipedia_regular_user_html(regular_session: requests.Session, main_url: str) -> str:
    """Main page, regular (non-admin) user logged in, ?useskin=maccabipedia.
    Verifies the edit dropdown's admin-only items (delete/move/protect) are
    correctly hidden — without this, accidental privilege leaks slip past
    the admin-only test (which only asserts admin items ARE visible)."""
    response = regular_session.get(main_url, params={"useskin": "maccabipedia"}, timeout=15)
    assert response.status_code == 200
    return response.text


@pytest.fixture(scope="session")
def maccabipedia_edit_mode_html(admin_session: requests.Session, main_url: str) -> str:
    """Main page rendered in action=edit mode, admin-logged-in (anon users
    don't have edit permission so the dropdown's edit link wouldn't render
    even when not gated). Edit dropdown should show "חזור לערך" (back to
    article view) instead of "עריכה" (open editor)."""
    response = admin_session.get(
        main_url, params={"useskin": "maccabipedia", "action": "edit"}, timeout=15
    )
    assert response.status_code == 200
    return response.text


@pytest.fixture(scope="session")
def maccabipedia_talk_page_html(base_url: str) -> str:
    """Talk-namespace page (שיחה:עמוד_ראשי), anon, ?useskin=maccabipedia.
    The page may not exist (HTTP 404) but the skin chrome must still render.
    Asserts the subject-back link points at the parent article."""
    url = f"{base_url}/{quote('שיחה:עמוד_ראשי')}?useskin=maccabipedia"
    response = requests.get(url, timeout=15, allow_redirects=True)
    # Talk page may or may not exist — chrome still renders either way.
    assert response.status_code in (200, 404), (
        f"GET {url} returned HTTP {response.status_code}"
    )
    return response.text


@pytest.fixture(scope="session")
def maccabipedia_oldid_html(main_url: str) -> tuple[str, str]:
    """Main page at ?oldid=<old_revision>&useskin=maccabipedia, returned as
    (html, oldid) so the regression test can assert that exact revision id is
    preserved in the edit/history action hrefs on the new skin."""
    history = requests.get(main_url, params={"action": "history", "useskin": "maccabipedia"}, timeout=15)
    assert history.status_code == 200
    oldid_match = re.search(r"oldid=(\d+)", history.text)
    if not oldid_match:
        pytest.skip("couldn't find an oldid in page history — only 1 revision?")
    oldid = oldid_match.group(1)
    response = requests.get(main_url, params={"useskin": "maccabipedia", "oldid": oldid}, timeout=15)
    assert response.status_code == 200
    return response.text, oldid
