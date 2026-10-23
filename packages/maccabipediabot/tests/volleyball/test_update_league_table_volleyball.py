import pandas as pd

from maccabipediabot.volleyball.update_league_table_volleyball import parse_team_record


def test_parses_separate_for_and_against_columns():
    # The IVA 2026/27 table as of 2026-10-19
    row = pd.Series({'מקום': 1, 'קבוצה': 'מכבי יעדים תל אביב', 'משחקים': 2, "נצ'": 1, "הפ'": 1,
                     'זכו': 187, 'חובה': 160, 'סטים זכו': 5, 'סטים חובה': 3, 'נקודות': 4})

    record = parse_team_record(row)

    assert record.adapt_to_mediawiki_code() == 'מכבי יעדים תל אביב^2^1^1^187^160^5^3^4'


def test_parses_combined_against_for_columns():
    # The layout IVA showed until 2026-10-19: each pair is one "against-for" string
    row = pd.Series({'נקודות': 4, 'יחס סטים': 1.67, 'סטים': '3-5', 'יחס נקודות': 1.17,
                     'סה"כ נקודות': '160-187', "'הפ": 1, "'נצ": 1, "'מש": 2,
                     'קבוצה': 'מכבי יעדים תל אביב', 'מקום': 1})

    record = parse_team_record(row)

    assert record.adapt_to_mediawiki_code() == 'מכבי יעדים תל אביב^2^1^1^187^160^5^3^4'
