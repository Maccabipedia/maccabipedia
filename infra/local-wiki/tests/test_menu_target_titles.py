"""The menu-targets seed list is parsed at runtime from the skin source —
this test runs the extraction against the real in-repo skin file, so a menu
refactor that breaks the parsing fails CI instead of silently seeding nothing.
"""
from download_pages_from_prod import menu_target_titles


def test_menu_targets_parsed_from_real_skin():
    titles = menu_target_titles()
    assert "עונות" in titles
    assert "סטטיסטיקות" in titles
    assert "מכבימדיה" in titles            # the standalone pageUrl() link
    assert len(titles) >= 15
    assert len(titles) == len(set(titles))
