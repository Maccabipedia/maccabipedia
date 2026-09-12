"""Thin, validated MediaWiki API client shared by the perf tooling.

Cargo Export and api.php both return HTML error pages on internal errors, so
every response is checked for status and content type before parsing.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests

DEFAULT_BASE_URL = "https://www.maccabipedia.co.il"
USER_AGENT = "MaccabipediaPerfBenchmark/1.0 (+https://www.maccabipedia.co.il)"

# Resolved against the repo root, not the working directory: .gitignore's
# `.claude/tmp/` has an interior slash and so is anchored to the root. A
# relative default would drop output in infra/perf/.claude/tmp/ when the
# scripts are run as documented (`cd infra/perf`), where it is NOT ignored and
# shows up as untracked junk after every run.
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = REPO_ROOT / ".claude" / "tmp" / "perf"

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
        """Return the subset of `titles` that exist, resolving in batches of 50.

        MediaWiki normalizes requested titles (underscores to spaces, trimming,
        first-letter casing) and returns the normalized form in `page.title`,
        reporting the mapping under `query.normalized`. A Cargo value carrying a
        stray underscore would otherwise come back under a different string and
        be misread as a missing page, so the mapping is folded back in and the
        caller's own spelling is what gets returned.
        """
        found: set[str] = set()
        for start in range(0, len(titles), 50):
            batch = titles[start:start + 50]
            payload = self.get(action="query", titles="|".join(batch))
            query = payload.get("query", {})
            # normalized: [{"from": "<as asked>", "to": "<as stored>"}, ...]
            normalized_from = {
                entry["to"]: entry["from"] for entry in query.get("normalized", [])
            }
            for page in query.get("pages", []):
                if page.get("missing") or page.get("invalid"):
                    continue
                title = page["title"]
                found.add(title)
                if title in normalized_from:
                    found.add(normalized_from[title])
        return found
