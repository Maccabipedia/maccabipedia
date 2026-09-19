"""Tests for `infra/recent-changes-review/render_report.py`.

The rendered page quotes edit comments and titles that any wiki user can write, and it is served
on a public tunnel. These pin the one property that matters: nothing in the markdown becomes live
HTML. They also fail CI if `markdown-it-py` stops being installed — it arrives only as a
dependency of `rich`, not as one of ours.
"""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "recent-changes-review" / "render_report.py"


def _load():
    spec = importlib.util.spec_from_file_location("render_report", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _body(page: str) -> str:
    return page.split("<main", 1)[1]


def test_raw_html_is_escaped():
    page = _load().render('<script>alert(1)</script>\n\n<img src=x onerror="alert(2)">\n', "r.md")
    body = _body(page)
    assert "<script" not in body
    assert "<img" not in body
    assert "&lt;script&gt;" in body


def test_javascript_links_are_not_linked():
    page = _load().render("[click](javascript:alert(1))\n", "r.md")
    assert 'href="javascript:' not in page


def test_markdown_still_renders():
    page = _load().render("## Suggestions\n\n- **bold** `code`\n", "r.md")
    body = _body(page)
    assert "<h2>Suggestions</h2>" in body
    assert "<strong>bold</strong>" in body
    assert "<code>code</code>" in body


def test_source_name_is_escaped():
    page = _load().render("x", "<b>evil</b>.md")
    assert "<b>evil</b>" not in page
