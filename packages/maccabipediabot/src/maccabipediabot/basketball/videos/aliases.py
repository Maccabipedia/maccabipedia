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

from maccabipediabot.basketball.translations import video_title_team_to_hebrew

# Sponsor names the club or its opponents have carried; noise inside a team name.
_SPONSOR_TOKENS = frozenset({
    "rapyd", "playtika", "fox", "electra", "elite", "tsm", "unet", "יונט",
    "aktor", "meridianbet", "beko", "olkер", "olker", "ibi", "sp", "hunter",
})

# Words that appear or vanish between eras without changing which club is meant.
_OPTIONAL_WORDS = frozenset({
    "עירוני", "מ.כ", "בי.סי", "bc", "basket", "basketball", "bv", "sk",
    # Union Olimpija Ljubljana is written both with and without the "Union": the pages
    # hold "אוניון אולימפיה" and the titles "אולימפיה לובליאנה".
    "אוניון",
})

_ABBREVIATIONS = (
    ('ת"א', "תל אביב"),
    ("ת״א", "תל אביב"),
    ('ר"ג', "רמת גן"),
    ('פ"ת', "פתח תקווה"),
    ('י"ם', "ירושלים"),
    ("י-ם", "ירושלים"),
    ('ראשל"צ', "ראשון לציון"),
    ("ראשל״צ", "ראשון לציון"),
    ('בנה"ש', "בני השרון"),
    ("בנה״ש", "בני השרון"),
)

_QUOTE_CHARS = str.maketrans("", "", "\"'`״׳")

# Hebrew spellings that differ between eras or between editors for the same club. Both
# sides of the comparison are folded through this, so the pair only has to agree on one
# spelling — which spelling wins does not matter.
_HEBREW_SPELLING_VARIANTS = {
    "קריית": "קרית",
    "מונאקו": "מונקו",
    "באסקוניה": "בסקוניה",
    "ז'אלגריס": "ז'לגיריס",
    "מאלגה": "מלאגה",
    "ארמאני": "ארמני",
    "אוסטנדה": "אוסטנד",
    "פילזן": "פלזן",
    "טרויזו": "טרביזו",
    "טרוויזו": "טרביזו",
    "היראקליס": "איראקליס",
    "בדאלונה": "דאלונה",
    "סארייבו": "סרייבו",
    "סקאבוליני": "סקבוליני",
}


def normalize_team_name(name: str) -> str:
    """Expand abbreviations, drop sponsor words and quote marks, collapse whitespace."""
    text = html.unescape(name)
    for abbreviation, expansion in _ABBREVIATIONS:
        text = text.replace(abbreviation, expansion)
    # A hyphen joins two halves of one name as often as a space does — "ליון-וילרבאן",
    # "לה-מאן", "גלבוע/עפולה" — so both it and the slash become word breaks.
    text = text.translate(_QUOTE_CHARS).replace("/", " ").replace("-", " ")
    words = [
        _HEBREW_SPELLING_VARIANTS.get(word, word)
        for word in text.split()
        if word.lower() not in _SPONSOR_TOKENS
    ]
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
    # The map's keys carry their own sponsor words ("EA7 Emporio Armani Milan"), which
    # normalization strips, so try the untouched spelling as well.
    for candidate in (name, html.unescape(opponent_raw).strip()):
        translated = video_title_team_to_hebrew(candidate)
        if translated is not None:
            return translated
    if re.search(r"[֐-׿]", name):
        return name  # already Hebrew: the tolerant comparison below absorbs spellings
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
