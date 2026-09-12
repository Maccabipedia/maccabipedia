"""Tests for the season window the scheduled run uses.

The window is always TWO seasons wide, never just the latest: a club video can appear
days after the game, and at the turn of a season the previous one is still being
filled in. See the "latest season rollover" trap that has bitten other bots here.
"""
from datetime import date

import pytest

from maccabipediabot.basketball.videosbot_basketball import (
    current_and_previous_seasons,
    resolve_seasons,
    season_label,
)


@pytest.mark.parametrize("today,expected", [
    (date(2026, 2, 3), ["2024/25", "2025/26"]),    # mid-season
    (date(2026, 8, 5), ["2025/26", "2026/27"]),    # just after the rollover
    (date(2026, 7, 30), ["2024/25", "2025/26"]),   # just before it
    (date(2000, 9, 1), ["1999/00", "2000/01"]),    # across the century
    (date(1999, 12, 31), ["1998/99", "1999/00"]),
])
def test_season_window(today, expected):
    assert current_and_previous_seasons(today) == expected


@pytest.mark.parametrize("start_year,expected", [
    (2025, "2025/26"),
    (1999, "1999/00"),
    (2009, "2009/10"),
])
def test_season_label(start_year, expected):
    assert season_label(start_year) == expected


def test_resolve_seasons_all_means_every_season():
    assert resolve_seasons("all") is None


def test_resolve_seasons_reads_the_window():
    assert resolve_seasons("current,previous", today=date(2026, 2, 3)) == ["2024/25", "2025/26"]


def test_resolve_seasons_reads_an_explicit_list():
    assert resolve_seasons("2024/25, 2019/20") == ["2024/25", "2019/20"]
