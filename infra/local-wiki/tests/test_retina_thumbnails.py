"""Thumbnails get a 2x copy only, and no image form can break a page.

Runs against a running local wiki (MACCABIPEDIA_LOCAL_URL, default :8080) with the
ThumbnailBeforeProduceHTML hook from LocalSettings.shared.php; skips when the stack is down.
The hook's first version took prod down because an image without a link (|link=) hands it
$linkAttribs = false, so every link form is rendered here, not only the common ones.
"""
from __future__ import annotations

import re
import struct
import zlib

import pytest
import requests

from skin_test_constants import PHP_ERROR_RE

LANDSCAPE = "Retina test landscape.png"
PORTRAIT = "Retina test portrait.png"
TINY = "Retina test tiny.png"
GIF = "Retina test pixel.gif"

LINK_FORMS = ["", "|link=", "|link=עמוד ראשי", "|link=https://example.org", "|alt=תמונה"]
SHAPES = ["120px", "x90px", "100x100px", "thumb", "thumb|upright", "thumb|220px", "frame", "frameless",
          "border|150px", "3000px"]
GALLERIES = ["", "mode=packed", "mode=packed-hover", "mode=packed-overlay", "mode=nolines", "mode=slideshow",
             "widths=150px heights=150px"]


def _png(width: int, height: int) -> bytes:
    """A solid-colour RGB PNG, written with the standard library only."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    row = b"\x00" + b"\x20\x60\xc0" * width
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b"")


# A 1x1 GIF: smaller than every size asked for, so the "thumbnail" is the original itself.
_GIF = bytes.fromhex("47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b")


@pytest.fixture(scope="module")
def api(base_url: str, admin_session: requests.Session) -> str:
    """Upload the test images once (as admin) and return the api.php URL."""
    api_url = f"{base_url}/api.php"
    token = admin_session.get(api_url, params={"action": "query", "meta": "tokens", "format": "json"},
                              timeout=30).json()["query"]["tokens"]["csrftoken"]
    for name, content in ((LANDSCAPE, _png(1600, 1000)), (PORTRAIT, _png(1000, 1600)), (TINY, _png(40, 30)),
                          (GIF, _GIF)):
        reply = admin_session.post(api_url, data={"action": "upload", "filename": name, "ignorewarnings": 1,
                                                  "token": token, "format": "json"},
                                   files={"file": (name, content)}, timeout=60).json()
        assert "error" not in reply or reply["error"].get("code") == "fileexists-no-change", reply
    return api_url


def _parse(api_url: str, wikitext: str) -> str:
    reply = requests.post(api_url, data={"action": "parse", "format": "json", "text": wikitext,
                                         "contentmodel": "wikitext", "prop": "text"}, timeout=60).json()
    assert "error" not in reply, f"{wikitext!r} -> {reply['error']}"
    html = reply["parse"]["text"]["*"]
    assert not PHP_ERROR_RE.search(html), f"PHP error in the render of {wikitext!r}"
    return html


def _srcsets(html: str) -> list[str]:
    return [m.group(1) for tag in re.findall(r"<img [^>]+>", html) for m in [re.search(r'srcset="([^"]*)"', tag)] if m]


def _all_cases() -> list[str]:
    cases = [f"[[File:{name}|{shape}{link}]]" for name in (LANDSCAPE, PORTRAIT, TINY, GIF)
             for shape in SHAPES for link in LINK_FORMS]
    cases += [f"<gallery {options}>\nFile:{name}|כיתוב\nFile:{name}|link=\n</gallery>"
              for name in (LANDSCAPE, PORTRAIT, TINY, GIF) for options in GALLERIES]
    cases += ["[[File:Retina test missing.png|120px|link=]]", f"[[File:{LANDSCAPE}|thumb={PORTRAIT}]]",
              f"[[Media:{LANDSCAPE}]]", f"[[:File:{LANDSCAPE}]]"]
    return cases


@pytest.mark.parametrize("wikitext", _all_cases())
def test_every_image_form_renders_with_2x_only(api: str, wikitext: str) -> None:
    for srcset in _srcsets(_parse(api, wikitext)):
        entries = [entry.split() for entry in srcset.split(",")]
        assert len(entries) == 1, f"{wikitext!r} links more than one copy: {srcset!r}"
        url, density = entries[0]
        # "1.5x" only when the copy is the original file (core's own label then); never a 1.5x thumbnail.
        assert density == "2x" or (density == "1.5x" and "/thumb/" not in url), f"{wikitext!r} has srcset {srcset!r}"


def test_image_smaller_than_the_thumb_gets_no_2x(api: str) -> None:
    assert _srcsets(_parse(api, f"[[File:{GIF}|120px]]")) == []


def test_bitmap_thumb_gets_a_2x(api: str) -> None:
    """The hook is actually on: without this, every other test passes vacuously."""
    assert len(_srcsets(_parse(api, f"[[File:{LANDSCAPE}|120px|link=]]"))) == 1


@pytest.mark.parametrize("special", ["Special:ListFiles", "Special:NewFiles"])
def test_file_lists_render(base_url: str, api: str, special: str) -> None:
    html = requests.get(f"{base_url}/index.php", params={"title": special}, timeout=60).text
    assert not PHP_ERROR_RE.search(html)


def test_file_page_history_thumb_has_no_2x(base_url: str, api: str) -> None:
    html = requests.get(f"{base_url}/index.php", params={"title": f"File:{LANDSCAPE}"}, timeout=60).text
    assert not PHP_ERROR_RE.search(html)
    history = html.split('id="filehistory"', 1)[-1]
    assert _srcsets(history) == [], "the file history table never had 2x copies on prod"
