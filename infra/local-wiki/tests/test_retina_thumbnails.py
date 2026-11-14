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


def _page(base_url: str, title: str) -> str:
    """A page's HTML; a 500 must fail here, since the local wiki does not print PHP errors."""
    response = requests.get(f"{base_url}/index.php", params={"title": title}, timeout=60)
    assert response.status_code == 200, f"{title} answered {response.status_code}"
    assert "internal_api_error" not in response.text and "MWException" not in response.text
    return response.text


# Where core gave a 2x, the hook must too. The hook swallows its own errors, so without these
# a hook that failed on every image would pass every test above.
@pytest.mark.parametrize("wikitext", [
    f"[[File:{LANDSCAPE}|120px|link=]]", f"[[File:{LANDSCAPE}|120px]]", f"[[File:{LANDSCAPE}|thumb]]",
    f"[[File:{PORTRAIT}|x90px]]", f"[[File:{PORTRAIT}|thumb|upright]]",
    f"<gallery>\nFile:{LANDSCAPE}\n</gallery>", f"<gallery>\nFile:{PORTRAIT}|link=\n</gallery>",
    f"<gallery mode=packed>\nFile:{PORTRAIT}\n</gallery>",
])
def test_images_core_gave_a_2x_still_get_one(api: str, wikitext: str) -> None:
    srcsets = _srcsets(_parse(api, wikitext))
    assert len(srcsets) == 1 and srcsets[0].endswith(" 2x") and "/thumb/" in srcsets[0], f"{wikitext!r}: {srcsets}"


@pytest.mark.parametrize("special", ["Special:ListFiles", "Special:NewFiles"])
def test_file_lists_render(base_url: str, api: str, special: str) -> None:
    _page(base_url, special)


def test_file_page_main_image_2x_and_history_without(base_url: str, api: str) -> None:
    main, _, history = _page(base_url, f"File:{LANDSCAPE}").partition('id="filehistory"')
    assert history, "no file history table on the File page"
    assert len(_srcsets(main.split('id="file"', 1)[-1])) == 1, "the File page's main image lost its 2x"
    assert _srcsets(history) == [], "the file history table never had 2x copies on prod"
