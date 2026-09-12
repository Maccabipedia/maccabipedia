"""Thin, validated MediaWiki API client shared by the perf tooling.

Cargo Export and api.php both return HTML error pages on internal errors, so
every response is checked for status and content type before parsing.
"""
from __future__ import annotations

import time
from typing import Any

import requests

DEFAULT_BASE_URL = "https://www.maccabipedia.co.il"
USER_AGENT = "MaccabipediaPerfBenchmark/1.0 (+https://www.maccabipedia.co.il)"

# Shared hosting applies per-account CPU caps; pace requests so the probe does
# not distort the very thing it measures.
MIN_SECONDS_BETWEEN_REQUESTS = 1.0


class WikiApiError(RuntimeError):
    """Raised when the wiki returns something that is not a usable API response."""


class WikiApi:
    def __init__(self, base_url: str = DEFAULT_BASE_URL,
                 pace_seconds: float = MIN_SECONDS_BETWEEN_REQUESTS) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api.php"
        self.pace_seconds = pace_seconds
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._last_request_at = 0.0

    def _pace(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.pace_seconds:
            time.sleep(self.pace_seconds - elapsed)
        self._last_request_at = time.monotonic()

    def get(self, **params: Any) -> dict[str, Any]:
        params.setdefault("format", "json")
        params.setdefault("formatversion", "2")
        self._pace()
        response = self.session.get(self.api_url, params=params, timeout=180)
        if response.status_code != 200:
            raise WikiApiError(
                f"HTTP {response.status_code} from api.php "
                f"(params={ {k: v for k, v in params.items() if k != 'format'} })"
            )
        content_type = response.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            raise WikiApiError(
                f"expected JSON from api.php, got {content_type!r}; "
                f"body starts: {response.text[:200]!r}"
            )
        payload = response.json()
        if "error" in payload:
            raise WikiApiError(f"API error: {payload['error'].get('info', payload['error'])}")
        return payload

    def cargo_query(self, tables: str, fields: str, **extra: Any) -> list[dict[str, Any]]:
        payload = self.get(action="cargoquery", tables=tables, fields=fields, **extra)
        return [row["title"] for row in payload.get("cargoquery", [])]

    def existing_titles(self, titles: list[str]) -> set[str]:
        """Return the subset of `titles` that exist, resolving in batches of 50."""
        found: set[str] = set()
        for start in range(0, len(titles), 50):
            batch = titles[start:start + 50]
            payload = self.get(action="query", titles="|".join(batch))
            for page in payload.get("query", {}).get("pages", []):
                if not page.get("missing") and not page.get("invalid"):
                    found.add(page["title"])
        return found
