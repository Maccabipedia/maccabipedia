"""Browser tests for the game-search URL trim (scripts/game-search-url.js).

The script drops empty fields from the PageForms query string before submission,
so the search URL stops overflowing the 1,000 characters GA4 stores for
page_location.

These must be driven in a real browser rather than asserted as strings. Two
runtime facts decide whether the script works at all, and neither is visible in
the source:

  * PageForms' `ext.pageforms.submit` binds a handler on the same form that
    throws on every submit outside Special:FormEdit. jQuery routes all its
    handlers through one native listener with no try/catch, so that exception
    kills the whole jQuery queue. An earlier version bound via jQuery and was a
    verified no-op while every static assertion about it passed.
  * On a RESULTS page PFRunQuery.php replays the previous query as hidden
    inputs, including one bracketless blob holding the entire prior query
    string. A bare form shows none of this, so tests that only load the empty
    page cannot see the case the script exists for.

Requires the local wiki with the game-search pages seeded::

    cd infra/local-wiki
    uv run python scripts/download_pages_from_prod.py pages \\
        scripts/content-manifests/game-search.manifest
    bash scripts/seed-content.sh game-search

Run with::

    uv run --with playwright pytest -m integration \\
        infra/local-wiki/tests/test_game_search_instrumentation.py
"""
from __future__ import annotations

import urllib.parse

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

pytestmark = pytest.mark.integration

LOCAL = "http://localhost:8080"
FOOTBALL = "חיפוש משחק כדורגל"
SEARCH_URL = LOCAL + "/index.php?title=" + urllib.parse.quote("חיפוש משחק")

# A results page: PFRunQuery only replays prior parameters once it considers the
# form submitted, which the pfRunQueryFormName marker is what triggers.
RESULTS_URL = SEARCH_URL + "&" + urllib.parse.urlencode(
    [
        ("pfRunQueryFormName", FOOTBALL),
        ("QueryGamesTemplate[Season]", "2013/14"),
        ("QueryGamesTemplate[EndDate]", ""),
        ("QueryGamesTemplate[Opponent]", ""),
    ]
)

# Submits without navigating, returning the query string the browser would have
# sent. Our handler is a native listener and has already run by the time this
# bubble-phase preventDefault fires.
CAPTURE_SUBMIT = """
    () => {
        const form = document.querySelector('form.createbox[method="get"]')
        const serialized = () => new URLSearchParams(new FormData(form)).toString()
        const before = serialized()
        let after = null
        form.addEventListener('submit', e => {
            e.preventDefault()
            after = serialized()
        }, false)
        form.requestSubmit(form.querySelector('button[name="wpRunQuery"]'))
        const counts = new Map()
        form.querySelectorAll('input, select, textarea').forEach(el => {
            if (el.name) { counts.set(el.name, (counts.get(el.name) || 0) + 1) }
        })
        const duplicated = Array.from(counts.entries())
            .filter(([, n]) => n > 1).map(([name]) => name)
        return { before, after, duplicated }
    }
"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        instance = p.chromium.launch()
        yield instance
        instance.close()


def _submit(browser, url):
    context = browser.new_context(locale="he-IL")
    page = context.new_page()
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(500)
    measured = page.evaluate(CAPTURE_SUBMIT)
    context.close()
    return measured


def _pairs(query):
    return urllib.parse.parse_qsl(query, keep_blank_values=True)


def test_empty_fields_are_dropped_from_the_submitted_query_string(browser):
    measured = _submit(browser, SEARCH_URL)

    assert [k for k, v in _pairs(measured["before"]) if not v.strip()], (
        "fixture is stale: the form no longer submits empty fields, so this test "
        "can no longer detect whether they are stripped"
    )
    # Duplicate-named controls are deliberately exempt: disabling an empty one
    # would promote its twin and change the reader's results.
    survivors = {k for k, v in _pairs(measured["after"]) if not v.strip()}
    assert survivors <= set(measured["duplicated"]), (
        f"empty fields survived submission that are not duplicates: "
        f"{survivors - set(measured['duplicated'])}"
    )
    assert len(measured["after"]) < len(measured["before"])


def test_checkbox_markers_survive_the_strip(browser):
    """PageForms pairs each checkbox with an [is_checkbox] marker it needs sent."""
    measured = _submit(browser, SEARCH_URL)

    assert "is_checkbox" in urllib.parse.unquote(measured["after"])


def test_the_replayed_previous_query_is_dropped_on_a_results_page(browser):
    """PFRunQuery re-emits the whole prior query as one bracketless hidden input.

    It is non-empty, so the empty-field rule never touches it, and the browser
    re-encodes it — a second search would otherwise carry a doubly-escaped copy
    of the first.
    """
    measured = _submit(browser, RESULTS_URL)
    names_before = [k for k, _ in _pairs(measured["before"])]

    assert "QueryGamesTemplate" in names_before, (
        "fixture is stale: the results page no longer replays the prior query as "
        "a bracketless blob, so this test proves nothing"
    )
    assert "QueryGamesTemplate" not in [k for k, _ in _pairs(measured["after"])]


def test_a_results_page_search_still_shrinks(browser):
    measured = _submit(browser, RESULTS_URL)

    assert len(measured["after"]) < len(measured["before"])


def test_the_readers_filter_survives_on_a_results_page(browser):
    """Refining a search must not lose the filter that is already applied."""
    measured = _submit(browser, RESULTS_URL)

    assert ("QueryGamesTemplate[Season]", "2013/14") in _pairs(measured["after"])


def test_duplicate_named_fields_are_left_alone(browser):
    """The form renders some fields twice, and PHP keeps the LAST occurrence.

    Disabling an empty duplicate promotes the other one, which would change the
    reader's results — so repeated names must survive the strip untouched.
    """
    context = browser.new_context(locale="he-IL")
    page = context.new_page()
    page.goto(SEARCH_URL, wait_until="networkidle")
    page.wait_for_timeout(500)

    report = page.evaluate(
        """() => {
            const form = document.querySelector('form.createbox[method="get"]')
            const counts = new Map()
            const controls = Array.from(form.querySelectorAll('input, select, textarea'))
            controls.forEach(el => {
                if (el.name) { counts.set(el.name, (counts.get(el.name) || 0) + 1) }
            })
            const duplicated = Array.from(counts.entries())
                .filter(([, n]) => n > 1)
                .map(([name]) => name)
            form.addEventListener('submit', e => e.preventDefault(), false)
            form.requestSubmit(form.querySelector('button[name="wpRunQuery"]'))
            const disabledDuplicates = controls
                .filter(el => el.name && duplicated.includes(el.name) && el.disabled)
                .map(el => el.name)
            return { duplicated, disabledDuplicates }
        }"""
    )
    context.close()

    assert report["duplicated"], (
        "fixture is stale: the form no longer renders any field twice, so this "
        "test can no longer detect the promotion hazard"
    )
    assert not report["disabledDuplicates"], (
        f"duplicate-named controls were disabled: {report['disabledDuplicates']} — "
        "this silently changes which value PHP keeps"
    )
