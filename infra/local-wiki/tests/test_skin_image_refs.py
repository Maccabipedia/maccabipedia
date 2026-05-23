"""Static guard against CSSJanus rewriting image url()s to missing files.

MediaWiki auto-generates an RTL stylesheet from the (LTR-authored) source via
CSSJanus, which *swaps `ltr`<->`rtl` tokens inside `url(...)` paths*. So a
rule written `url(images/search-rtl.svg)` makes the RTL page request
`search-ltr.svg` — a different file that may not exist (a silent 404 the
author never sees on an LTR dev setup). This bit the skin twice: the
main-page search icon and the external-link icon.

This guard scans the skin's LESS for *repo-local* image refs (`url(images/…)`)
and asserts that both the referenced file and its CSSJanus-flipped counterpart
exist. The `assets/` dir is intentionally skipped — it's gitignored and
FTP-synced from prod, so those files aren't present in a checkout. Not marked
`integration`: reads files from disk, needs no live wiki.
"""
from __future__ import annotations

import re
from pathlib import Path

SKIN_DIR = Path(__file__).resolve().parents[3] / "skins" / "Maccabipedia"

# Repo-local refs only: `url(images/x.svg)`, optionally quoted/spaced. Absolute
# `url("/skins/Maccabipedia/assets/…")` refs don't start with `images/`, so the
# anchored group skips them.
LOCAL_IMAGE_URL_RE = re.compile(r"""url\(\s*['"]?(images/[^)'"\s]+)['"]?\s*\)""")


def _cssjanus_flip(path: str) -> str:
    """Swap ltr<->rtl tokens the way CSSJanus does for the opposite direction."""
    return path.replace("ltr", "\0").replace("rtl", "ltr").replace("\0", "rtl")


def test_local_image_refs_are_cssjanus_safe() -> None:
    problems = []
    for less_file in SKIN_DIR.rglob("*.less"):
        for match in LOCAL_IMAGE_URL_RE.finditer(less_file.read_text(encoding="utf-8")):
            ref = match.group(1)
            where = f"{less_file.relative_to(SKIN_DIR)}: url({ref})"

            if not (SKIN_DIR / ref).exists():
                problems.append(f"{where} -> referenced file is missing")

            flipped = _cssjanus_flip(ref)
            if flipped != ref and not (SKIN_DIR / flipped).exists():
                problems.append(
                    f"{where} -> CSSJanus requests '{flipped}' on the opposite "
                    "text direction, but that file is missing (silent 404)"
                )

    assert not problems, "CSSJanus-unsafe image refs:\n" + "\n".join(problems)
