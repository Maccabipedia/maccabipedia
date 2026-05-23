"""Static guard that the Maccabipedia skin keeps VisualEditor's required DOM hooks.

VisualEditor's preinit (ve.init.mw.DesktopArticleTarget.init.js) refuses to load
and logs "Your skin is incompatible with VisualEditor" unless the page provides
all three of: a target container (#content or [data-mw-ve-target-container]), the
editable-area wrapper (#mw-content-text), and an edit entry point (#ca-edit). This
skin emits all three from templates/skin.mustache. If a future template edit drops
one, VE silently breaks for every editor once Maccabipedia becomes the default
skin — so guard the template source statically (reads from disk, no live wiki).
"""
from __future__ import annotations

from pathlib import Path

SKIN_DIR = Path(__file__).resolve().parents[3] / "skins" / "Maccabipedia"
TEMPLATE = SKIN_DIR / "templates" / "skin.mustache"


def test_ve_required_hooks_present() -> None:
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'id="content"' in html or "data-mw-ve-target-container" in html, (
        "VE target container missing (#content or [data-mw-ve-target-container])"
    )
    assert 'id="mw-content-text"' in html, "VE editable-area wrapper #mw-content-text missing"
    assert 'id="ca-edit"' in html, "VE edit entry-point #ca-edit missing"
