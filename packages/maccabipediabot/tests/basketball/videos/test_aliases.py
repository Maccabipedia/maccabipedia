"""Tests for turning a video title's opponent name into something comparable to Cargo.

The opponent names stored in Basketball_Games vary by era for the same club
("ראשון לציון" / "מכבי ראשון לציון" / 'ראשל"צ', "מילאנו" / "ארמאני מילאנו"), so
comparison is deliberately tolerant rather than exact.
"""
import pytest

from maccabipediabot.basketball.videos.aliases import (
    normalize_team_name,
    opponent_matches,
    resolve_opponent,
)


@pytest.mark.parametrize("raw,expected", [
    ('הפועל ת"א', "הפועל תל אביב"),
    ("הפועל  ירושלים ", "הפועל ירושלים"),
    ("Maccabi Playtika Tel Aviv", "Maccabi Tel Aviv"),
    ('צסק"א מוסקבה', "צסקא מוסקבה"),
])
def test_normalize_team_name(raw, expected):
    assert normalize_team_name(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("Hapoel Jerusalem", "הפועל ירושלים"),          # via the existing EN->HE map
    # Video-title aliases resolve to the DISTINCTIVE part of the name, because Cargo
    # spells this club both "אליצור נתניה" and "אליצור עירוני נתניה".
    ("Elitzur Netanya", "נתניה"),
    ("Panathinaikos", "פנאתינייקוס"),
    ("Zalgiris Kaunas", "ז'לגיריס קובנה"),
    ("אליצור נתניה", "אליצור נתניה"),               # Hebrew titles pass through
    ("מילאנו", "מילאנו"),
    ("No Such Club FC", None),                       # unknown English stays unknown
])
def test_resolve_opponent(raw, expected):
    assert resolve_opponent(raw) == expected


@pytest.mark.parametrize("title_name,cargo_opponent", [
    # Straight hits.
    ("אליצור נתניה", "אליצור נתניה"),
    ("Hapoel Jerusalem", "הפועל ירושלים"),
    # The club renamed itself, or Cargo carries a sponsor the title drops.
    ("מילאנו", "ארמאני מילאנו"),
    ("מילאנו", "אולימפיה מילאנו"),
    ("פנרבחצ'ה", "פנרבחצ'ה אולקר"),
    ("Elitzur Netanya", "אליצור נתניה"),
    ("נהריה", "עירוני נהריה"),
    # Abbreviations and quote marks.
    ('הפועל ת"א', "הפועל תל אביב"),
    ("צסקא מוסקבה", 'צסק"א מוסקבה'),
    # The channel's spelling of a club Cargo stores canonically.
    ("פנאתינייקוס", "פנאתינייקוס"),
])
def test_opponent_matches_across_era_spellings(title_name, cargo_opponent):
    assert opponent_matches(title_name, cargo_opponent) is True


@pytest.mark.parametrize("title_name,cargo_opponent", [
    ("הפועל ירושלים", "הפועל תל אביב"),
    ("מכבי חיפה", "הפועל חיפה"),
    ("ברצלונה", "ריאל מדריד"),
    ("מכבי ראשון לציון", "מכבי רמת גן"),
])
def test_opponent_does_not_match_a_different_club(title_name, cargo_opponent):
    assert opponent_matches(title_name, cargo_opponent) is False


@pytest.mark.parametrize("typo", [
    "DInamo Sassari",      # stray capital
    "Crvena zvezda",       # lower case
    "UNICS Kazan",         # all caps
    "Hapoel Gilboa-Galil",  # hyphen instead of a slash
    "Zenit St. Petersburg",  # abbreviation dot
    "Asvel",
])
def test_channel_typos_and_case_still_resolve(typo):
    """The channels are inconsistent about case and punctuation; none of that should
    cost a match."""
    assert resolve_opponent(typo) is not None


def test_unknown_opponent_never_claims_a_match():
    assert resolve_opponent("No Such Club FC") is None
    assert opponent_matches("No Such Club FC", "הפועל תל אביב") is False


@pytest.mark.parametrize("title_name,cargo_opponent", [
    # A hyphen joins the halves of one club name the way a space does.
    ("וילרבאן", "ליון-וילרבאן"),
    ("לה מאן", "לה-מאן"),
    # The same club spelled differently by the title and by the page.
    ("מלאגה", "מלאגה"),
    ("אפס פלזן", "אפס פילזן"),
    ("איראקליס", "היראקליס סלוניקי"),
    ("בנטון טרויזו", "בנטון טרביזו"),
    ("חובנטוד דאלונה", "חובנטוד בדאלונה"),
    ("אוסטנד", "אוסטנדה"),
    # Abbreviations the channel uses and the pages spell out.
    ("מכבי ראשון לציון", 'ראשל"צ'),
    ('בנה"ש', "בני השרון"),
    # 1980s sponsors and appended city names in the English archive uploads.
    ("Tracer Milano", "אולימפיה מילאנו"),
    ("Nashua Den Bosch", "דן בוס"),
    ("Squibb Cantù", "קאנטו"),
    ("Aris Thessaloniki", "אריס סלוניקי"),
    ("Synudine Bologna", "וירטוס בולוניה"),
    ("Union Olimpija", "אולימפיה לובליאנה"),
    ("Upper Galil", "גליל עליון"),
    ("טאלין", "קאלב"),
])
def test_era_spellings_of_one_club_match(title_name, cargo_opponent):
    """Each of these pairs names a single club and cost a real match before the fold."""
    assert opponent_matches(title_name, cargo_opponent) is True


def test_hebrew_name_is_not_rewritten_away_from_the_wiki():
    """Translating 'מלאגה' to 'מאלגה' moved the name off the spelling the pages use."""
    assert resolve_opponent("מלאגה") == "מלאגה"


def test_canonical_rename_does_not_break_a_live_cargo_spelling():
    """canonical_team_name() maps 'פנאתינייקוס' to 'פנאתינאיקוס', but Cargo stores the
    former on 58 rows. Matching must accept the spelling that is actually on the wiki."""
    assert opponent_matches("Panathinaikos AKTOR Athens", "פנאתינייקוס") is True
