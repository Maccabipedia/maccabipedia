"""Guard: every extension loaded by LocalSettings.shared.php must be either
bundled in MediaWiki 1.39 core or pinned in extensions.lock — otherwise the
local Docker wiki fatals at boot (the extension dir won't exist in the image).

Pure static test: reads two files, hits no network and no docker.
"""
from __future__ import annotations

import re
from pathlib import Path

_LOCAL_WIKI = Path(__file__).resolve().parents[1]
_SHARED = _LOCAL_WIKI / "config" / "LocalSettings.shared.php"
_LOCK = _LOCAL_WIKI / "extensions.lock"

# Bundled with the MediaWiki 1.39 core tarball (from mediawiki@REL1_39/.gitmodules).
# These ship in the image already, so they need no entry in extensions.lock.
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
    names: set[str] = set()
    for raw_line in _SHARED.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        # Skip fully commented-out lines (PHP // and #), so disabled
        # wfLoadExtension calls don't count as required.
        if line.startswith("//") or line.startswith("#"):
            continue
        names.update(_WF_LOAD_RE.findall(line))
        names.update(_REQUIRE_RE.findall(line))
    return names


def _locked_extensions() -> set[str]:
    names: set[str] = set()
    for raw_line in _LOCK.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        names.add(line.split("\t", 1)[0])
    return names


def test_every_loaded_extension_is_bundled_or_pinned() -> None:
    missing = _loaded_extensions() - _BUNDLED_1_39 - _locked_extensions()
    assert not missing, (
        "extensions loaded in LocalSettings.shared.php but neither bundled in "
        f"1.39 nor pinned in extensions.lock: {sorted(missing)}"
    )
