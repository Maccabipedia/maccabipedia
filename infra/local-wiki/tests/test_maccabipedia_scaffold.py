"""End-to-end smoke tests for the Maccabipedia skin, the default skin.

Asserts the skin renders the main page without PHP errors, emits the
expected body class, mobile viewport, no firstHeading h1, search input
text-field class, every menu link in MENU_LABELS, no prod-URL leakage,
loadable logo + powered-by assets, and Title-encoded menu hrefs.

`MENU_LABELS` and `PHP_ERROR_RE` come from `skin_test_constants.py`.
"""
from __future__ import annotations

import re

import pytest
import requests

from skin_test_constants import MENU_LABELS, PHP_ERROR_RE

pytestmark = pytest.mark.integration


def test_no_php_errors(maccabipedia_anon_html: str) -> None:
    matches = PHP_ERROR_RE.findall(maccabipedia_anon_html)
    assert not matches, f"PHP errors leaked into body: {matches[:5]}"


def test_exactly_one_body_tag(maccabipedia_anon_html: str) -> None:
    body_tag_count = len(re.findall(r"<body\b", maccabipedia_anon_html))
    assert body_tag_count == 1, f"expected exactly 1 <body>, found {body_tag_count}"


def test_body_has_skin_maccabipedia_class(maccabipedia_anon_html: str) -> None:
    body_open_match = re.search(r"<body[^>]*>", maccabipedia_anon_html)
    assert body_open_match, "no <body> tag in response"
    assert "skin-maccabipedia" in body_open_match.group(0), (
        f"skin-maccabipedia not in body classes: {body_open_match.group(0)}"
    )


def test_mobile_viewport_meta_present(maccabipedia_anon_html: str) -> None:
    """Without this, iPhones render the page at 1000px-wide desktop layout."""
    assert re.search(
        r'<meta[^>]*name="viewport"[^>]*content="[^"]*width=device-width',
        maccabipedia_anon_html,
    ), "mobile viewport meta tag missing — mobile UX would render at desktop width"


def test_title_not_wrapped_in_firstheading(maccabipedia_anon_html: str) -> None:
    """SkinMustache's default `html-title-heading` wraps the title in
    <h1 class="firstHeading">, but our `.firstHeading` rule has font-size:140%
    which scales the .mw-page-title-main span ~40% bigger inside the yellow
    .maccabipedia-page-title bar. SkinMaccabipedia overrides html-title-heading
    to use OutputPage::getPageTitle() instead. Assert nothing leaked."""
    assert "firstHeading" not in maccabipedia_anon_html, (
        "found .firstHeading in rendered HTML — would scale the title to ~25px "
        "instead of 17.6px. See SkinMaccabipedia::getTemplateData()."
    )


def test_special_page_keeps_user_and_options_dropdowns(
    maccabipedia_special_recentchanges_html: str,
) -> None:
    """On Special: pages the edit dropdown is correctly hidden (no editable
    wikitext / talk page / history), but the user dropdown and the global
    options dropdown must still render — otherwise a logged-in reader
    can't reach Preferences/Logout from Special:Recentchanges."""
    html = maccabipedia_special_recentchanges_html
    assert 'fa-user option-icon' in html, "user dropdown missing on Special page"
    assert 'fa-cogs option-icon' in html, "options dropdown missing on Special page"
    assert 'fa-pencil-alt option-icon' not in html, (
        "edit dropdown unexpectedly rendered on Special:Recentchanges"
    )


# ---------------------------------------------------------------------------
# Per-state menu coverage — every branch in SkinMaccabipedia::buildOptionsPanel
# and ::buildUserPanel.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label, present",
    [
        ("כניסה לחשבון", True),    # login link
        ("יצירת חשבון", True),     # create-account link
        (">התנתק</a>", False),     # logout must NOT appear
        (">העדפות</a>", False),    # preferences must NOT appear (anon)
    ],
)
def test_anon_user_panel_on_maccabipedia(
    maccabipedia_anon_html: str, label: str, present: bool
) -> None:
    if present:
        assert label in maccabipedia_anon_html
    else:
        assert label not in maccabipedia_anon_html


@pytest.mark.parametrize(
    "label, present",
    [
        # Logged-in user panel
        (">התנתק</a>", True),
        (">העדפות</a>", True),
        (">התרומות שלי</a>", True),
        (">עמוד השיחה שלי</a>", True),
        (">כניסה לחשבון</a>", False),
        (">יצירת חשבון</a>", False),
        # Edit dropdown for any registered user with 'edit' permission
        (">עריכה</a>", True),
        # Admin-only items gated on $user->isAllowed('protect')
        (">מחיקה</a>", True),
        (">העברה</a>", True),
        (">הגנה</a>", True),
    ],
)
def test_admin_user_panel_on_maccabipedia(
    maccabipedia_admin_html: str, label: str, present: bool
) -> None:
    if present:
        assert label in maccabipedia_admin_html
    else:
        assert label not in maccabipedia_admin_html


@pytest.mark.parametrize(
    "label, present",
    [
        # Logged-in panel — should look like a registered user
        (">התנתק</a>", True),
        (">העדפות</a>", True),
        (">התרומות שלי</a>", True),
        (">כניסה לחשבון</a>", False),
        (">יצירת חשבון</a>", False),
        # Edit shown for any registered user
        (">עריכה</a>", True),
        # Admin-only items must NOT appear for a regular user — this is
        # the privilege-leak guard the admin-only test couldn't check.
        (">מחיקה</a>", False),
        (">העברה</a>", False),
        (">הגנה</a>", False),
    ],
)
def test_regular_user_panel_on_maccabipedia(
    maccabipedia_regular_user_html: str, label: str, present: bool
) -> None:
    if present:
        assert label in maccabipedia_regular_user_html, (
            f"expected {label!r} in regular user's view"
        )
    else:
        assert label not in maccabipedia_regular_user_html, (
            f"{label!r} leaked into regular user's view (admin-only or anon-only)"
        )


def test_edit_mode_shows_back_to_article_link(maccabipedia_edit_mode_html: str) -> None:
    """When ?action=edit is on the URL the edit dropdown should show
    "חזור לערך" (back to article view) instead of "עריכה" (open editor) —
    matches Metrolook's behavior."""
    assert ">חזור לערך</a>" in maccabipedia_edit_mode_html, (
        "in action=edit mode, expected back-to-article link in the edit dropdown"
    )


def test_talk_page_emits_subject_back_link(maccabipedia_talk_page_html: str) -> None:
    """On a talk-namespace page the edit dropdown must include a "חזור לערך"
    link pointing back to the subject article. The parent's `talk-page-url`
    is null on talk pages, so the dropdown's subject-back branch fires
    instead — see SkinMaccabipedia::buildOptionsPanel()."""
    assert ">חזור לערך</a>" in maccabipedia_talk_page_html
    # The href should point to the subject article (no Talk: prefix).
    assert re.search(
        r'<a href="/[^"]*%D7%A2%D7%9E%D7%95%D7%93[^"]*">חזור לערך</a>',
        maccabipedia_talk_page_html,
    ), "subject-back link not pointing at the parent article"


def test_oldid_preserved_in_action_urls_on_maccabipedia(
    maccabipedia_oldid_html: tuple[str, str],
) -> None:
    """Viewing ?oldid=N on Maccabipedia must keep that exact oldid in
    edit/history action hrefs, so editing/historying while viewing an old
    revision keeps targeting that revision."""
    html, oldid = maccabipedia_oldid_html
    edit_re = re.compile(
        rf'href="[^"]*action=edit[^"]*oldid={oldid}'
        rf'|href="[^"]*oldid={oldid}[^"]*action=edit'
    )
    history_re = re.compile(
        rf'href="[^"]*action=history[^"]*oldid={oldid}'
        rf'|href="[^"]*oldid={oldid}[^"]*action=history'
    )
    assert edit_re.search(html), f"oldid {oldid} dropped from edit href"
    assert history_re.search(html), f"oldid {oldid} dropped from history href"


def test_search_input_has_text_field_class(maccabipedia_anon_html: str) -> None:
    """Five LESS rules in `app-header.less` (white text, padding, transition,
    ::placeholder, focus opacity) target `.search-content .text-field`."""
    assert re.search(
        r'<input[^>]*id="searchInput"[^>]*class="[^"]*\btext-field\b',
        maccabipedia_anon_html,
    ), "search input missing the text-field class hook"


@pytest.mark.parametrize("label", MENU_LABELS)
def test_menu_link_renders(maccabipedia_anon_html: str, label: str) -> None:
    """Maccabipedia must emit every menu link in MENU_LABELS — the mirror of
    SkinMaccabipedia::buildPrimaryDropdowns()."""
    assert f">{label}</a>" in maccabipedia_anon_html


def test_no_broken_dropdown_hrefs(maccabipedia_anon_html: str) -> None:
    """A dead link from pageUrl() degrades to href="#" — never intended."""
    broken = re.findall(r'<a href="#">', maccabipedia_anon_html)
    assert not broken, f"found {len(broken)} menu link(s) degraded to href=\"#\""


def test_no_prod_url_leakage(maccabipedia_anon_html: str) -> None:
    """No hrefs/text mentioning the production wiki should leak through the
    local stack."""
    assert "maccabipedia.co.il" not in maccabipedia_anon_html


@pytest.mark.parametrize("asset", ["logo", "powered-by"])
def test_static_asset_loads(maccabipedia_anon_html: str, asset: str) -> None:
    """The skin's own logo (assets/images/logo.png) and the powered-by-MediaWiki
    <img src> must be present and resolve to HTTP 200. Both are $wgServer-prefixed
    absolute URLs (see SkinMaccabipedia::buildAppHeaderData/buildAppFooterData).

    The logo is served from the synced banner assets (docker-compose mounts
    synced/skins/Metrolook/assets into the skin's assets/), so this test
    presupposes `sync-from-prod.sh maccabipedia-skin-assets` has run."""
    pattern = {
        "logo": r'src="([^"]*logo\.png[^"]*)"',
        "powered-by": r'src="([^"]*poweredby[^"]*)"',
    }[asset]
    match = re.search(pattern, maccabipedia_anon_html)
    assert match, f"<img src> for {asset} not found in main page"
    asset_url = match.group(1)
    response = requests.get(asset_url, timeout=15)
    assert response.status_code == 200, (
        f"{asset} URL {asset_url} -> HTTP {response.status_code}"
    )


def test_menu_links_title_encoded(maccabipedia_anon_html: str) -> None:
    """Menu hrefs come from Title->getLocalURL(), so they're fully URL-encoded:
    no literal spaces, and Hebrew titles land on /%D7… paths (with
    $wgArticlePath = "/$1" the local stack mirrors prod's pretty URLs)."""
    literal_space = re.findall(r'href="[^"]* [^"]*"', maccabipedia_anon_html)
    assert not literal_space, f"menu hrefs with literal spaces: {literal_space[:3]}"
    encoded = re.findall(r'href="/%D7', maccabipedia_anon_html)
    assert encoded, "expected at least one Title-encoded Hebrew menu link"
