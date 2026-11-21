"""Which players are credited with which title. The only place the rule exists.

A rule is a pure function of the Cargo exports, so the same code writes a new title's
lines, lists what a rule change would do, and feeds the proposals.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import NamedTuple


class Title(NamedTuple):
    """One competition Maccabi won in one season."""
    season: str
    competition: str


class Credit(NamedTuple):
    """One row of Football_Player_Titles: this player is credited with this title."""
    player: str
    season: str
    competition: str


class SeasonPlayed(NamedTuple):
    """A player has at least one Maccabi game-sheet row in a season."""
    player: str
    season: str


def todays_rule(
    titles: Iterable[Title], seasons_played: Iterable[SeasonPlayed]
) -> dict[Title, list[str]]:
    """What the profile template computes today: everyone on any Maccabi game sheet in a
    season is credited with every competition won that season."""
    players_by_season: dict[str, set[str]] = defaultdict(set)
    for played in seasons_played:
        players_by_season[played.season].add(played.player)

    return {title: sorted(players_by_season[title.season]) for title in titles}


# The rule the job runs. A rule change is a change of this constant, made only after a
# maintainer approved the list of credits it adds and removes.
RULE = todays_rule
