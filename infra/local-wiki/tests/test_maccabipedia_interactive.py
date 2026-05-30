"""Playwright-driven interaction tests for the Maccabipedia skin.

The pytest tests in test_maccabipedia_scaffold.py only inspect rendered
HTML strings. Things they cannot catch:
  - Hover-to-open dropdown menus (the .dropdown-content max-height
    transition fires on .dropdown-container:hover)
  - Mobile menu toggle (`.mobile-side-menu-trigger` click)
  - Keyboard-accessible dropdown alternatives (none currently — gap)

This file requires playwright (installed via `uv run --with playwright`)
and the chromium browser. Run with::

    uv run --with playwright pytest -m integration \
        infra/local-wiki/tests/test_maccabipedia_interactive.py

Skipped if playwright isn't available.
"""
from __future__ import annotations

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

pytestmark = pytest.mark.integration

# Maccabipedia is the default skin, so no ?useskin override — these exercise
# the real default experience.
LOCAL = "http://localhost:8080"
HOME_URL = f"{LOCAL}/%D7%A2%D7%9E%D7%95%D7%93_%D7%A8%D7%90%D7%A9%D7%99"
WIDE_VIEWPORT = {"width": 1440, "height": 900}


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


def _open_page(browser, viewport=WIDE_VIEWPORT):
    """Helper: spawn a fresh context, render the home page, return page."""
    ctx = browser.new_context(viewport=viewport, locale="he-IL")
    page = ctx.new_page()
    page.goto(HOME_URL, wait_until="networkidle", timeout=30000)
    return ctx, page


def test_primary_dropdown_opens_on_hover(browser):
    """Hovering over a primary dropdown title (e.g. 'מכבי תל אביב') must
    expand the .dropdown-content from max-height:0 to a visible height.
    This is pure CSS (no JS), but it's the only way users can navigate."""
    ctx, page = _open_page(browser)
    try:
        title = page.locator(".dropdown-title", has_text="מכבי תל אביב").first
        title.scroll_into_view_if_needed()

        container = page.locator(".dropdown-container", has_text="מכבי תל אביב").first
        content = container.locator(".dropdown-content").first

        before = content.bounding_box()
        title.hover()
        page.wait_for_timeout(400)  # let the max-height transition complete
        after = content.bounding_box()

        assert before is not None and after is not None, "dropdown elements not found"
        assert before["height"] < 5, f"dropdown was already open before hover (h={before['height']})"
        assert after["height"] > 50, (
            f"dropdown did not expand on hover (before={before['height']}, after={after['height']}) "
            f"— hover-to-open is broken"
        )
    finally:
        ctx.close()


def test_user_dropdown_opens_on_hover(browser):
    """The user dropdown (right side of the options panel) must also open
    on hover so anonymous users can find the login link."""
    ctx, page = _open_page(browser)
    try:
        # The user dropdown's title contains the fa-user icon
        title = page.locator(".options-navigation-container .dropdown-title").filter(
            has=page.locator(".fa-user")
        ).first
        title.scroll_into_view_if_needed()

        container = title.locator("xpath=..")
        content = container.locator(".dropdown-content").first

        title.hover()
        page.wait_for_timeout(400)
        after = content.bounding_box()

        assert after is not None
        assert after["height"] > 30, (
            f"user dropdown did not expand on hover (h={after['height']})"
        )
        # The login link must be reachable
        assert page.locator("a", has_text="כניסה לחשבון").first.is_visible(), (
            "login link not visible after hovering the user dropdown"
        )
    finally:
        ctx.close()


def test_search_form_submits(browser):
    """Type a query in the header search input + submit → wiki returns a
    page (direct hit on a matching article, or Special:Search results).
    Validates the form's `action` URL + `name="search"` input wiring."""
    from urllib.parse import unquote
    ctx, page = _open_page(browser)
    try:
        page.fill("#searchInput", "ערן זהבי")
        with page.expect_navigation(wait_until="domcontentloaded", timeout=10000):
            page.locator("form#searchform").evaluate("f => f.submit()")
        # The URL is percent-encoded; compare against the decoded form so we
        # accept both direct hits ("/ערן_זהבי") and search-result pages.
        decoded = unquote(page.url)
        assert "ערן" in decoded or "Special:Search" in decoded or "search=" in decoded, (
            f"search submission landed somewhere unexpected: {page.url} (decoded: {decoded})"
        )
    finally:
        ctx.close()
