"""Static regression guard for the Maccabipedia skin's ResourceLoader graph.

The slider scripts (`scripts/sliders.js`) call `$.fn.slick()`, but the slick
library is shipped by a *separate* module — `maccabipedia.customizations`,
defined in `LocalSettings.shared.php` and injected on every page. If the JS
module that ships the slider code does not declare a dependency on that
module, ResourceLoader is free to execute the two in any order. The slider
init then races slick registration and intermittently throws
`slick is not a function`, leaving the main-page carousel flashing forever.

This bit prod once (the Maccabipedia skin's JS bundle is light enough to win
the race). The race is invisible locally — the local wiki doesn't even mount
the prod `customizations/` dir — so a static invariant is the only thing that
catches a regression before it ships. Not marked `integration`: reads JSON
from disk, needs no live wiki.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKIN_JSON = REPO_ROOT / "skins" / "Maccabipedia" / "skin.json"

# The module name slick is registered under (see LocalSettings.shared.php).
SLICK_PROVIDER = "maccabipedia.customizations"
# The call that proves a script needs slick. Keyed on the symbol, not a
# filename: slick is invoked from sliders.js *and* shirts-list.js, and new
# call sites can appear in any script.
SLICK_CALL = ".slick("


def test_modules_calling_slick_depend_on_provider() -> None:
    skin_dir = SKIN_JSON.parent
    modules = json.loads(SKIN_JSON.read_text(encoding="utf-8"))["ResourceModules"]

    checked_any = False
    offenders = []
    for name, module in modules.items():
        slick_scripts = [
            script
            for script in module.get("scripts", [])
            if SLICK_CALL in (skin_dir / script).read_text(encoding="utf-8")
        ]
        if not slick_scripts:
            continue
        checked_any = True
        if SLICK_PROVIDER not in module.get("dependencies", []):
            offenders.append((name, slick_scripts, module.get("dependencies", [])))

    assert checked_any, (
        f"no script in {SKIN_JSON}'s modules calls {SLICK_CALL!r} — did the slider "
        "code move or stop using slick? update this guard accordingly."
    )
    assert not offenders, (
        "module(s) ship scripts that call $.fn.slick() without depending on "
        f"'{SLICK_PROVIDER}' (which provides slick). Without the dependency, "
        "ResourceLoader load order is a race and slick() intermittently throws "
        f"'slick is not a function'. Offenders: {offenders}"
    )
