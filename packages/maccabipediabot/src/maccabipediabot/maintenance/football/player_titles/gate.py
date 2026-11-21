"""The gate: do the credits give every profile the title lists it shows today?

Read-only. For each football profile, the six lists the live template computes (asked from
the wiki with `expandtemplates`, so it is the template's own answer and not a copy of its
logic) are compared with the lists the credits give for that player.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from collections.abc import Iterable
from typing import NamedTuple

import mwparserfromhell

from maccabipediabot.maintenance.football.player_titles.api import Api
from maccabipediabot.maintenance.football.player_titles.exports import CUP_KIND, LEAGUE_KIND
from maccabipediabot.maintenance.football.player_titles.rule import Credit

logger = logging.getLogger(__name__)

PROFILES_CATEGORY = "קטגוריה:פרופילי כדורגל"
PROFILE_TEMPLATE = "פרופיל כדורגל"
LIST_TEMPLATE = "פרופיל כדורגל/הרכבת רשימת זכיות/שחקן"
DISPLAY_NAME_FIELD = "שם להצגה"

# Two players with different titles; the self-test compares one's live lists with the
# other's credits and has to fail.
SELFTEST_PROFILE = "אבי נמני"
SELFTEST_OTHER_PLAYER = "שרן ייני"

_TITLES_PER_READ = 50
_PROFILES_PER_EXPANSION = 5
_SEASON = re.compile(r"\d{4}(/\d{2})?")
_CHUNK = re.compile(r"@@(\d+)@@(\d+)@@")
_ERROR_SNIPPET_LIMIT = 200


class Kind(NamedTuple):
    """One of the profile's six title lists."""
    key: str
    template_filter: str
    field_suffix: str


# In the order the profile template builds them. `field_suffix` names the manual fields:
# `הוספת זכיות <suffix> כשחקן` and `הסרת זכיות <suffix> כשחקן`.
KINDS = (
    Kind(LEAGUE_KIND, "|קטגוריית מפעל=ליגה", "באליפות"),
    Kind(CUP_KIND, "|קטגוריית מפעל=גביע", "בגביע המדינה"),
    Kind("גביע הטוטו", "|שם מפעל=גביע הטוטו", "בגביע הטוטו"),
    Kind("אלוף האלופים", "|שם מפעל=אלוף האלופים", "באלוף האלופים"),
    Kind("גביע ליליאן", "|שם מפעל=גביע ליליאן", "בגביע ליליאן"),
    Kind("גביע אסיה לאלופות", "|שם מפעל=גביע אסיה לאלופות", "בגביע אסיה לאלופות"),
)


class Profile(NamedTuple):
    title: str
    display_name: str | None
    add: dict[str, str]
    remove: dict[str, str]


class LiveLists(NamedTuple):
    lists: dict[str, list[str]]
    error: str | None


def profile_from_wikitext(title: str, wikitext: str) -> Profile:
    """The name the profile computes with and its manual title fields, by kind."""
    add: dict[str, str] = {}
    remove: dict[str, str] = {}
    display_name = None
    for template in mwparserfromhell.parse(wikitext).filter_templates():
        if str(template.name).strip() != PROFILE_TEMPLATE:
            continue

        def field(name: str) -> str:
            return str(template.get(name).value).strip() if template.has(name) else ""

        display_name = field(DISPLAY_NAME_FIELD) or None
        for kind in KINDS:
            if field(f"הוספת זכיות {kind.field_suffix} כשחקן"):
                add[kind.key] = field(f"הוספת זכיות {kind.field_suffix} כשחקן")
            if field(f"הסרת זכיות {kind.field_suffix} כשחקן"):
                remove[kind.key] = field(f"הסרת זכיות {kind.field_suffix} כשחקן")
        break
    return Profile(title, display_name, add, remove)


def profiles(api: Api) -> list[Profile]:
    """Every page in the football profiles category, with its fields read from its text."""
    titles: list[str] = []
    continuation: dict[str, str] = {}
    while True:
        response = api(
            action="query", list="categorymembers", cmtitle=PROFILES_CATEGORY,
            cmnamespace=0, cmlimit=500, **continuation,
        )
        titles.extend(member["title"] for member in response["query"]["categorymembers"])
        if "continue" not in response:
            break
        continuation = {"cmcontinue": response["continue"]["cmcontinue"]}

    wikitext_by_title: dict[str, str] = {}
    for start in range(0, len(titles), _TITLES_PER_READ):
        response = api(
            action="query", prop="revisions", rvprop="content", rvslots="main",
            titles="|".join(titles[start:start + _TITLES_PER_READ]),
        )
        for page in response["query"]["pages"].values():
            wikitext_by_title[page["title"]] = page["revisions"][0]["slots"]["main"]["*"]
    return [profile_from_wikitext(title, wikitext_by_title[title]) for title in titles]


def _list_call(profile: Profile, kind: Kind) -> str:
    name = profile.display_name or f"{{{{PAGENAME:{profile.title}}}}}"
    return (
        f"{{{{{LIST_TEMPLATE} |זכיות להוספה={profile.add.get(kind.key, '')}"
        f" |זכיות להסרה={profile.remove.get(kind.key, '')} {kind.template_filter} |שם={name}}}}}"
    )


def live_lists(api: Api, batch: list[Profile]) -> dict[str, LiveLists]:
    """The six lists the live template gives each profile of the batch, in one request."""
    text = "\n".join(
        f"@@{profile_index}@@{kind_index}@@{_list_call(profile, kind)}"
        for profile_index, profile in enumerate(batch)
        for kind_index, kind in enumerate(KINDS)
    )
    expanded = api(action="expandtemplates", text=text, prop="wikitext")["expandtemplates"]["wikitext"]

    pieces = _CHUNK.split(expanded)
    outputs = {
        (int(pieces[index]), int(pieces[index + 1])): pieces[index + 2].strip()
        for index in range(1, len(pieces) - 2, 3)
    }

    result: dict[str, LiveLists] = {}
    for profile_index, profile in enumerate(batch):
        lists: dict[str, list[str]] = {}
        error = None
        for kind_index, kind in enumerate(KINDS):
            output = outputs.get((profile_index, kind_index))
            if output is None:
                error = f"no answer for the {kind.key} list"
                break
            seasons = [season.strip() for season in output.split(",")] if output else []
            if not all(_SEASON.fullmatch(season) for season in seasons):
                error = f"the {kind.key} list is not a list of seasons: {output[:_ERROR_SNIPPET_LIMIT]}"
                break
            lists[kind.key] = seasons
        result[profile.title] = LiveLists(lists, error)
    return result


def credit_lists(player_credits: Iterable[Credit], kinds: dict[str, set[str]]) -> dict[str, list[str]]:
    """The six lists one player's credits give: sorted, unique seasons per kind."""
    player_credits = list(player_credits)
    return {
        kind.key: sorted({credit.season for credit in player_credits if credit.competition in kinds[kind.key]})
        for kind in KINDS
    }


def run_gate(
    api: Api,
    profiles_to_check: list[Profile],
    credits: Iterable[Credit],
    kinds: dict[str, set[str]],
    *,
    credits_name_override: str | None = None,
) -> int:
    """Compare every profile. Returns 1 on any difference or unreadable live answer.

    `credits_name_override` is the self-test: every profile is compared with that
    player's credits instead of its own, which has to fail.
    """
    credits_by_player: dict[str, list[Credit]] = defaultdict(list)
    for credit in credits:
        credits_by_player[credit.player].append(credit)

    if not profiles_to_check:
        logger.error("Gate: no profile to compare - an empty list proves nothing")
        return 1

    equal = 0
    failed: list[str] = []
    for start in range(0, len(profiles_to_check), _PROFILES_PER_EXPANSION):
        batch = profiles_to_check[start:start + _PROFILES_PER_EXPANSION]
        live = live_lists(api, batch)
        for profile in batch:
            name = credits_name_override or profile.display_name or profile.title
            expected = credit_lists(credits_by_player.get(name, []), kinds)
            answer = live[profile.title]
            if answer.error:
                failed.append(profile.title)
                logger.error("%s: %s", profile.title, answer.error)
            elif answer.lists != expected:
                failed.append(profile.title)
                for kind in KINDS:
                    if answer.lists[kind.key] != expected[kind.key]:
                        logger.error(
                            "%s, %s: live %s, credits %s",
                            profile.title, kind.key, answer.lists[kind.key], expected[kind.key],
                        )
            else:
                equal += 1
        logger.info("compared %d/%d profiles, %d differ so far", min(start + len(batch), len(profiles_to_check)), len(profiles_to_check), len(failed))

    logger.info("Gate: %d profiles compared, %d equal, %d differ", len(profiles_to_check), equal, len(failed))
    return 1 if failed else 0
