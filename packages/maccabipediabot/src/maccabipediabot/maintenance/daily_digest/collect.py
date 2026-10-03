"""What happened on MaccabiPedia in a time window, compact enough to hand to a model.

Recent changes are hundreds of rows a day, most of them one bot run touching hundreds of
pages with the same edit comment. Grouping by (user, action, comment) turns such a run into
one row with a count, while a hand-made edit keeps its own row. Grouping by user alone would
not do: MaccabiBot is both the uploaders and the account sessions edit by hand with.
"""
from __future__ import annotations

import datetime
import json
import re
import subprocess
from collections.abc import Iterable
from urllib.parse import quote

WIKI_URL = "https://www.maccabipedia.co.il/"
GITHUB_REPO = "Maccabipedia/maccabipedia"
SAMPLE_TITLES_PER_GROUP = 8
MAX_GROUPS = 80
MAX_COMMENT_CHARS = 150

_GAME_TITLE = re.compile(r"^(משחק:|כדורסל:|כדורעף:)\d{2}-\d{2}-\d{4} ")
_SPORT_BY_PREFIX = {"משחק:": "football", "כדורסל:": "basketball", "כדורעף:": "volleyball"}


def page_url(title: str) -> str:
    return WIKI_URL + quote(title.replace(" ", "_"), safe=":/()")


def _action(change: dict) -> str:
    if change["type"] == "log":
        return f"{change.get('logtype')}/{change.get('logaction')}"
    return change["type"]


def _label(change: dict) -> str:
    """The title, plus where it went for a move."""
    target = (change.get("logparams") or {}).get("target_title")
    return f"{change['title']} → {target}" if target else change["title"]


def group_changes(changes: Iterable[dict]) -> list[dict]:
    """One row per (user, action, comment), largest first."""
    groups: dict[tuple, dict] = {}
    for change in changes:
        user = change.get("user", "?")
        comment = (change.get("comment") or "").strip()[:MAX_COMMENT_CHARS]
        key = (user, _action(change), comment)
        group = groups.setdefault(key, {"user": user, "action": key[1], "comment": comment,
                                        "bot_flag": False, "count": 0, "sample_titles": []})
        group["count"] += 1
        group["bot_flag"] = group["bot_flag"] or bool(change.get("bot"))
        label = _label(change)
        if len(group["sample_titles"]) < SAMPLE_TITLES_PER_GROUP and label not in group["sample_titles"]:
            group["sample_titles"].append(label)
    return sorted(groups.values(), key=lambda group: -group["count"])[:MAX_GROUPS]


def new_game_pages(changes: Iterable[dict]) -> list[dict]:
    """Game pages created in the window, every one of them, in creation order."""
    games = []
    for change in changes:
        match = _GAME_TITLE.match(change["title"])
        if change["type"] == "new" and match:
            games.append({"sport": _SPORT_BY_PREFIX[match.group(1)], "title": change["title"],
                          "user": change.get("user", "?"), "comment": (change.get("comment") or "")[:MAX_COMMENT_CHARS]})
    return games


def fetch_changes(site, since: datetime.datetime, until: datetime.datetime) -> list[dict]:
    """Every recent change in [since, until): edits, page creations and all log types.

    MediaWiki includes both ends, so the end stops a second short of ``until``, which is where
    the next window starts.
    """
    return list(site.recentchanges(start=since, end=until - datetime.timedelta(seconds=1), reverse=True))


def _github_stamp(moment: datetime.datetime) -> str:
    return moment.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_merged_prs(since: datetime.datetime, until: datetime.datetime) -> list[dict]:
    """PRs merged into the bot repo in [since, until), from the gh CLI.

    The repo is named explicitly: GitHub search does not follow a rename, and a clone whose
    origin still has the old name gets an empty list with exit code 0.
    """
    last_second = until - datetime.timedelta(seconds=1)
    output = subprocess.run(
        ["gh", "pr", "list", "--repo", GITHUB_REPO, "--state", "merged",
         "--search", f"merged:{_github_stamp(since)}..{_github_stamp(last_second)}",
         "--json", "number,title,url,mergedAt", "--limit", "50"],
        check=True, capture_output=True, text=True, timeout=120).stdout
    return sorted(json.loads(output), key=lambda pr: pr["mergedAt"])


def build_activity(changes: list[dict], merged_prs: list[dict],
                   since: datetime.datetime, until: datetime.datetime) -> dict:
    return {
        "window": {"since": since.isoformat(), "until": until.isoformat()},
        "total_changes": len(changes),
        "new_games": new_game_pages(changes),
        "change_groups": group_changes(changes),
        "merged_prs": merged_prs,
    }


def link_targets(activity: dict) -> set[str]:
    """Every wiki title the digest may link to: the ones the data actually names."""
    titles = {game["title"] for game in activity["new_games"]}
    users = {game["user"] for game in activity["new_games"]}
    for group in activity["change_groups"]:
        users.add(group["user"])
        for label in group["sample_titles"]:
            titles.update(part.strip() for part in label.split(" → "))
    for user in users:
        titles.update(user_pages(user))
    return titles


def user_pages(user: str) -> tuple[str, str]:
    """The user's page and their contributions list, the two links a name can carry."""
    return f"משתמש:{user}", f"מיוחד:תרומות/{user}"


def link_urls(activity: dict) -> set[str]:
    """Every non-wiki URL the digest may show: the merged PRs."""
    return {pr["url"] for pr in activity["merged_prs"]}
