"""Guard: every extension loaded by LocalSettings.shared.php must be either
bundled in MediaWiki 1.39 core or pinned in extensions.json — otherwise the
local Docker wiki fatals at boot (the extension dir won't exist in the image).

Pure static test: reads two files, hits no network and no docker.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_LOCAL_WIKI = Path(__file__).resolve().parents[1]
_SHARED = _LOCAL_WIKI / "config" / "LocalSettings.shared.php"
_MANIFEST = _LOCAL_WIKI / "extensions.json"
_DOCKERFILE = _LOCAL_WIKI / "Dockerfile"

# Bundled with the MediaWiki 1.39 core tarball (from mediawiki@REL1_39/.gitmodules).
# These ship in the image already, so they need no entry in extensions.json.
# Tied to MW 1.39 — test_bundled_set_tracks_dockerfile_version fails loudly if
# the image's MW_VERSION moves off 1.39, prompting a re-derive from .gitmodules.
_BUNDLED_1_39 = {
    "AbuseFilter", "CategoryTree", "Cite", "CiteThisPage", "CodeEditor",
    "ConfirmEdit", "Gadgets", "ImageMap", "InputBox", "Interwiki", "Math",
    "MultimediaViewer", "Nuke", "OATHAuth", "PageImages", "ParserFunctions",
    "PdfHandler", "Poem", "Renameuser", "ReplaceText", "Scribunto",
    "SecureLinkFixer", "SpamBlacklist", "SyntaxHighlight_GeSHi", "TemplateData",
    "TextExtracts", "TitleBlacklist", "VisualEditor", "WikiEditor",
}

_WF_LOAD_RE = re.compile(r"wfLoadExtension\(\s*'([^']+)'")
_REQUIRE_RE = re.compile(r'require_once\s+"\$IP/extensions/([^/"]+)/')


def _loaded_extensions() -> set[str]:
    """Extension names loaded by shared.php. Recognizes the two forms shared.php
    actually uses: ``wfLoadExtension('Name')`` and
    ``require_once "$IP/extensions/Name/...";``. Lines fully commented out (PHP
    // or #) are ignored. Other load styles (e.g. wfLoadExtensions([...])) are
    not used here and intentionally not parsed.
    """
    names: set[str] = set()
    for raw_line in _SHARED.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("//") or line.startswith("#"):
            continue
        names.update(_WF_LOAD_RE.findall(line))
        names.update(_REQUIRE_RE.findall(line))
    return names


def _pinned_extensions() -> set[str]:
    data = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    return {ext["name"] for ext in data["extensions"]}


def test_every_loaded_extension_is_bundled_or_pinned() -> None:
    missing = _loaded_extensions() - _BUNDLED_1_39 - _pinned_extensions()
    assert not missing, (
        "extensions loaded in LocalSettings.shared.php but neither bundled in "
        f"1.39 nor pinned in extensions.json: {sorted(missing)}"
    )


def test_bundled_set_tracks_dockerfile_version() -> None:
    """_BUNDLED_1_39 is a snapshot of MW 1.39's bundled extensions. If the image
    is bumped to another MW release, that set must be re-derived from the new
    release's .gitmodules — fail loudly here rather than let the guard go stale.
    """
    match = re.search(r"MW_VERSION=(\d+\.\d+)", _DOCKERFILE.read_text(encoding="utf-8"))
    found = match.group(1) if match else None
    assert found == "1.39", (
        f"Dockerfile MW_VERSION is {found!r}, but _BUNDLED_1_39 was captured for "
        "1.39 — re-derive the bundled set from that release's .gitmodules and update both."
    )
