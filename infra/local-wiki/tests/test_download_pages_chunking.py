"""Chunked Special:Export — big manifests must split into URL-safe GET batches.

Prod's edge layer rejects POST to Special:Export, and Apache's request-line
limit (~8K) 414s a GET once the title list grows past ~50 game titles. The
downloader therefore splits titles into URL-budget chunks and merges the
per-chunk XML dumps back into one importable file.
"""
from urllib.parse import quote

from download_pages_from_prod import chunk_titles, merge_export_dumps

_DUMP_TEMPLATE = (
    '<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/" xml:lang="he">\n'
    "  <siteinfo>\n    <sitename>מכביפדיה</sitename>\n  </siteinfo>\n"
    "{pages}</mediawiki>\n"
)


def _dump_with_pages(*titles: str) -> str:
    pages = "".join(
        f"  <page>\n    <title>{title}</title>\n  </page>\n" for title in titles
    )
    return _DUMP_TEMPLATE.format(pages=pages)


def test_chunk_titles_respects_url_budget():
    long_hebrew_title = "משחק:15-07-2024 מכבי תל אביב נגד מכבי פתח תקווה - אלוף האלופים"
    titles = [f"{long_hebrew_title} {index}" for index in range(168)]
    budget = 6000

    chunks = chunk_titles(titles, budget=budget)

    assert len(chunks) > 1
    assert [title for chunk in chunks for title in chunk] == titles
    for chunk in chunks:
        # safe="" mirrors requests' quote_plus: '/' counts encoded too.
        encoded = quote("\n".join(chunk), safe="")
        assert len(encoded) <= budget


def test_chunk_titles_small_list_is_single_chunk():
    titles = ["ערן זהבי", "אבי כהן"]
    assert chunk_titles(titles, budget=6000) == [titles]


def test_merge_export_dumps_combines_pages_under_one_root():
    first = _dump_with_pages("ערן זהבי", "אבי כהן")
    second = _dump_with_pages("מוטל'ה שפיגלר")

    merged = merge_export_dumps([first, second])

    assert merged.count("<mediawiki") == 1
    assert merged.count("</mediawiki>") == 1
    assert merged.count("<page>") == 3
    assert "מוטל'ה שפיגלר" in merged
    assert merged.index("מוטל'ה שפיגלר") < merged.index("</mediawiki>")


def test_merge_export_dumps_skips_pageless_chunk():
    first = _dump_with_pages("ערן זהבי")
    empty = _DUMP_TEMPLATE.format(pages="")

    merged = merge_export_dumps([first, empty])

    assert merged.count("<page>") == 1
    assert merged.count("</mediawiki>") == 1
