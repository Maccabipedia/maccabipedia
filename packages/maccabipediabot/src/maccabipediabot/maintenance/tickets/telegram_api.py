"""The few Telegram Bot API calls the ticket bot needs, over plain requests."""
from __future__ import annotations

import requests

# Bots may download files up to this size through getFile.
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024


class TelegramApi:
    def __init__(self, token: str) -> None:
        self._base = f"https://api.telegram.org/bot{token}"
        self._file_base = f"https://api.telegram.org/file/bot{token}"
        self._session = requests.Session()

    def _call(self, method: str, **params) -> object:
        response = self._session.post(f"{self._base}/{method}", json=params, timeout=60)
        payload = response.json()
        if not payload.get("ok"):
            # Never echo the URL: it carries the token.
            raise RuntimeError(f"Telegram {method} failed: {payload.get('description', response.status_code)}")
        return payload["result"]

    def get_updates(self, offset: int | None = None, limit: int = 100) -> list[dict]:
        """Unconfirmed updates, oldest first. Passing ``offset`` confirms everything
        before it, so Telegram will not return those again."""
        params: dict = {"timeout": 0, "limit": limit, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        result = self._call("getUpdates", **params)
        assert isinstance(result, list)
        return result

    def download(self, file_id: str) -> bytes:
        file_info = self._call("getFile", file_id=file_id)
        assert isinstance(file_info, dict)
        response = self._session.get(f"{self._file_base}/{file_info['file_path']}", timeout=120)
        response.raise_for_status()
        return response.content

    def send_message(self, chat_id: int, text: str) -> None:
        """Send ``text`` as Telegram HTML; the caller escapes everything but its links."""
        self._call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                   link_preview_options={"is_disabled": True})

    def send_document(self, chat_id: int, file_id: str, caption: str, reply_to: int) -> None:
        """Send an already-uploaded Telegram file back by id — no re-upload, and the
        user can reply to it because the reply carries the document."""
        self._call("sendDocument", chat_id=chat_id, document=file_id, caption=caption,
                   reply_parameters={"message_id": reply_to, "allow_sending_without_reply": True})
