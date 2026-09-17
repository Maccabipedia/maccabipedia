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
from urllib.parse import quote, unquote

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
# Two converted strips on one page, written by
# scratchpad probe / infra/tabs/make_host_pages.py.
TWO_STRIPS = "ארגז חול/טאבים/שני מדפים"

pytestmark = pytest.mark.integration

# The FIRST converted widget on the host page. A referee section has four
# (a page-level count of 16 tabs is not "4 tabs"), and on a profile-3 page they
# sit inside the page's own native tabber, whose tabs are not ours to test.
TAB = ".tabber-converted >> nth=0 >> .tabber__tab"
PANEL = ".tabber-converted >> nth=0 >> .tabber__panel"
OLD_PANEL = '.slim-tabs >> nth=0 >> [id^="tab"][id$="-content"]'


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
    tabs = converted.locator(TAB)
    assert tabs.count() == 4, f"expected 4 tabs, got {tabs.count()}"
    for index in range(4):
        assert tabs.nth(index).is_visible(), f"tab {index + 1} is not visible"


def selected_index(page) -> int:
    """Which tab is active, per ARIA.

    NOT which panel is display:block. TabberNeue is a scroll carousel: every
    panel stays in the DOM and Playwright reports all four as visible, so
    is_visible() cannot answer this question at all.
    """
    states = page.locator(TAB).evaluate_all(
        "tabs => tabs.map(tab => tab.getAttribute('aria-selected'))")
    active = [index for index, state in enumerate(states) if state == "true"]
    assert len(active) == 1, f"aria-selected on {len(active)} tabs: {states}"
    return active[0]


def test_one_tab_is_active_at_a_time(converted):
    assert converted.locator(PANEL).count() == 4
    assert selected_index(converted) == 0, "the first tab should start active"


def test_the_anchor_ids_are_readable(converted):
    """The panel ids come from the tab NAMES, and they end up in the address
    bar because this wiki sets $wgTabberNeueUpdateLocationOnTabChange. Markup
    in a tab name produced ids like
    `#tabber-tabpanel-&lt;i_class=&quot;far_fa-circle&quot;...`."""
    hrefs = converted.locator(TAB).evaluate_all(
        "tabs => tabs.map(tab => tab.getAttribute('href') || '')")
    for href in hrefs:
        assert "&" not in href and "<" not in href, f"unreadable anchor: {href}"
        assert href.startswith("#tabber-tabpanel-"), href


def test_clicking_a_tab_switches_the_panel(converted):
    tabs = converted.locator(TAB)

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
    tabs = converted.locator(TAB)
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
        # Per panel: its rows, each row's words kept together - so a name
        # stays paired with its number - and the rows sorted, because a ranked
        # list whose template orders by count alone returns ties in any order.
        # A panel without row elements falls back to its words in order.
        texts = []
        for element in page.locator(selector).all():
            rows = element.evaluate("""panel => Array.from(panel.querySelectorAll(
                '.Top10Row, .atom-records-list-player-row, .tab-header'))
                .map(row => row.textContent.split(/\\s+/).filter(Boolean).join(' '))""")
            texts.append(sorted(rows) if rows
                         else (element.text_content() or "").split())
        page.close()
        return texts

    before = panel_texts(ORIGINAL, OLD_PANEL)
    after = panel_texts(CONVERTED, PANEL)

    assert before, "the original page rendered no panels - test is vacuous"
    assert len(before) == len(after), (
        f"{len(before)} panels before, {len(after)} after")
    for index, (old, new) in enumerate(zip(before, after), start=1):
        # Rows compared as whole rows (name with its number). Which member of
        # a tie at the top-ten boundary is shown is proven per widget by its
        # own comparison (compare_referee_leaderboards.py), not here.
        assert old == new, f"panel {index} rows differ"

# --- URL, refresh and history -------------------------------------------------
#
# The strip being replaced never touched the URL: a refresh always came back to
# tab 1 and a link could not point at a tab. The converted strip does, because
# this wiki sets $wgTabberNeueUpdateLocationOnTabChange. That is a behaviour
# CHANGE, so it is pinned here rather than discovered later.


def test_clicking_a_tab_updates_the_url(converted):
    converted.locator(TAB).nth(2).click()
    converted.wait_for_timeout(400)
    fragment = unquote(converted.evaluate("() => location.hash"))
    assert fragment.startswith("#tabber-tabpanel-"), fragment
    assert "&" not in fragment and "<" not in fragment, (
        f"the fragment is not readable: {fragment}")


def test_a_refresh_comes_back_to_the_same_tab(converted):
    converted.locator(TAB).nth(2).click()
    converted.wait_for_timeout(400)
    before = selected_index(converted)

    converted.reload(wait_until="networkidle")
    converted.wait_for_timeout(600)
    assert selected_index(converted) == before, (
        "a refresh did not return to the tab the URL names")


def test_clicking_a_tab_does_not_scroll_the_page(converted):
    """A tab is an `<a href="#tabber-tabpanel-…">`, and MediaWiki:Common.js
    animates the page to the target of ANY `a[href^="#"]` - so every tab click
    slid the strip itself off screen, 52px on a phone-width day page and more
    on a long one. The radio strip used labels and never did.

    Two things keep this from passing vacuously: the page is made taller than
    the viewport first (the host page is short enough that nothing CAN
    scroll), and the tab is clicked through JavaScript, because Playwright's
    own click scrolls the element into view and would hide the jump."""
    # Filler ABOVE the strip and below it, so the strip can sit mid-screen
    # with room to be scrolled either way. Below alone left it at the top,
    # where "200px above the strip" clamps to 0.
    converted.evaluate("""() => {
        const content = document.querySelector('.mw-parser-output');
        for (const where of ['afterbegin', 'beforeend']) {
            content.insertAdjacentHTML(where, '<div style="height:1500px"></div>');
        }
    }""")
    converted.locator(".tabber").first.evaluate(
        "node => window.scrollTo(0, node.getBoundingClientRect().top"
        " + scrollY - 200)")
    converted.wait_for_timeout(300)
    start = converted.evaluate("() => scrollY")
    assert start > 0, "the page did not scroll at all - the test is vacuous"

    converted.locator(TAB).nth(2).evaluate("node => node.click()")
    # The jump animated over 950ms; wait it out.
    converted.wait_for_timeout(1300)
    assert converted.evaluate("() => scrollY") == start, (
        "clicking a tab scrolled the page - is a jump-to-anchor handler "
        "catching tabber tabs again?")


def test_clicking_tabs_does_not_fill_the_back_button(converted):
    """The back button must leave the page, not walk back through tabs."""
    start = converted.evaluate("() => history.length")
    for index in (1, 2, 3):
        converted.locator(TAB).nth(index).click()
        converted.wait_for_timeout(300)
    assert converted.evaluate("() => history.length") == start, (
        "tab clicks pushed history entries")


def test_two_strips_on_one_page_do_not_share_anchors(browser):
    """Tab names repeat across the statistics strips - ליגה, גביע and
    בינלאומי are in almost all of them - and a page often carries several. If
    two panels shared an id, a fragment would address the wrong strip."""
    page = browser.new_page(viewport={"width": 1100, "height": 1600})
    page.goto(url_of(TWO_STRIPS), wait_until="networkidle")
    page.wait_for_timeout(600)

    strips = page.locator(".tabber")
    if strips.count() < 2:
        page.close()
        pytest.skip(f"{TWO_STRIPS} does not hold two converted strips")

    ids = page.locator(".tabber__panel").evaluate_all(
        "panels => panels.map(panel => panel.id)")
    page.close()
    assert len(ids) == len(set(ids)), f"duplicate panel ids: {ids}"
