"""Tests for parsing official-channel video titles into a game key.

Every title here is real, taken from the channel's own listing. The channel writes
the home team first and embeds the current sponsor name ("Rapyd", "Playtika", "FOX",
"Electra"), so which side is Maccabi has to be decided by name, never by position.

SCORE ORDER: Hebrew titles are written right to left, so the first team named takes
the SECOND number, while English titles pair them in reading order. The scores below
for the 2026 league finals are checked against Basketball_Games:

    game 1 (16-06-2026) Maccabi 96 Hapoel 75
    game 3 (21-06-2026) Maccabi 74 Hapoel 80
    game 4 (23-06-2026) Maccabi 83 Hapoel 79

and the channel's own Hebrew and English titles for game 3 carry the digits in
opposite order, which is what fixes the rule.
"""
import pytest

from maccabipediabot.basketball.videos.title_parser import VideoKind, parse_game_video_title


@pytest.mark.parametrize("title,kind,opponent,maccabi,opponent_points,language", [
    ('תקציר המשחק: מכבי Rapyd ת"א - אליצור נתניה 92:102', VideoKind.HIGHLIGHTS, "אליצור נתניה", 102, 92, "he"),
    ("תקציר: הפועל אילת - מכבי Playtika תל אביב 85:70 (ליגת העל, מחזור 18)",
     VideoKind.HIGHLIGHTS, "הפועל אילת", 85, 70, "he"),
    # Verified: game 1 of the 2026 finals, Maccabi 96 Hapoel 75.
    ('תקציר: מכבי Rapyd ת"א - הפועל ת"א 75:96 (גמר פלייאוף 1)',
     VideoKind.HIGHLIGHTS, 'הפועל ת"א', 96, 75, "he"),
    ("Highlights: Maccabi FOX Tel Aviv - Maccabi Haifa 67:59",
     VideoKind.HIGHLIGHTS, "Maccabi Haifa", 67, 59, "en"),
    ("Highlights: Hapoel Jerusalem - Maccabi FOX TelAviv 74:63",
     VideoKind.HIGHLIGHTS, "Hapoel Jerusalem", 63, 74, "en"),
    ("Highlights: Gilboa/Galil vs Maccabi Playtika Tel Aviv 60:77 | תקציר: גלבוע/גליל נגד מכבי",
     VideoKind.HIGHLIGHTS, "Gilboa/Galil", 77, 60, "en"),
    ("Highlights: Maccabi Playtika Tel Aviv vs Real Madrid 75:74 | תקציר הניצחון של מכבי על ריאל מדריד",
     VideoKind.HIGHLIGHTS, "Real Madrid", 75, 74, "en"),
    ('המשחק המלא: מכבי Rapyd ת"א - באיירן מינכן 106:111',
     VideoKind.FULL_GAME, "באיירן מינכן", 111, 106, "he"),
    ("Full Game: Barcelona - Maccabi Electra Tel Aviv 89:71",
     VideoKind.FULL_GAME, "Barcelona", 71, 89, "en"),
    ("Highlights: Maccabi Electra Tel-Aviv - Maccabi Rishon Lezion 79:58",
     VideoKind.HIGHLIGHTS, "Maccabi Rishon Lezion", 79, 58, "en"),
    # Verified: game 3 of the 2026 finals, Maccabi 74 Hapoel 80.
    ('תרכיז המשחק: מכבי Rapyd ת"א - הפועל ת"א 80:74', VideoKind.CONDENSED, 'הפועל ת"א', 74, 80, "he"),
    ("Game Highlights: Maccabi Rapyd Tel Aviv vs. Hapoel Tel Aviv 74:80 (Playoff Finals Game 3)",
     VideoKind.HIGHLIGHTS, "Hapoel Tel Aviv", 74, 80, "en"),
    # Verified: game 4 of the 2026 finals, Maccabi 83 Hapoel 79.
    ('תרכיז משחק האליפות: הפועל ת"א - מכבי Rapyd ת"א 83:79', VideoKind.CONDENSED, 'הפועל ת"א', 83, 79, "he"),
    ('תקציר משחק האליפות: הפועל ת"א - מכבי Rapyd ת"א 83:79 (גמר פלייאוף משחק 4)',
     VideoKind.HIGHLIGHTS, 'הפועל ת"א', 83, 79, "he"),
    ("Championship Game Highlights: Hapoel Tel Aviv - Maccabi Rapyd Tel Aviv 79:83",
     VideoKind.HIGHLIGHTS, "Hapoel Tel Aviv", 83, 79, "en"),
])
def test_parses_game_titles(title, kind, opponent, maccabi, opponent_points, language):
    parsed = parse_game_video_title(title)
    assert parsed is not None, f"expected a parse for: {title}"
    assert parsed.kind == kind
    assert parsed.opponent_raw == opponent
    assert (parsed.maccabi_points, parsed.opponent_points) == (maccabi, opponent_points)
    assert parsed.language == language


@pytest.mark.parametrize("title,kind,opponent,maccabi,opponent_points", [
    # English variants of the highlights prefix.
    ("Game Highlights: Maccabi Rapyd Tel Aviv vs. Hapoel Tel Aviv 80:74",
     VideoKind.HIGHLIGHTS, "Hapoel Tel Aviv", 80, 74),
    ("Match Highlights: Hapoel HaEmek - Maccabi Rapyd Tel Aviv 98:88",
     VideoKind.HIGHLIGHTS, "Hapoel HaEmek", 88, 98),
    ("Championship Game Highlights: Hapoel Tel Aviv - Maccabi Rapyd Tel Aviv 79:83",
     VideoKind.HIGHLIGHTS, "Hapoel Tel Aviv", 83, 79),
    # A qualifier between the keyword and the colon.
    ('המשחק המלא (חצי גמר פלייאוף משחק 1): מכבי Rapyd ת"א - הפועל חולון 93:107',
     VideoKind.FULL_GAME, "הפועל חולון", 107, 93),
    ('המשחק המלא, גמר גביע המדינה 2025/26: מכבי Rapyd ת"א - בני הרצליה 90:109',
     VideoKind.FULL_GAME, "בני הרצליה", 109, 90),
    ('תקציר מחזור 8 יורוליג: מכבי Rapyd ת"א - הכוכב האדום 99:92',
     VideoKind.HIGHLIGHTS, "הכוכב האדום", 92, 99),
    ('תקציר גמר גביע המדינה: מכבי Playtika תל אביב - הפועל ירושלים 72:87',
     VideoKind.HIGHLIGHTS, "הפועל ירושלים", 87, 72),
    # A pipe where the colon usually goes.
    ('תרכיז המשחק | מכבי Rapyd ת"א - הכוכב האדום 99:92',
     VideoKind.CONDENSED, "הכוכב האדום", 92, 99),
    ('תרכיז המשחק | פנאתינייקוס - מכבי Rapyd ת"א 85:99',
     VideoKind.CONDENSED, "פנאתינייקוס", 85, 99),
    # The keyword trailing the title instead of leading it.
    ('מכבי Rapyd ת"א - ריאל מדריד 91:92 המשחק המלא',
     VideoKind.FULL_GAME, "ריאל מדריד", 92, 91),
    # "מול" used as the separator instead of a dash.
    ("תקציר: הפועל חולון מול מכבי Playtika תל אביב 76:82 (ליגת העל, מחזור 27)",
     VideoKind.HIGHLIGHTS, "הפועל חולון", 76, 82),
    ("תקציר: מכבי Playtika תל אביב מול פנאתינייקוס 95:88 (פלייאוף היורוליג, משחק מספר 4)",
     VideoKind.HIGHLIGHTS, "פנאתינייקוס", 88, 95),
    # The English name for a תרכיז.
    ("Condensed Game: Valencia Basket - Maccabi Playtika Tel Aviv 93:94 | התרכיז: ולנסיה מול מכבי",
     VideoKind.CONDENSED, "Valencia Basket", 94, 93),
    ("Condensed Game: Kiryat Ata vs Maccabi Playtika Tel Aviv 88:100 | התרכיז: קרית אתא מול מכבי",
     VideoKind.CONDENSED, "Kiryat Ata", 100, 88),
    ("Condensed game: Maccabi - Barcelona 85:68 | תקציר 10 דקות: מכבי נגד ברצלונה",
     VideoKind.CONDENSED, "Barcelona", 85, 68),
    # EuroLeague-era titles name the club as a bare "Maccabi", with no Tel Aviv token.
    ("Highlights: Brose Bamberg - Maccabi 90:75", VideoKind.HIGHLIGHTS, "Brose Bamberg", 75, 90),
    ("Highlights: Galatasaray - Maccabi 102:63", VideoKind.HIGHLIGHTS, "Galatasaray", 63, 102),
    ("Highlights:  Maccabi - CSKA Moscow 76:80", VideoKind.HIGHLIGHTS, "CSKA Moscow", 76, 80),
    # "at" marks the away side.
    ("Highlights: Maccabi Playtika Tel Aviv at Milano 72:83", VideoKind.HIGHLIGHTS, "Milano", 72, 83),
])
def test_parses_alternate_title_shapes(title, kind, opponent, maccabi, opponent_points):
    parsed = parse_game_video_title(title)
    assert parsed is not None, f"expected a parse for: {title}"
    assert parsed.kind == kind
    assert parsed.opponent_raw == opponent
    assert (parsed.maccabi_points, parsed.opponent_points) == (maccabi, opponent_points)


@pytest.mark.parametrize("title", [
    "Highlights: Partizan Belgrade - Maccabi Rapyd Tel Aviv 96:103 (Preseason)",
    "Full Game: Partizan Belgrade vs Maccabi Rapyd Tel Aviv 96:103 (Preseason)",
    "Highlights: Anadolu Efes vs. Maccabi Playtika Tel Aviv 89:66 (Preseason Game)",
    "תקציר: פנאתינייקוס - מכבי Playtika תל אביב 81:73 (משחק הכנה)",
    'תקציר משחק אימון: מכבי Rapyd ת"א - הפועל ירושלים 87:80',
    "Highlights: Maccabi vs. Herzliya 87:100 | תקציר משחק אימון: מכבי מול בני הרצליה",
    "Condensed Game: Maccabi Playtika Tel Aviv vs Fenerbahce 82:78 (Preseason) | תרכיז: מכבי נגד פנרבחצ'ה",
])
def test_rejects_friendlies_and_training_games(title):
    """These have two teams and a score but no Cargo row, so a match would be a false one."""
    assert parse_game_video_title(title) is None


def test_player_compilation_with_a_game_score_is_still_rejected():
    """The score belongs to the game, but the video is one player's plays."""
    assert parse_game_video_title(
        "Gorlavie Highlights (31 Points) - Maccabi Rapyd Tel Aviv vs. Ironi Ness Ziona 111:80"
    ) is None


@pytest.mark.parametrize("title,opponent,maccabi,opponent_points", [
    ("Highlights: Maccabi Rapyd Tel Aviv - Maccabi Rishon LeZion 86:81", "Maccabi Rishon LeZion", 86, 81),
    ("Highlights: Maccabi FOX Tel Aviv - Maccabi Haifa 67:59", "Maccabi Haifa", 67, 59),
    ("Game Highlights: Maccabi Rapyd Tel Aviv vs. Maccabi Ra'anana 95:75", "Maccabi Ra'anana", 95, 75),
])
def test_another_maccabi_club_is_not_mistaken_for_maccabi_tel_aviv(title, opponent, maccabi, opponent_points):
    """Several opponents are themselves named Maccabi, so a bare-Maccabi rule must not
    swallow them: only a side that is Maccabi ALONE (sponsor tokens aside) is the club."""
    parsed = parse_game_video_title(title)
    assert parsed is not None
    assert parsed.opponent_raw == opponent
    assert (parsed.maccabi_points, parsed.opponent_points) == (maccabi, opponent_points)


def test_bare_maccabi_on_both_sides_is_refused_rather_than_guessed():
    assert parse_game_video_title("Highlights: Maccabi - Maccabi 80:70") is None


@pytest.mark.parametrize("title,kind,opponent,maccabi,opponent_points", [
    # "Summary" is the channel's other word for a highlights video.
    ("Game summary: Maccabi Rapyd Tel Aviv - Hapoel Holon 61:89 (playoff semi-final game 3)",
     VideoKind.HIGHLIGHTS, "Hapoel Holon", 61, 89),
    ("Summary: Maccabi Rapyd Tel Aviv - Elitzur Netanya 88:94",
     VideoKind.HIGHLIGHTS, "Elitzur Netanya", 88, 94),
    ("Derby Summary: Hapoel Tel Aviv - Maccabi Rapyd Tel Aviv 80:85",
     VideoKind.HIGHLIGHTS, "Hapoel Tel Aviv", 85, 80),
    ("Full game: Maccabi Rapyd Tel Aviv - Ironi Kiryat Ata 77:102",
     VideoKind.FULL_GAME, "Ironi Kiryat Ata", 77, 102),
])
def test_parses_summary_titles(title, kind, opponent, maccabi, opponent_points):
    parsed = parse_game_video_title(title)
    assert parsed is not None, f"expected a parse for: {title}"
    assert parsed.kind == kind
    assert parsed.opponent_raw == opponent
    assert (parsed.maccabi_points, parsed.opponent_points) == (maccabi, opponent_points)


@pytest.mark.parametrize("title,opponent,maccabi,opponent_points,language", [
    # The archive uploads carry no keyword at all: "<competition> <year>, <stage>,
    # <teams> <score>". These are most of the pre-2010 material on the channel.
    ("National League 1985, Round 15, Hapoel Holon - Maccabi Tel Aviv 82:83",
     "Hapoel Holon", 83, 82, "en"),
    ("1980 European Cup, Preliminary Round, Maccabi Tel Aviv vs. Aris Thessaloniki 111:78",
     "Aris Thessaloniki", 111, 78, "en"),
    ("1997 State Cup Final, Hapoel Jerusalem vs. Maccabi Tel Aviv 89:82",
     "Hapoel Jerusalem", 82, 89, "en"),
    ("EuroLeague 1997, Group Stage, Maccabi Tel Aviv vs. CSKA 78:77, Koudelin's game-winning basket",
     "CSKA", 78, 77, "en"),
    ('גביע אירופה 1985,בית הגמר,מח\' 1, מכבי ת"א - באנקו רומא 86:95',
     "באנקו רומא", 95, 86, "he"),
    ('ליגה לאומית 1997,מח\' 11, מכבי ת"א - הפועל גליל עליון 86:88',
     "הפועל גליל עליון", 88, 86, "he"),
    ('בני הרצליה - מכבי Rapyd ת"א 114:99 (18 שלשות)',
     "בני הרצליה", 114, 99, "he"),
    # Stage before a colon rather than a comma. The stage text used to land inside the
    # opponent name, so no alias could ever match it.
    # Hebrew, so the first team named takes the SECOND number.
    ("גביע אירופה 1995 שלב הבתים 1/8 הגמר מח' 2: פנאתניקוס - מכבי ת\"א 85:80",
     "פנאתניקוס", 85, 80, "he"),
    ("בית 1/8 הגמר: אורטז - מכבי ת\"א 78:92", "אורטז", 78, 92, "he"),
    ("יורוליג 1998 שלב הבתים מח' 11: טלקום אנקרה - מכבי ת\"א 70:83",
     "טלקום אנקרה", 70, 83, "he"),
])
def test_parses_archive_titles_without_a_keyword(title, opponent, maccabi, opponent_points, language):
    parsed = parse_game_video_title(title)
    assert parsed is not None, f"expected a parse for: {title}"
    assert parsed.opponent_raw == opponent
    assert (parsed.maccabi_points, parsed.opponent_points) == (maccabi, opponent_points)
    assert parsed.language == language
    # No keyword means the kind cannot be read off the title; the matcher decides it
    # from the video's duration instead.
    assert parsed.kind is None


@pytest.mark.parametrize("title", [
    # Player compilations carrying a real game score, in both languages.
    "היילייטס רומן סורקין (18 נקודות) | מכבי מול נתניה 92:102",
    "היילייטס ג'יילן הורד (21 נקודות ו-10 אסיסטים) | מכבי מול נתניה 92:102",
    "היילייטס רומן סורקין (16 נקודות) | בני הרצליה - מכבי Rapyd ת\"א 114:99",
    "Lonnie Walker Highlights (15 Pts) Maccabi Rapyd Tel Aviv vs. Ironi Ramat Gan 81:84",
    # Friendlies, however they are worded.
    "Training match summary | Maccabi Rapyd Tel Aviv - Maccabi Raanana 66:99",
    "משחק הכנה: מכבי - זניט 77:102 | FULL GAME",
])
def test_rejects_player_clips_and_friendlies_without_a_keyword(title):
    assert parse_game_video_title(title) is None


@pytest.mark.parametrize("title", [
    # Player compilations: a name and a points count, no game score.
    "Roman Sorkin (13 points) Highlights vs Galil Elyon | המהלכים של רומן סורקין נגד גליל עליון",
    "John DiBartolomeo Highlights (18 points) | Bnei Herzliya vs. Maccabi Rapyd Tel Aviv 114:99",
    "Tyler Dorsey Highlights vs Olympiacos",
    "Highlights: Jake Cohen (15 points) vs Kiryat Ata",
    # Not games at all.
    "Welcome to Maccabi Shane Hunter",
    "אצלי בלב | סדרת גמר הפלייאוף 2025-26",
    "מבט לתוך האימון בקפריסין 👀",
    # A game prefix but no score to match on.
    "Highlights: Maccabi FOX Tel Aviv - Maccabi Haifa",
    # Pre-season friendly: teams and a score, but no Cargo row exists for it.
    'צפו במשחק ההכנה: מכבי Rapyd ת"א - מכבי תפוזינה ראשון לציון 81:95',
])
def test_rejects_non_game_titles(title):
    assert parse_game_video_title(title) is None
