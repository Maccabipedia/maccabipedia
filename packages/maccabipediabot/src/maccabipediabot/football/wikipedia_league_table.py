"""The Israeli Premier League table as English Wikipedia's season page has it.

livescore.com does not follow Israeli Football Association rulings: a technical win stays the
draw played on the pitch, and a points deduction is never applied. Wikipedia's editors apply both,
usually within hours of the final whistle or the ruling (measured 2026-10-31 over 56 games:
median 1.6 h, worst 29 h), so the numbers come from there and livescore only guards the timing.
"""
from dataclasses import dataclass

import mwparserfromhell
import requests

_WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
_USER_AGENT = "MaccabiPediaBot/1.0 (https://www.maccabipedia.co.il; league table)"

# Keyed by the Wikipedia article each table's name_XXX links to: article titles outlive the
# three-letter codes and the display names, which editors change between seasons.
WIKIPEDIA_TEAM_ARTICLE_TO_HEBREW = {
    "Beitar Jerusalem F.C.": "בית\"ר ירושלים",
    "Bnei Sakhnin F.C.": "בני סכנין",
    "F.C. Ashdod": "מ.ס. אשדוד",
    "Hapoel Be'er Sheva F.C.": "הפועל באר שבע",
    "Hapoel Hadera F.C.": "הפועל חדרה",
    "Hapoel Haifa F.C.": "הפועל חיפה",
    "Hapoel Ironi Kiryat Shmona F.C.": "עירוני קריית שמונה",
    "Hapoel Jerusalem F.C.": "הפועל ירושלים",
    "Hapoel Petah Tikva F.C.": "הפועל פתח תקווה",
    "Hapoel Ramat Gan Givatayim F.C.": "הפועל רמת גן",
    "Hapoel Tel Aviv F.C.": "הפועל תל אביב",
    "Ironi Tiberias F.C.": "עירוני טבריה",
    "Maccabi Bnei Reineh F.C.": "מכבי בני ריינה",
    "Maccabi Haifa F.C.": "מכבי חיפה",
    "Maccabi Netanya F.C.": "מכבי נתניה",
    "Maccabi Petah Tikva F.C.": "מכבי פתח תקווה",
    "Maccabi Tel Aviv F.C.": "מכבי תל אביב",
}


@dataclass(frozen=True)
class TeamRow:
    name: str
    win: int
    draw: int
    loss: int
    goals_for: int
    goals_against: int
    points: int

    @property
    def played(self) -> int:
        return self.win + self.draw + self.loss

    def as_template_row(self) -> str:
        """One row of תבנית:טבלת ליגת כדורגל: name^played^W^D^L^GF^GA^points."""
        return "^".join(str(value) for value in (
            self.name, self.played, self.win, self.draw, self.loss,
            self.goals_for, self.goals_against, self.points))


def fetch_season_wikitext(page_title: str) -> str:
    response = requests.get(_WIKIPEDIA_API, headers={"User-Agent": _USER_AGENT}, timeout=30, params={
        "action": "query", "prop": "revisions", "titles": page_title, "rvprop": "content",
        "rvslots": "main", "format": "json", "formatversion": "2"})
    if response.status_code != 200 or "application/json" not in response.headers.get("Content-Type", ""):
        raise RuntimeError(f"Wikipedia answered {response.status_code} for {page_title!r}: {response.text[:500]}")
    page = response.json()["query"]["pages"][0]
    if page.get("missing"):
        raise RuntimeError(f"No Wikipedia page {page_title!r}")
    return page["revisions"][0]["slots"]["main"]["content"]


def _sports_tables(wikitext: str) -> list:
    # Recursive: the regular-season table sits inside <onlyinclude>.
    return [template for template in mwparserfromhell.parse(wikitext).filter_templates()
            if template.name.strip().lower().replace("_", " ") == "#invoke:sports table"]


def _value(table, key: str, default: str | None = None) -> str:
    if table.has(key):
        return table.get(key).value.strip_code().strip()
    if default is None:
        raise ValueError(f"Wikipedia table has no {key}")
    return default


def _number(table, key: str, default: str | None = None) -> int:
    # Editors write deductions with a Unicode minus as often as with a hyphen.
    return int(_value(table, key, default).replace("−", "-"))


def _team_codes_in_order(table) -> list[str]:
    """Positions as the editors ranked them, by IFA tie-breakers: team_order=, or teamN= per position.

    A relegation-round table numbers by overall position, so its teamN start at team7, in any order.
    """
    if table.has("team_order"):
        return [code.strip() for code in _value(table, "team_order").split(",") if code.strip()]
    positions = {}
    for param in table.params:
        name = str(param.name).strip()
        if name.startswith("team") and name[4:].isdigit():
            positions[int(name[4:])] = param.value.strip_code().strip()
    if not positions:
        raise ValueError("Wikipedia table has neither team_order nor teamN")
    return [positions[position] for position in sorted(positions)]


def _hebrew_name(table, code: str) -> str:
    links = mwparserfromhell.parse(str(table.get(f"name_{code}").value)).filter_wikilinks()
    if not links:
        raise ValueError(f"name_{code} links to no article")
    article = links[0].title.strip()
    if article not in WIKIPEDIA_TEAM_ARTICLE_TO_HEBREW:
        raise ValueError(f"No Hebrew name for Wikipedia article {article!r} (name_{code}); "
                         f"add it to WIKIPEDIA_TEAM_ARTICLE_TO_HEBREW")
    return WIKIPEDIA_TEAM_ARTICLE_TO_HEBREW[article]


def parse_league_tables(wikitext: str, table_indexes: list[int]) -> list[TeamRow]:
    """The rows of the page's Sports tables at table_indexes (0 = first on the page), in order.

    Tables are picked by position, not by their section= name, because editors misspell it
    ("Relegations round" on the 2025-26 page).
    """
    tables = _sports_tables(wikitext)
    rows = []
    for index in table_indexes:
        if index >= len(tables):
            raise ValueError(f"Wikipedia page has {len(tables)} league tables, no table {index}")
        table = tables[index]
        for code in _team_codes_in_order(table):
            win, draw = _number(table, f"win_{code}"), _number(table, f"draw_{code}")
            rows.append(TeamRow(
                name=_hebrew_name(table, code),
                win=win,
                draw=draw,
                loss=_number(table, f"loss_{code}"),
                goals_for=_number(table, f"gf_{code}"),
                goals_against=_number(table, f"ga_{code}"),
                points=win * 3 + draw + _number(table, f"adjust_points_{code}", "0"),
            ))
    return rows
