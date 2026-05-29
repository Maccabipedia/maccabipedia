"""Tests for the basketball translations module."""
from datetime import datetime

import pytest

from maccabipediabot.basketball.translations import (
    basket_co_il_competition_name,
    canonical_team_name,
    normalize_player_name,
    person_name_to_hebrew,
    stadium_name_to_hebrew,
    team_name_to_hebrew,
)


def test_lookup_functions_resolve_known_keys_and_pass_through_unknowns():
    """Sanity: every lookup function maps a known key and passes unknowns through.
    Includes a few previously-trailing-space TS keys (cleaned at source) as a guard
    against the kind of regression that used to require runtime whitespace tolerance."""
    # team
    assert team_name_to_hebrew("Maccabi Tel-Aviv") == "מכבי תל אביב"
    assert team_name_to_hebrew("Unknown Team") == "Unknown Team"
    # person — including former trailing-space keys
    assert person_name_to_hebrew("Wade Baldwin Iv") == "ווייד בולדווין"
    assert person_name_to_hebrew("Sergio Llull") == "סרחיו יוי"   # source had trailing space
    assert person_name_to_hebrew("Andres Feliz") == "אנדרס פליס"
    assert person_name_to_hebrew("Unknown Coach") == "Unknown Coach"
    # stadium
    assert stadium_name_to_hebrew("MENORA MIVTACHIM ARENA") == "היכל מנורה מבטחים"
    assert stadium_name_to_hebrew("Unknown Arena") == "Unknown Arena"


def test_normalize_player_name_strips_trailing_junior_suffix():
    """basket.co.il includes 'ג'וניור' in player names (Jeff Dowtin Jr, Derrick Alston Jr);
    wiki convention drops it. Generic stripper avoids needing per-player map entries."""
    assert normalize_player_name("ג'ף דאוטין ג'וניור") == "ג'ף דאוטין"
    assert normalize_player_name("דריק אלסטון ג'וניור") == "דריק אלסטון"
    assert normalize_player_name("ג'וניור ישראלי") == "ג'וניור ישראלי"  # not a suffix
    assert normalize_player_name("טל ברודי") == "טל ברודי"  # unknown passes through


@pytest.mark.parametrize("code, expected", [
    (5, "ליגת העל"),
    (34, "הסופרקאפ הישראלי"),
    (999, None),
])
def test_basket_co_il_competition_name(code, expected):
    assert basket_co_il_competition_name(code) == expected


@pytest.mark.parametrize("name, year, expected", [
    ("מכבי אלקטרה", 2010, "מכבי תל אביב"),                     # always-on rule
    ("הפועל ירושלים", 2024, "הפועל ירושלים"),                   # not in registry → pass through
    ("שם לא ידוע", 2024, "שם לא ידוע"),                         # unknown → pass through
    ("מכבי רמת עמידר", 2000, "מכבי רמת עמידר"),                 # year-bounded, pre-2005
    ("מכבי רמת עמידר", 2010, "הכח עמידר רמת גן"),               # year-bounded, post-2005
])
def test_canonical_team_name(name, year, expected):
    assert canonical_team_name(name, datetime(year, 6, 1)) == expected
