"""Unit tests for the season manifest generator (stubbed Cargo fetcher)."""
from generate_season_manifest import collect_season_titles, expand_with_redirects

# Stub fetcher: maps (tables, where) → canned CargoExport rows, real-name fixtures.
_CANNED = {
    ("Football_Games", 'Season="2024/25"'): [
        {"_pageName": "משחק:31-08-2024 מכבי תל אביב נגד הפועל תל אביב - ליגת העל",
         "Opponent": "הפועל תל אביב", "Stadium": "אצטדיון בלומפילד",
         "CoachMaccabi": "ז'ארקו לאזטיץ'", "Competition": "ליגת העל",
         "Refs": "אוראל גרינפלד"},
        {"_pageName": "משחק:07-12-2024 מכבי תל אביב נגד מכבי חיפה - ליגת העל",
         "Opponent": "מכבי חיפה", "Stadium": "אצטדיון בלומפילד",
         "CoachMaccabi": "Cant found coach", "Competition": "ליגת העל",
         "Refs": "Cant found referee"},
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
    ("Profiles", '_pageName IN ("ערן זהבי","דור פרץ")'): [
        {"_pageName": "ערן זהבי", "ProfilePicture": "Eran Zahavi Profile.png"},
        {"_pageName": "דור פרץ", "ProfilePicture": ""},
    ],
    ("Basketball_Players", '_pageName IN ("כדורסל:טל ברודי")'): [
        {"_pageName": "כדורסל:טל ברודי", "ProfilePicture": "Tal Brody Profile.png"},
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
    assert "כדורגל:אוראל גרינפלד (שופט)" in titles   # referee page, prefixed+suffixed
    assert "מכבי תל אביב" in titles                  # the club page itself
    assert "Cant found referee" not in str(titles)
    assert "קובץ:Eran Zahavi Profile.png" in titles  # profile photo description page
    assert "קובץ:" not in titles                     # photo-less players add nothing


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


def test_expand_with_redirects_adds_targets_and_sources():
    def stub_api(params):
        assert params["action"] == "query"
        return {
            "query": {
                # ביתר ירושלים (quote-stripped Cargo value) IS a redirect.
                "redirects": [{"from": "ביתר ירושלים", "to": 'בית"ר ירושלים'}],
                "pages": {
                    "5986": {
                        "title": "מכבי תל אביב",
                        # short forms redirect TO the club page
                        "redirects": [{"title": 'מכבי ת"א'}, {"title": "מכבי תא"}],
                    },
                },
            },
        }

    titles = expand_with_redirects(["ביתר ירושלים", "מכבי תל אביב"], api=stub_api)

    assert 'בית"ר ירושלים' in titles      # redirect target added
    assert 'מכבי ת"א' in titles           # redirect source added
    assert titles[:2] == ["ביתר ירושלים", "מכבי תל אביב"]  # originals kept first
    assert len(titles) == len(set(titles))
