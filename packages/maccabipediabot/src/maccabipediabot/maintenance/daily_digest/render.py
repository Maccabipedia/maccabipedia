"""Turn the model's digest text into the Telegram HTML message.

The model writes plain Hebrew lines with wiki links, ``[[title|text]]`` or ``[[title]]``, and
external links, ``[url text]``. A link becomes an inline ``<a>`` only when its title or URL is
one the collected data names, so one the model made up stays plain text instead of a dead or
planted link. A bare URL survives only if it is
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
# The model sometimes double-brackets an external link, [[url text]]; both forms are accepted.
_LINK = re.compile(r"\[\[?(?P<url>https?://[^\s\[\]]+) (?P<url_label>[^\[\]]+)\]\]?"
                   r"|\[\[(?P<title>[^\[\]|]+)(?:\|(?P<label>[^\[\]]+))?\]\]")
_BARE_URL = re.compile(r"https?://[^\s<>\"]+")
_TRAILING_PUNCTUATION = ".,;:!?)"
_PULL_NUMBER = re.compile(r"/pull/(\d+)$")


def _anchor(url: str, text: str) -> str:
    return f'<a href="{html.escape(url)}">{html.escape(text)}</a>'


def _short_label(url: str) -> str:
    pull = _PULL_NUMBER.search(url)
    return f"PR #{pull.group(1)}" if pull else "קישור"


def _plain(text: str, known_urls: set[str]) -> str:
    """Escape ``text``; a bare URL the data names becomes a short inline link, any other goes."""
    parts = []
    position = 0
    for match in _BARE_URL.finditer(text):
        url = match.group(0).rstrip(_TRAILING_PUNCTUATION)
        parts.append(html.escape(text[position:match.start()]))
        if url in known_urls or url.startswith(WIKI_URL):
            parts.append(_anchor(url, _short_label(url)))
        position = match.start() + len(url)
    parts.append(html.escape(text[position:]))
    return "".join(parts)


def _render_line(line: str, known_titles: set[str], known_urls: set[str]) -> str:
    parts = []
    position = 0
    for match in _LINK.finditer(line):
        parts.append(_plain(line[position:match.start()], known_urls))
        if match.group("url"):
            target = match.group("url") if match.group("url") in known_urls else None
            text = match.group("url_label").strip()
        else:
            title = match.group("title").strip()
            target = page_url(title) if title in known_titles else None
            text = (match.group("label") or title).strip()
        if target:
            parts.append(_anchor(target, text))
        else:
            parts.append(html.escape(text))
        position = match.end()
    parts.append(_plain(line[position:], known_urls))
    return RIGHT_TO_LEFT_MARK + "".join(parts)


def render_message(digest_text: str, known_titles: set[str], known_urls: set[str]) -> str:
    """Headline, blank line, bullets, blank line, signature; empty when the model wrote nothing.

    The layout is fixed here rather than trusted to the prompt: the model puts blank lines
    between bullets on busy days, which doubles the message's height on a phone.
    """
    lines = [line.strip() for line in digest_text.strip().splitlines() if line.strip()]
    if not lines:
        return ""
    headline, *bullets = (_render_line(line, known_titles, known_urls) for line in lines)
    signature = _render_line(SIGNATURE, set(), set())
    return "\n".join([headline, "", *bullets, "", signature] if bullets else [headline, "", signature])
