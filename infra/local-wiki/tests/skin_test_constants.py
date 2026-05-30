"""Shared constants for the local-wiki skin integration tests.

`conftest.py` files exist under several test-path roots in this monorepo
(packages/maccabistats/tests/, packages/maccabipediabot/tests/, etc.), so
`from conftest import …` is ambiguous — Python's import machinery picks
the first `conftest` module on sys.path, not necessarily this one. Use
this dedicated, uniquely-named module for cross-test sharing instead.

Reachable thanks to `pythonpath = ["infra/local-wiki/tests"]` in
`pyproject.toml`'s `[tool.pytest.ini_options]`.
"""
from __future__ import annotations

import re


# Mirror of the menu definitions in `SkinMaccabipedia::buildPrimaryDropdowns()`.
# Adding, removing, or renaming a menu link must be a coordinated change in
# both PHP and this list — the duplication between PHP and tests is the point.
MENU_LABELS = (
    # מכבי תל אביב dropdown
    "ההיסטוריה", "עונות", "מתקנים", "מפעלים", "מדים", "תארים",
    # שחקנים וצוות dropdown
    "שחקנים", "אנשי צוות",
    # אוהדים ותרבות dropdown
    "שירים", "כרטיסים ומנויים", "כרזות", "קלפים ומדבקות",
    "תפאורות", "ארגונים", "ספרים", "פנזינים",
    # משחקים dropdown
    "חיפוש משחק", "סטטיסטיקות",
    # standalone link
    "מכבימדיה",
    # footer about-section links
    "תרומות", "יצירת קשר",
)


# Anchor on PHP's display_errors markup (`<b>type</b>: …`) so we don't
# false-positive on wiki content that happens to contain the words "Notice:"
# / "Warning:" / etc. in prose.
PHP_ERROR_RE = re.compile(r"<b>(?:Fatal error|Warning|Notice|Deprecated)</b>:")
