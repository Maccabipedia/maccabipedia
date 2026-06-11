"""Unit tests for the season manifest generator (stubbed Cargo fetcher)."""
from generate_season_manifest import collect_season_titles

# Stub fetcher: maps (tables, where) → canned CargoExport rows, real-name fixtures.
_CANNED = {
    ("Football_Games", 'Season="2024/25"'): [
        {"_pageName": "משחק:31-08-2024 מכבי תל אביב נגד הפועל תל אביב - ליגת העל",
         "Opponent": "הפועל תל אביב", "Stadium": "אצטדיון בלומפילד",
         "CoachMaccabi": "ז'ארקו לאזטיץ'", "Competition": "ליגת העל"},
        {"_pageName": "משחק:07-12-2024 מכבי תל אביב נגד מכבי חיפה - ליגת העל",
         "Opponent": "מכבי חיפה", "Stadium": "אצטדיון בלומפילד",
         "CoachMaccabi": "Cant found coach", "Competition": "ליגת העל"},
        # Cargo stores quotes HTML-entity-encoded (the wiki-wide &quot; quirk).
        {"_pageName": "משחק:03-02-2025 מכבי תל אביב נגד בית&quot;ר ירושלים - ליגת העל",
         "Opponent": "בית&quot;ר ירושלים", "Stadium": "אצטדיון בלומפילד",
         "CoachMaccabi": "ז'ארקו לאזטיץ'", "Competition": "ליגת העל"},
    ],
    ("Games_Events,Football_Games", 'Football_Games.Season="2024/25" AND Games_Events.Team=1'): [
        {"PlayerName": "ערן זהבי"},
        {"PlayerName": "דור פרץ"},
    ],
    ("Football_Uniforms", 'Season="2024/25"'): [
        {"_pageName": "מדי בית 2024/25"},
    ],
    ("Songs", 'PremiereSeason="2024/25"'): [
        {"_pageName": "שיר: קדימה מכבי"},
    ],
    ("Basketball_Games", 'Season="2023/24"'): [
        {"_pageName": "כדורסל:25-05-2024 מכבי תל אביב נגד הפועל חולון - ליגת העל",
         "Opponent": "הפועל חולון", "Stadium": "היכל מנורה מבטחים",
         "CoachMaccabi": "עודד קטש", "Competition": "ליגת העל"},
    ],
    ("Basketball_Player_Game_Events_Summary,Basketball_Games",
     'Basketball_Games.Season="2023/24" AND Basketball_Player_Game_Events_Summary.Team=1'): [
        {"PlayerName": "טל ברודי"},
    ],
    ("Basketball_Uniforms", 'Season="2023/24"'): [],
}


def stub_fetch(tables, fields, where, **kwargs):
    return _CANNED[(tables, where)]


def test_football_collects_all_page_kinds():
    titles = collect_season_titles("football", "2024/25", fetch=stub_fetch)
    assert "משחק:31-08-2024 מכבי תל אביב נגד הפועל תל אביב - ליגת העל" in titles
    assert "ערן זהבי" in titles
    assert "הפועל תל אביב" in titles          # main namespace, no prefix
    assert "אצטדיון בלומפילד" in titles
    assert "ליגת העל" in titles
    assert "עונת 2024/25" in titles
    assert "מדי בית 2024/25" in titles
    assert "שיר: קדימה מכבי" in titles
    assert "ז'ארקו לאזטיץ'" in titles


def test_basketball_titles_get_sport_prefix():
    titles = collect_season_titles("basketball", "2023/24", fetch=stub_fetch)
    assert "כדורסל:25-05-2024 מכבי תל אביב נגד הפועל חולון - ליגת העל" in titles
    assert "כדורסל:טל ברודי" in titles         # player prefixed
    assert "כדורסל:הפועל חולון" in titles      # opponent prefixed
    assert "כדורסל:ליגת העל" in titles         # competition prefixed
    assert "כדורסל:עונת 2023/24" in titles     # season page prefixed
    assert "כדורסל:היכל מנורה מבטחים" in titles
    assert "טל ברודי" not in titles            # no unprefixed leak
    assert "שיר: קדימה מכבי" not in titles     # songs are football/club-wide only


def test_filters_sentinels_and_dedupes():
    titles = collect_season_titles("football", "2024/25", fetch=stub_fetch)
    assert "Cant found coach" not in titles
    assert len(titles) == len(set(titles)), "duplicate titles in manifest"


def test_html_entities_unescaped_to_canonical_titles():
    titles = collect_season_titles("football", "2024/25", fetch=stub_fetch)
    assert 'בית"ר ירושלים' in titles
    assert 'משחק:03-02-2025 מכבי תל אביב נגד בית"ר ירושלים - ליגת העל' in titles
    assert not any("&quot;" in title for title in titles)
