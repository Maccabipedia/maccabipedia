"""The text of the data page: one store-template call per credit, grouped by season and title.

Rendering and parsing are pure. The parser reads a line the way MediaWiki does, so that
"the rows the page stores" can be compared with the rows in the table.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import NamedTuple

import mwparserfromhell
from mwparserfromhell.nodes import Heading, Template

from maccabipediabot.maintenance.football.player_titles.rule import Credit, Title

PAGE_TITLE = "הזנת תארי שחקני כדורגל"
STORE_TEMPLATE = "תארי שחקני כדורגל/הזנה לקארגו"
HEADER_MARKER = "<!-- player-titles-data-page -->"

HEADER = (
    f"{HEADER_MARKER}\n"
    "__NOINDEX__\n"
    "עמוד זה מזין את טבלת התארים של שחקני הכדורגל (Football_Player_Titles): שורה לכל שחקן, עונה ומפעל. "
    "העמוד בבנייה ונכתב כרגע בידי הבוט בלבד — אין לערוך אותו בשלב זה, עריכות ידניות יידרסו.\n"
)

PLAYER_PARAM = "שחקן"
SEASON_PARAM = "עונה"
COMPETITION_PARAM = "מפעל"
REMOVED_PARAM = "הוסר"
APPROVED_PARAM = "אושר"

# What PHP's trim() removes, which is what MediaWiki strips from a named template argument.
# Python's str.strip() also removes no-break spaces and other Unicode spaces, and a name
# must reach the table byte for byte.
_PHP_TRIM_CHARACTERS = " \t\n\r\0\x0b"

# Characters that would end or split the template call, or open a tag or a comment.
_UNSAFE_CHARACTERS = ("|", "=", "{", "}", "<", ">", "\n", "\r")


class UnsafeName(ValueError):
    """A value that cannot be written into a template call and read back unchanged."""


class Line(NamedTuple):
    """One store-template call on the page."""
    credit: Credit
    removed: str | None
    approved: str | None
    block: Title | None


class ParsedPage(NamedTuple):
    has_header_marker: bool
    blocks: list[Title]
    lines: list[Line]


def _checked(value: str) -> str:
    is_trimmed = value == value.strip(_PHP_TRIM_CHARACTERS)
    if not value or not is_trimmed or any(character in value for character in _UNSAFE_CHARACTERS):
        raise UnsafeName(f"{value!r} cannot be written into a template call and read back unchanged")
    return value


def _render_line(credit: Credit, removed_reason: str | None) -> str:
    call = (
        f"{{{{{STORE_TEMPLATE} |{PLAYER_PARAM}={_checked(credit.player)}"
        f" |{SEASON_PARAM}={_checked(credit.season)} |{COMPETITION_PARAM}={_checked(credit.competition)}"
    )
    if removed_reason is not None:
        call += f" |{REMOVED_PARAM}={_checked(removed_reason)}"
    return call + "}}\n"


def render_page(credits_by_title: dict[Title, list[str]], removed: dict[Credit, str]) -> str:
    """The whole page: header, then seasons oldest first, a block per title, a line per player.

    A credit in `removed` is written with its reason and stores no row, whether or not the
    rule lists the player.
    """
    players_by_title: dict[Title, set[str]] = defaultdict(set)
    for title, players in credits_by_title.items():
        players_by_title[title].update(players)
    for credit in removed:
        players_by_title[Title(credit.season, credit.competition)].add(credit.player)

    parts = [HEADER]
    current_season = None
    for title in sorted(players_by_title):
        if title.season != current_season:
            parts.append(f"== {_checked(title.season)} ==\n")
            current_season = title.season
        parts.append(f"=== {_checked(title.competition)} ===\n")
        for player in sorted(players_by_title[title]):
            credit = Credit(player, title.season, title.competition)
            parts.append(_render_line(credit, removed.get(credit)))
    return "".join(parts)


def _argument(template: Template, name: str) -> str | None:
    if not template.has(name):
        return None
    return str(template.get(name).value).strip(_PHP_TRIM_CHARACTERS)


def parse_page(text: str) -> ParsedPage:
    """Read the top-level headings and store-template calls of the page."""
    blocks: list[Title] = []
    lines: list[Line] = []
    season: str | None = None
    block: Title | None = None

    for node in mwparserfromhell.parse(text).nodes:
        if isinstance(node, Heading):
            heading = str(node.title).strip(_PHP_TRIM_CHARACTERS)
            if node.level == 2:
                season, block = heading, None
            elif node.level == 3 and season is not None:
                block = Title(season, heading)
                blocks.append(block)
            continue

        if not isinstance(node, Template) or str(node.name).strip(_PHP_TRIM_CHARACTERS) != STORE_TEMPLATE:
            continue

        credit = Credit(
            _argument(node, PLAYER_PARAM) or "",
            _argument(node, SEASON_PARAM) or "",
            _argument(node, COMPETITION_PARAM) or "",
        )
        lines.append(Line(
            credit=credit,
            removed=_argument(node, REMOVED_PARAM) or None,
            approved=_argument(node, APPROVED_PARAM) or None,
            block=block,
        ))

    return ParsedPage(has_header_marker=HEADER_MARKER in text, blocks=blocks, lines=lines)


def stored_credits(parsed: ParsedPage) -> Counter[Credit]:
    """The rows MediaWiki stores for this page: every line without a removal reason."""
    return Counter(line.credit for line in parsed.lines if line.removed is None)
