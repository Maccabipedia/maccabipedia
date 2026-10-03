"""Turn the model's digest text into the Telegram HTML message.

The model writes plain Hebrew lines with wiki links, ``[[title|text]]`` or ``[[title]]``.
A link becomes an ``<a>`` only when its title is one the collected data names, so a title
the model made up stays plain text instead of a dead link. Everything else is escaped.
"""
from __future__ import annotations

import html
import re

from maccabipediabot.maintenance.daily_digest.collect import page_url

RIGHT_TO_LEFT_MARK = "‏"
SIGNATURE = "— תקציר יומי אוטומטי של מכביפדיה"
_WIKI_LINK = re.compile(r"\[\[([^\[\]|]+)(?:\|([^\[\]]+))?\]\]")


def _render_line(line: str, known_titles: set[str]) -> str:
    parts = []
    position = 0
    for match in _WIKI_LINK.finditer(line):
        parts.append(html.escape(line[position:match.start()]))
        title = match.group(1).strip()
        text = (match.group(2) or title).strip()
        if title in known_titles:
            parts.append(f'<a href="{html.escape(page_url(title))}">{html.escape(text)}</a>')
        else:
            parts.append(html.escape(text))
        position = match.end()
    parts.append(html.escape(line[position:]))
    return RIGHT_TO_LEFT_MARK + "".join(parts)


def render_message(digest_text: str, known_titles: set[str]) -> str:
    """Empty when the model wrote nothing; blank lines between paragraphs are kept."""
    lines = [line.rstrip() for line in digest_text.strip().splitlines()]
    if not any(lines):
        return ""
    lines.append("")
    lines.append(SIGNATURE)
    return "\n".join(_render_line(line, known_titles) if line else "" for line in lines)
