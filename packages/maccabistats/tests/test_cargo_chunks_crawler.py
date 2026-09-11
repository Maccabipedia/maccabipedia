"""MaccabiPedia's Imunify360 WAF used to answer bot requests with HTTP 415; pinning
`Accept: application/json` fixed that, but ~15% of scheduled runs still get a 200 whose
body parses as a bare JSON string (a block page). That used to blow up deep in the
iteration as "'str' object has no attribute 'items'", far from the real cause. Guard that
the crawler now rejects those bodies at the parse point and logs the raw response."""
import logging

import pytest
import requests

from maccabistats.parse.maccabipedia.maccabipedia_cargo_chunks_crawler import (
    MaccabiPediaCargoChunksCrawler,
)

CARGO_URL = "https://www.maccabipedia.co.il/index.php?title=Special:CargoExport&format=json"


def _response(body: str, content_type: str = "application/json") -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response.url = CARGO_URL
    response._content = body.encode("utf-8")
    response.headers["Content-Type"] = content_type
    response.headers["Server"] = "openresty/1.29.2.3"
    return response


def test_row_array_is_returned_unchanged():
    rows = MaccabiPediaCargoChunksCrawler._parse_cargo_rows(
        _response('[{"_pageName": "אבי כהן"}, {"_pageName": "מוטלה שפיגלר"}]'))

    assert [row["_pageName"] for row in rows] == ["אבי כהן", "מוטלה שפיגלר"]


def test_empty_result_is_allowed():
    assert MaccabiPediaCargoChunksCrawler._parse_cargo_rows(_response("[]")) == []


def test_bare_json_string_raises_instead_of_corrupting_iteration(caplog):
    with caplog.at_level(logging.ERROR):
        with pytest.raises(ValueError, match="bare str"):
            MaccabiPediaCargoChunksCrawler._parse_cargo_rows(_response('"imunify360 block"'))

    # The whole point: the raw body reaches the CI log so we can show it to the host.
    assert "imunify360 block" in caplog.text
    assert "openresty/1.29.2.3" in caplog.text


def test_html_block_page_raises_with_body_logged(caplog):
    with caplog.at_level(logging.ERROR):
        with pytest.raises(ValueError, match="non-JSON body"):
            MaccabiPediaCargoChunksCrawler._parse_cargo_rows(
                _response("<html>403 Forbidden</html>", content_type="text/html"))

    assert "403 Forbidden" in caplog.text
