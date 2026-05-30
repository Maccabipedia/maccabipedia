"""Static guard against CSSJanus rewriting image url()s to missing files.

MediaWiki auto-generates an RTL stylesheet from the (LTR-authored) source via
CSSJanus, which *swaps `ltr`<->`rtl` tokens inside `url(...)` paths*. So a
rule written `url(images/search-rtl.svg)` makes the RTL page request
`search-ltr.svg` — a different file that may not exist (a silent 404 the
author never sees on an LTR dev setup). This bit the skin twice: the
main-page search icon and the external-link icon.

This guard scans the skin's LESS for image refs and asserts the files exist
(and that their CSSJanus-flipped ltr/rtl counterpart exists too). It covers
two ref styles:
  * repo-local `url(images/…)` — relative to the skin dir; and
  * vendored assets `url(/skins/Maccabipedia/assets/…)` — these now live in the
    repo (vendored in PR #142). They used to be FTP-synced from prod and absent
    from a checkout, so this dir was skipped; that's no longer true.

Not marked `integration`: reads files from disk, needs no live wiki.
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


# Absolute refs into the skin's own vendored assets, e.g.
# `url("/skins/Maccabipedia/assets/images/players/list-banner.png")`. The
# captured group is the path relative to the skin dir (`assets/...`).
ASSET_IMAGE_URL_RE = re.compile(
    rf"""url\(\s*['"]?/skins/{re.escape(SKIN_DIR.name)}/(assets/[^)'"\s]+)['"]?\s*\)"""
)

# Refs the LESS points at but whose file doesn't exist yet. Each entry MUST cite
# a tracking ticket and be removed once fixed — never add a silent exception.
KNOWN_MISSING_ASSET_REFS = {
    # Generic shirt-list page banner — never existed (silent 404 on prod too).
    # Tracking: Trello #576 (https://trello.com/c/GlKFMSwO). Remove this entry
    # once the ref is fixed (point at an existing banner or vendor the file).
    "assets/images/shirts/list-banner.png",
}


def test_skin_asset_image_refs_exist() -> None:
    """Every `/skins/<Skin>/assets/...` image the LESS references must exist.

    Assets are vendored in the repo since PR #142, so a missing one is a silent
    404 we can catch statically (the same class of bug the local-image guard
    above catches for `images/` refs).
    """
    problems = []
    for less_file in SKIN_DIR.rglob("*.less"):
        for match in ASSET_IMAGE_URL_RE.finditer(less_file.read_text(encoding="utf-8")):
            ref = match.group(1)  # e.g. assets/images/shirts/list-banner.png
            if ref in KNOWN_MISSING_ASSET_REFS:
                continue
            where = f"{less_file.relative_to(SKIN_DIR)}: url(/skins/{SKIN_DIR.name}/{ref})"

            if not (SKIN_DIR / ref).exists():
                problems.append(f"{where} -> referenced asset is missing")

            flipped = _cssjanus_flip(ref)
            if flipped != ref and not (SKIN_DIR / flipped).exists():
                problems.append(
                    f"{where} -> CSSJanus requests '{flipped}' on the opposite "
                    "text direction, but that asset is missing (silent 404)"
                )

    assert not problems, "Missing skin asset refs:\n" + "\n".join(problems)


def _referenced_asset_refs() -> set[str]:
    """Every `assets/...` ref the skin's LESS currently points at."""
    refs: set[str] = set()
    for less_file in SKIN_DIR.rglob("*.less"):
        text = less_file.read_text(encoding="utf-8")
        refs.update(m.group(1) for m in ASSET_IMAGE_URL_RE.finditer(text))
    return refs


def test_known_missing_asset_refs_stay_honest() -> None:
    """Stop KNOWN_MISSING_ASSET_REFS from rotting. An entry is only legitimate
    while it's BOTH still referenced by some LESS AND still absent on disk.
    Once the ref is fixed — whether by adding the file OR by re-pointing the
    LESS at an existing asset — the entry is obsolete and must be deleted so
    the guard above enforces it for real."""
    referenced = _referenced_asset_refs()
    obsolete = []
    for ref in sorted(KNOWN_MISSING_ASSET_REFS):
        if (SKIN_DIR / ref).exists():
            obsolete.append(f"{ref} (file now exists)")
        elif ref not in referenced:
            obsolete.append(f"{ref} (no longer referenced by any LESS)")
    assert not obsolete, (
        "Obsolete KNOWN_MISSING_ASSET_REFS entries — delete them so the guard "
        "enforces them:\n  " + "\n  ".join(obsolete)
    )
