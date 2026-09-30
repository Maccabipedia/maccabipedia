"""The wiki half of uploading a ticket: find its game, check it is new, upload it."""
from __future__ import annotations

import os
from datetime import date

import requests

from maccabipediabot.common.maccabipedia_http import (
    MACCABIPEDIA_JSON_HEADERS,
    build_maccabipedia_session,
    parse_cargo_rows,
)
from maccabipediabot.maintenance.tickets.ticket_names import CARGO_TABLES, Sport

API_URL = "https://www.maccabipedia.co.il/api.php"
CARGO_EXPORT_URL = "https://www.maccabipedia.co.il/index.php"

_MIME_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".pdf": "application/pdf"}

_session = build_maccabipedia_session()


class GameLookupError(ValueError):
    """No game, or more than one, on the ticket's date — the sender has to fix it."""


def game_pages_on(sport: Sport, game_date: date) -> list[str]:
    table = CARGO_TABLES[sport]
    response = _session.get(CARGO_EXPORT_URL, params={
        "title": "Special:CargoExport",
        "format": "json",
        "tables": table,
        "fields": "_pageName",
        "where": f"{table}.Date='{game_date:%Y-%m-%d}'",
    })
    response.raise_for_status()
    return [row["_pageName"] for row in parse_cargo_rows(response)]


def find_game_page(sport: Sport, game_date: date) -> str:
    pages = game_pages_on(sport, game_date)
    if not pages:
        raise GameLookupError(f"אין משחק {sport.value} בתאריך {game_date:%d-%m-%Y}")
    if len(pages) > 1:
        raise GameLookupError(f"יש {len(pages)} משחקי {sport.value} בתאריך {game_date:%d-%m-%Y}: {', '.join(pages)}")
    return pages[0]


def file_exists(file_name: str) -> bool:
    response = _session.get(API_URL, params={
        "action": "query", "titles": f"File:{file_name}", "format": "json", "formatversion": "2",
    })
    response.raise_for_status()
    pages = response.json()["query"]["pages"]
    return not pages[0].get("missing", False)


def upload_file(site, file_name: str, data: bytes, text: str, comment: str) -> None:
    """Upload ``data`` as ``File:<file_name>`` with ``text`` as its page text.

    Uses requests directly with pywikibot's cookies and CSRF token, because pywikibot's
    own multipart builder writes a ``MIME-Version`` header per part that Apache rejects
    with 400 Bad Request.
    """
    from pywikibot.comms import http as pw_http

    cookies = {c.name: c.value for c in pw_http.cookie_jar if "maccabipedia" in (c.domain or "")}
    script = os.environ.get("MACCABIPEDIA_UA_SCRIPT", "upload_tickets")
    user_agent = f"{script} (maccabipedia:he; User:{site.user()}) Pywikibot/9.6.0"
    extension = os.path.splitext(file_name)[1].lower()

    response = requests.post(
        API_URL,
        data={
            "action": "upload",
            "filename": file_name,
            "comment": comment,
            "text": text,
            "token": site.tokens["csrf"],
            "ignorewarnings": "1",
            "format": "json",
        },
        files={"file": ("FAKE-NAME", data, _MIME_TYPES.get(extension, "application/octet-stream"))},
        cookies=cookies,
        headers={"User-Agent": user_agent, **MACCABIPEDIA_JSON_HEADERS},
        timeout=120,
    )

    if "application/json" not in response.headers.get("Content-Type", ""):
        raise RuntimeError(f"Upload failed with non-JSON response (status {response.status_code}): {response.text[:300]}")
    result = response.json()
    if "error" in result:
        raise RuntimeError(f"Upload API error: {result['error']}")
    if result.get("upload", {}).get("result") != "Success":
        raise RuntimeError(f"Unexpected upload result: {result}")
