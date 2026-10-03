from maccabistats.parse.maccabipedia.maccabipedia_parser import build_opponent_names_lookup, restore_opponent_name

OPPONENT_PAGES = ['בית&quot;ר ירושלים', 'מ.ס. אשדוד', 'מכבי עירוני אשדוד', "הפועל באר שבע"]


class TestRestoreOpponentName:
    def test_quote_mark_stripped_by_the_wiki_is_restored(self):
        lookup = build_opponent_names_lookup(OPPONENT_PAGES)

        assert restore_opponent_name('ביתר ירושלים', lookup) == 'בית"ר ירושלים'

    def test_name_without_quotes_is_unchanged(self):
        lookup = build_opponent_names_lookup(OPPONENT_PAGES)

        assert restore_opponent_name('מ.ס. אשדוד', lookup) == 'מ.ס. אשדוד'
        assert restore_opponent_name('מכבי עירוני אשדוד', lookup) == 'מכבי עירוני אשדוד'

    def test_name_with_no_opponent_page_is_kept_as_stored(self):
        lookup = build_opponent_names_lookup(OPPONENT_PAGES)

        assert restore_opponent_name('מכבי פת', lookup) == 'מכבי פת'

    def test_pages_differing_only_by_quotes_are_not_guessed(self):
        lookup = build_opponent_names_lookup(['בית"ר ירושלים', "בית'ר ירושלים"])

        assert restore_opponent_name('ביתר ירושלים', lookup) == 'ביתר ירושלים'
