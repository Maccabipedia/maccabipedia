"""Byte-fidelity guard for the vendored slick library.

The Maccabipedia skin ships slick as a byte-identical copy of the production
files (see `skins/Maccabipedia/resources/slick/README.md`), pinned by sha256
because the minified JS carries no version banner. That pinning is only a
contract if something enforces it: this test recomputes the hash of every file
listed in the README's provenance table and fails on any drift — a hand-edit,
a partial re-fetch, a deleted asset, or an end-of-line renormalization that
silently diverges the vendored copy from prod.

It also covers the gif + webfont assets that `slick-theme.less` pulls in via
`url()` (and that the skin.json module list does not name), so deleting
`fonts/` or `ajax-loader.gif` is caught here. Not marked `integration`: reads
files from disk, needs no live wiki.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SLICK_DIR = REPO_ROOT / "skins" / "Maccabipedia" / "resources" / "slick"
README = SLICK_DIR / "README.md"

# Matches a provenance-table row: | `relative/path` | `<64 hex>` |
TABLE_ROW = re.compile(r"^\s*\|\s*`([^`]+)`\s*\|\s*`([0-9a-f]{64})`\s*\|\s*$")


def _pinned_checksums() -> dict[str, str]:
    pins = {}
    for line in README.read_text(encoding="utf-8").splitlines():
        match = TABLE_ROW.match(line)
        if match:
            relative_path, expected_sha = match.groups()
            pins[relative_path] = expected_sha
    return pins


def test_vendored_slick_files_match_pinned_checksums() -> None:
    pins = _pinned_checksums()

    assert pins, (
        f"no `file` | `sha256` rows parsed from {README} — did the provenance "
        "table move or change format? update this guard accordingly."
    )

    mismatches = []
    for relative_path, expected_sha in pins.items():
        vendored_file = SLICK_DIR / relative_path
        if not vendored_file.is_file():
            mismatches.append((relative_path, "MISSING", expected_sha))
            continue
        actual_sha = hashlib.sha256(vendored_file.read_bytes()).hexdigest()
        if actual_sha != expected_sha:
            mismatches.append((relative_path, actual_sha, expected_sha))

    assert not mismatches, (
        "vendored slick file(s) diverged from the sha256 pinned in "
        f"{README} (actual vs expected): {mismatches}. The vendored copy must "
        "stay byte-identical to prod; re-fetch from the source URL and update "
        "the README, or restore the file. (.gitattributes marks this dir -text "
        "to stop end-of-line renormalization from corrupting the bytes.)"
    )
