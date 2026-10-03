"""Turn the model's digest text into the Telegram HTML message.

The model writes plain Hebrew lines with wiki links, ``[[title|text]]`` or ``[[title]]``.
A link becomes an ``<a>`` only when its title is one the collected data names, so a title
the model made up stays plain text instead of a dead link. A bare URL survives only if it is
on the wiki or one the data names (a merged PR): edit comments are written by any editor and
reach the model, so a URL planted in one must not become a link in the founders' group.
Everything else is escaped.
"""
from __future__ import annotations

import html
import re

from maccabipediabot.maintenance.daily_digest.collect import WIKI_URL, page_url

RIGHT_TO_LEFT_MARK = "‏"
SIGNATURE = "— תקציר יומי אוטומטי של מכביפדיה"
_WIKI_LINK = re.compile(r"\[\[([^\[\]|]+)(?:\|([^\[\]]+))?\]\]")
_BARE_URL = re.compile(r"https?://[^\s<>\"]+")
_TRAILING_PUNCTUATION = ".,;:!?)"


def _plain(text: str, known_urls: set[str]) -> str:
    def keep_known(match: re.Match) -> str:
        url = match.group(0).rstrip(_TRAILING_PUNCTUATION)
        return match.group(0) if url in known_urls or url.startswith(WIKI_URL) else ""
    return html.escape(_BARE_URL.sub(keep_known, text))


def _render_line(line: str, known_titles: set[str], known_urls: set[str]) -> str:
    parts = []
    position = 0
    for match in _WIKI_LINK.finditer(line):
        parts.append(_plain(line[position:match.start()], known_urls))
        title = match.group(1).strip()
        text = (match.group(2) or title).strip()
        if title in known_titles:
            parts.append(f'<a href="{html.escape(page_url(title))}">{html.escape(text)}</a>')
        else:
            parts.append(html.escape(text))
        position = match.end()
    parts.append(_plain(line[position:], known_urls))
    return RIGHT_TO_LEFT_MARK + "".join(parts)


def render_message(digest_text: str, known_titles: set[str], known_urls: set[str]) -> str:
    """Empty when the model wrote nothing; blank lines between paragraphs are kept."""
    lines = [line.rstrip() for line in digest_text.strip().splitlines()]
    if not any(lines):
        return ""
    lines.append("")
    lines.append(SIGNATURE)
    return "\n".join(_render_line(line, known_titles, known_urls) if line else "" for line in lines)
