"""Compare an opponent name from a video title with the one stored in Basketball_Games.

Two problems make an exact string comparison useless here:

* The channel writes names its own way, in Hebrew or English, with the club's current
  sponsor embedded ("Maccabi Playtika Tel Aviv", 'הפועל ת"א').
* Cargo's own opponent names vary by era for the same club — "ראשון לציון",
  "מכבי ראשון לציון" and 'ראשל"צ' are all the same team, as are "מילאנו",
  "ארמאני מילאנו" and "אולימפיה מילאנו".

So a title name is resolved to Hebrew where possible and then compared TOLERANTLY: one
name matches the other when their significant words are the same, or when one club's
words are wholly contained in the other's (a sponsor or a "עירוני" prefix being the
usual difference). The opponent is only ever a CONFIRMATION of a match already made on
the score, never the thing that picks a game on its own, so this tolerance cannot pull
in an unrelated game — at worst it leaves an ambiguity for a human to settle.

Deliberately NOT used here: translations.canonical_team_name(). It rewrites names
towards the canonical spelling used when uploading new games ("פנאתינייקוס" becomes
"פנאתינאיקוס"), but the pages we are matching against hold the older spelling — 58
rows say "פנאתינייקוס". Canonicalising would move the name away from the wiki.
"""
import html
import re

from maccabipediabot.basketball.translations import team_name_to_hebrew

# Sponsor names the club or its opponents have carried; noise inside a team name.
_SPONSOR_TOKENS = frozenset({
    "rapyd", "playtika", "fox", "electra", "elite", "tsm", "unet", "יונט",
    "aktor", "meridianbet", "beko", "olkер", "olker", "ibi", "sp", "hunter",
})

# Words that appear or vanish between eras without changing which club is meant.
_OPTIONAL_WORDS = frozenset({
    "עירוני", "מ.כ", "בי.סי", "bc", "basket", "basketball", "bv", "sk",
})

_ABBREVIATIONS = (
    ('ת"א', "תל אביב"),
    ("ת״א", "תל אביב"),
    ('ר"ג', "רמת גן"),
    ('פ"ת', "פתח תקווה"),
    ('י"ם', "ירושלים"),
    ("י-ם", "ירושלים"),
)

_QUOTE_CHARS = str.maketrans("", "", "\"'`״׳")


def normalize_team_name(name: str) -> str:
    """Expand abbreviations, drop sponsor words and quote marks, collapse whitespace."""
    text = html.unescape(name)
    for abbreviation, expansion in _ABBREVIATIONS:
        text = text.replace(abbreviation, expansion)
    text = text.translate(_QUOTE_CHARS)
    words = [word for word in text.split() if word.lower() not in _SPONSOR_TOKENS]
    return re.sub(r"\s+", " ", " ".join(words)).strip()


def _significant_words(name: str) -> frozenset[str]:
    return frozenset(
        word for word in normalize_team_name(name).lower().split()
        if word not in _OPTIONAL_WORDS
    )


def resolve_opponent(opponent_raw: str) -> str | None:
    """The Hebrew club name a title's opponent refers to, or None when it can't be told.

    Hebrew input passes through: the channel writes the club's ordinary Hebrew name, and
    the tolerant comparison below absorbs the spelling differences. English input must
    be in the translations map, otherwise we would be guessing.
    """
    name = normalize_team_name(opponent_raw)
    if not name:
        return None
    translated = team_name_to_hebrew(name)
    if translated != name:
        return translated
    if re.search(r"[֐-׿]", name):
        return name
    # Try the untouched spelling too: the map's keys carry their own sponsor words
    # ("EA7 Emporio Armani Milan"), which normalization may have stripped.
    original = html.unescape(opponent_raw).strip()
    translated_original = team_name_to_hebrew(original)
    if translated_original != original:
        return translated_original
    return None


def opponent_matches(opponent_raw: str, cargo_opponent: str) -> bool:
    """True when a title's opponent and a Cargo row's opponent are the same club."""
    resolved = resolve_opponent(opponent_raw)
    if resolved is None or not cargo_opponent:
        return False
    title_words = _significant_words(resolved)
    cargo_words = _significant_words(cargo_opponent)
    if not title_words or not cargo_words:
        return False
    return title_words <= cargo_words or cargo_words <= title_words
