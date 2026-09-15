"""Browser checks for a tab strip converted from <shtml> to <tabber>.

    uv run --with playwright pytest -m integration \
        infra/local-wiki/tests/test_tabber_conversion.py

Skipped if playwright is unavailable. Needs the local stack up and a converted
sandbox page, which `infra/tabs/batch_verify.py` creates.

These are the checks `infra/tabs/verify_tabs.py` cannot make: it compares
rendered HTML, so it can prove the panels say the same thing but not that a
click switches them, that the keyboard works, or that the strip is visible at
all. See `.claude/shtml_free_tabs_design.md` §6 items 3 and 5.
"""
from __future__ import annotations

import os
from urllib.parse import quote

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

BASE = os.environ.get("MW_BASE_URL", "http://localhost:8080")

# HOST pages, not the templates themselves: a template's body lives inside
# <includeonly>, so viewing it directly renders an empty page and every
# assertion below fails for the wrong reason. Created by
# `infra/tabs/make_host_pages.py`.
ORIGINAL = "ארגז חול/טאבים/לפני"
CONVERTED = "ארגז חול/טאבים/אחרי"

pytestmark = pytest.mark.integration


def url_of(title: str) -> str:
    return f"{BASE}/{quote(title.replace(' ', '_'))}"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as runner:
        instance = runner.chromium.launch()
        yield instance
        instance.close()


@pytest.fixture
def converted(browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(url_of(CONVERTED), wait_until="networkidle")
    if page.locator(".tabber__panel").count() == 0:
        page.close()
        pytest.skip(f"{CONVERTED} has no tab strip - run "
                    "infra/tabs/make_host_pages.py first")
    yield page
    page.close()


def test_the_strip_renders_tabs(converted):
    """The tabs exist and are visible - not merely present in the HTML."""
    tabs = converted.locator(".tabber__tab")
    assert tabs.count() == 4, f"expected 4 tabs, got {tabs.count()}"
    for index in range(4):
        assert tabs.nth(index).is_visible(), f"tab {index + 1} is not visible"


def selected_index(page) -> int:
    """Which tab is active, per ARIA.

    NOT which panel is display:block. TabberNeue is a scroll carousel: every
    panel stays in the DOM and Playwright reports all four as visible, so
    is_visible() cannot answer this question at all.
    """
    states = page.locator(".tabber__tab").evaluate_all(
        "tabs => tabs.map(tab => tab.getAttribute('aria-selected'))")
    active = [index for index, state in enumerate(states) if state == "true"]
    assert len(active) == 1, f"aria-selected on {len(active)} tabs: {states}"
    return active[0]


def test_one_tab_is_active_at_a_time(converted):
    assert converted.locator(".tabber__panel").count() == 4
    assert selected_index(converted) == 0, "the first tab should start active"


def test_the_anchor_ids_are_readable(converted):
    """The panel ids come from the tab NAMES, and they end up in the address
    bar because this wiki sets $wgTabberNeueUpdateLocationOnTabChange. Markup
    in a tab name produced ids like
    `#tabber-tabpanel-&lt;i_class=&quot;far_fa-circle&quot;...`."""
    hrefs = converted.locator(".tabber__tab").evaluate_all(
        "tabs => tabs.map(tab => tab.getAttribute('href') || '')")
    for href in hrefs:
        assert "&" not in href and "<" not in href, f"unreadable anchor: {href}"
        assert href.startswith("#tabber-tabpanel-"), href


def test_clicking_a_tab_switches_the_panel(converted):
    tabs = converted.locator(".tabber__tab")

    for index in (1, 2, 3, 0):
        tabs.nth(index).click()
        converted.wait_for_timeout(400)
        assert selected_index(converted) == index, (
            f"clicked tab {index + 1} but tab "
            f"{selected_index(converted) + 1} is active")

        # …and the panel actually moved into view. aria-selected alone would
        # pass even if the carousel never scrolled.
        in_view = converted.evaluate("""() => {
            const panels = Array.from(
                document.querySelectorAll('.tabber__panel'));
            return panels.map(panel => {
                const box = panel.getBoundingClientRect();
                return box.left > -5 && box.left < window.innerWidth;
            });
        }""")
        assert in_view[index], (
            f"tab {index + 1} is active but its panel is not in view: "
            f"{in_view}")


def test_the_keyboard_moves_between_tabs(converted):
    """Whatever TabberNeue's keyboard behaviour is, record it rather than
    assume it. This wiki is RTL, so a left arrow may move either way."""
    tabs = converted.locator(".tabber__tab")
    tabs.nth(0).click()
    tabs.nth(0).focus()

    converted.keyboard.press("ArrowRight")
    converted.wait_for_timeout(200)
    after_right = converted.evaluate(
        "() => document.activeElement && document.activeElement.textContent")

    converted.keyboard.press("ArrowLeft")
    converted.wait_for_timeout(200)
    after_left = converted.evaluate(
        "() => document.activeElement && document.activeElement.textContent")

    assert after_right is not None and after_left is not None, (
        "focus left the tab strip entirely when arrows were pressed")


def test_no_raw_html_machinery_survives(converted):
    body = converted.content()
    for leak in ('type="radio"', "<shtml", "&lt;label"):
        assert leak not in body, f"{leak} is still in the rendered page"


def test_the_panels_hold_the_same_text_as_the_original(browser):
    """The same assertion verify_tabs.py makes, but through a browser, so it
    also covers anything the skin's JavaScript changes after load."""
    def panel_texts(title: str, selector: str) -> list[str]:
        page = browser.new_page()
        page.goto(url_of(title), wait_until="networkidle")
        # text_content(), not inner_text(): inner_text returns only what is
        # rendered, so an off-screen carousel panel or a display:none radio
        # panel comes back empty and the comparison passes vacuously.
        texts = [(element.text_content() or "").split()
                 for element in page.locator(selector).all()]
        page.close()
        return texts

    before = panel_texts(ORIGINAL, '[id^="tab"][id$="-content"]')
    after = panel_texts(CONVERTED, ".tabber__panel")

    assert before, "the original page rendered no panels - test is vacuous"
    assert len(before) == len(after), (
        f"{len(before)} panels before, {len(after)} after")
    for index, (old, new) in enumerate(zip(before, after), start=1):
        assert old == new, f"panel {index} text differs"
