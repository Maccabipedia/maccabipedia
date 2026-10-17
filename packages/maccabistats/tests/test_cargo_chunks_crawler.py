"""MaccabiPedia's Imunify360 WAF used to answer bot requests with HTTP 415; pinning
`Accept: application/json` fixed that, but ~15% of scheduled runs still get a 200 whose
body parses as a bare JSON string (a block page). That used to blow up deep in the
iteration as "'str' object has no attribute 'items'", far from the real cause. Guard that
the crawler now rejects those bodies at the parse point and logs the raw response."""
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import requests
from urllib3 import HTTPResponse

from maccabistats.parse.maccabipedia import maccabipedia_cargo_chunks_crawler as crawler_module
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


# --- the host's 508 "Resource Limit Is Reached" -------------------------------------
# A scheduled run died on a single 508 mid-crawl. It clears within seconds, so retry it,
# but never obey its four-hour Retry-After.

def _crawler_retry():
    return crawler_module._build_session().get_adapter(CARGO_URL).max_retries


def _urllib3_response(status: int, retry_after: str) -> HTTPResponse:
    return HTTPResponse(body=b"", status=status, headers={"Retry-After": retry_after})


def test_session_retries_on_host_resource_limit_508():
    assert 508 in _crawler_retry().status_forcelist


def test_host_508_retry_after_of_four_hours_is_capped():
    assert _crawler_retry().get_retry_after(_urllib3_response(508, "14400")) == 60


def test_short_retry_after_is_obeyed_as_is():
    assert _crawler_retry().get_retry_after(_urllib3_response(429, "5")) == 5


def test_capped_retry_survives_increment():
    next_retry = _crawler_retry().increment(method="GET", url="/", response=_urllib3_response(508, "14400"))
    assert next_retry.get_retry_after(_urllib3_response(508, "14400")) == 60


def test_crawler_rides_over_one_508_and_returns_the_rows(monkeypatch):
    monkeypatch.setattr(crawler_module, "_MAX_RETRY_AFTER_SECONDS", 0)
    answers = [(508, "text/html", b"<HTML>Resource Limit Is Reached</HTML>"),
               (200, "application/json", b'[{"_pageName": "x"}]')]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            status, content_type, body = answers.pop(0)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Retry-After", "14400")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    threading.Thread(target=server.handle_request, daemon=True).start()
    try:
        crawler = MaccabiPediaCargoChunksCrawler("Games_Events", "_pageName")
        crawler.base_crawling_address = f"http://127.0.0.1:{server.server_port}/?format=json"
        rows = list(crawler)
    finally:
        server.server_close()
    assert rows == [{"_pageName": "x"}]
