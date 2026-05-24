"""Static guard: every skin LESS file has balanced ``/* */`` block comments.

A dropped ``*`` turns a comment close ``*/`` into a bare ``/``, leaving the
comment open until the *next* ``*/`` — which silently swallows every rule in
between. This bit the Metrolook skin when an automated edit changed
``/* --- Top 10 Players Tables --- */`` to ``... --- /``: prod's ``less.php``
dropped the whole file, taking the ``.slim-tabs`` tab-switching engine with it
(tabs rendered but stopped switching), while node ``less.js`` in CI/dev tolerated
it and never flagged the breakage.

A plain "is every ``/*`` eventually closed" scan does NOT catch this — the next
comment's ``*/`` closes the runaway — so we assert the raw per-file counts of
``/*`` and ``*/`` are equal. Reads files from disk; needs no live wiki.
"""
from __future__ import annotations

from pathlib import Path

SKINS_DIR = Path(__file__).resolve().parents[3] / "skins"


def test_skin_less_block_comments_are_balanced() -> None:
    problems = []
    for less_file in sorted(SKINS_DIR.rglob("*.less")):
        text = less_file.read_text(encoding="utf-8", errors="replace")
        opens = text.count("/*")
        closes = text.count("*/")
        if opens != closes:
            problems.append(
                f"{less_file.relative_to(SKINS_DIR)}: {opens} '/*' vs {closes} '*/' "
                "— unbalanced block comment (likely a '*/' that lost its '*')"
            )

    assert not problems, (
        "Unbalanced LESS block comments — prod less.php silently drops every rule "
        "after a runaway comment:\n" + "\n".join(problems)
    )
