"""The data page's text: rendered from credits, and read back the way MediaWiki reads it."""
from collections import Counter

import pytest

from maccabipediabot.maintenance.football.player_titles.page import (
    HEADER_MARKER,
    UnsafeName,
    parse_page,
    render_page,
    stored_credits,
)
from maccabipediabot.maintenance.football.player_titles.rule import Credit, Title

STATE_CUP_2001 = Title("2000/01", "גביע המדינה")
TOTO_CUP_2001 = Title("2000/01", "גביע הטוטו")
LEAGUE_1996 = Title("1995/96", "ליגה לאומית")
SUPER_CUP_2026 = Title("2026/27", "אלוף האלופים")


def body_of(text: str) -> str:
    """The page without its header: from the first season heading on."""
    return text[text.index("== "):]


def test_render_orders_seasons_titles_and_players():
    text = render_page(
        {
            STATE_CUP_2001: ["כפיר אדרי", "אבי נמני"],
            LEAGUE_1996: ["אבי נמני"],
            TOTO_CUP_2001: ["אבי נמני"],
        },
        removed={},
    )

    assert body_of(text) == (
        "== 1995/96 ==\n"
        "=== ליגה לאומית ===\n"
        "{{תארי שחקני כדורגל/הזנה לקארגו |שחקן=אבי נמני |עונה=1995/96 |מפעל=ליגה לאומית}}\n"
        "== 2000/01 ==\n"
        "=== גביע הטוטו ===\n"
        "{{תארי שחקני כדורגל/הזנה לקארגו |שחקן=אבי נמני |עונה=2000/01 |מפעל=גביע הטוטו}}\n"
        "=== גביע המדינה ===\n"
        "{{תארי שחקני כדורגל/הזנה לקארגו |שחקן=אבי נמני |עונה=2000/01 |מפעל=גביע המדינה}}\n"
        "{{תארי שחקני כדורגל/הזנה לקארגו |שחקן=כפיר אדרי |עונה=2000/01 |מפעל=גביע המדינה}}"
    )


def test_rendered_text_is_the_text_the_wiki_keeps():
    """MediaWiki strips trailing whitespace on save. A render that ended with a newline
    would never equal the saved page, and every rebuild would save and re-store again."""
    text = render_page({LEAGUE_1996: ["אבי נמני"], STATE_CUP_2001: []}, removed={})

    assert text == text.rstrip()


def test_the_header_keeps_the_page_out_of_search_engines_and_says_who_writes_it():
    text = render_page({LEAGUE_1996: ["אבי נמני"]}, removed={})

    header = text[:text.index("== ")]
    assert header.startswith(HEADER_MARKER + "\n__NOINDEX__\n")
    assert "אין לערוך אותו בשלב זה" in header


def test_a_title_with_no_players_still_gets_its_heading():
    state_cup_1967 = Title("1966/67", "גביע המדינה")

    text = render_page({state_cup_1967: []}, removed={})

    assert "=== גביע המדינה ===" in text
    assert parse_page(text).blocks == [state_cup_1967]
    assert stored_credits(parse_page(text)) == Counter()


def test_removed_credit_is_rendered_with_its_reason_and_not_stored():
    late_arrival = Credit("אסטר סוקלר", "2026/27", "אלוף האלופים")

    text = render_page(
        {SUPER_CUP_2026: ["אסטר סוקלר", "דור פרץ"]},
        removed={late_arrival: "הגיע אחרי הזכייה"},
    )

    assert (
        "{{תארי שחקני כדורגל/הזנה לקארגו |שחקן=אסטר סוקלר |עונה=2026/27 |מפעל=אלוף האלופים"
        " |הוסר=הגיע אחרי הזכייה}}"
    ) in text
    assert stored_credits(parse_page(text)) == Counter([Credit("דור פרץ", "2026/27", "אלוף האלופים")])


def test_a_removed_credit_the_rule_does_not_list_is_still_written():
    late_arrival = Credit("אסטר סוקלר", "2026/27", "אלוף האלופים")

    parsed = parse_page(render_page({SUPER_CUP_2026: ["דור פרץ"]}, removed={late_arrival: "הגיע אחרי הזכייה"}))

    removed_lines = [line for line in parsed.lines if line.removed]
    assert [line.credit for line in removed_lines] == [late_arrival]
    assert removed_lines[0].removed == "הגיע אחרי הזכייה"


@pytest.mark.parametrize("name", ['אמנון חרל"פ', "דור תורג'מן", "הרונש‎", "שם ", "יוסף (ג'ו) סידי"])
def test_round_trip_keeps_a_name_byte_for_byte(name):
    text = render_page({LEAGUE_1996: [name]}, removed={})

    assert stored_credits(parse_page(text)) == Counter([Credit(name, "1995/96", "ליגה לאומית")])


@pytest.mark.parametrize("name", ["א|ב", "א=ב", "א{{ב", "א}}ב", "א\nב", "א<!--ב", " אבי נמני", "אבי נמני\t", ""])
def test_unsafe_names_stop_the_render(name):
    with pytest.raises(UnsafeName) as raised:
        render_page({LEAGUE_1996: [name]}, removed={})

    assert repr(name) in str(raised.value)


def test_an_unsafe_season_or_competition_stops_the_render():
    with pytest.raises(UnsafeName):
        render_page({Title("1995/96", "ליגה|לאומית"): ["אבי נמני"]}, removed={})
    with pytest.raises(UnsafeName):
        render_page({Title("1995=96", "ליגה לאומית"): ["אבי נמני"]}, removed={})


def test_parse_reads_a_hand_edited_line():
    text = (
        "== 2000/01 ==\n=== גביע המדינה ===\n"
        "{{ תארי שחקני כדורגל/הזנה לקארגו | מפעל = גביע המדינה | עונה = 2000/01 | שחקן = כפיר אדרי | אושר = היה בסגל }}\n"
    )

    parsed = parse_page(text)

    assert [line.credit for line in parsed.lines] == [Credit("כפיר אדרי", "2000/01", "גביע המדינה")]
    assert parsed.lines[0].approved == "היה בסגל"
    assert parsed.lines[0].removed is None
    assert stored_credits(parsed) == Counter([Credit("כפיר אדרי", "2000/01", "גביע המדינה")])


def test_an_empty_removal_reason_does_not_remove():
    text = "{{תארי שחקני כדורגל/הזנה לקארגו |שחקן=כפיר אדרי |עונה=2000/01 |מפעל=גביע המדינה |הוסר= }}\n"

    assert stored_credits(parse_page(text)) == Counter([Credit("כפיר אדרי", "2000/01", "גביע המדינה")])


def test_parse_reports_the_block_a_line_sits_under():
    text = (
        "{{תארי שחקני כדורגל/הזנה לקארגו |שחקן=לפני הכותרות |עונה=2000/01 |מפעל=גביע המדינה}}\n"
        "== 2000/01 ==\n=== גביע הטוטו ===\n"
        "{{תארי שחקני כדורגל/הזנה לקארגו |שחקן=כפיר אדרי |עונה=2000/01 |מפעל=גביע המדינה}}\n"
    )

    parsed = parse_page(text)

    assert [line.block for line in parsed.lines] == [None, TOTO_CUP_2001]
    assert parsed.blocks == [TOTO_CUP_2001]


def test_a_line_inside_a_comment_or_another_template_is_not_a_line():
    text = (
        "<!-- {{תארי שחקני כדורגל/הזנה לקארגו |שחקן=כפיר אדרי |עונה=2000/01 |מפעל=גביע המדינה}} -->\n"
        "{{תבנית אחרת |שחקן=כפיר אדרי}}\n"
    )

    assert parse_page(text).lines == []


def test_header_marker_is_detected():
    assert parse_page(render_page({LEAGUE_1996: ["אבי נמני"]}, removed={})).has_header_marker is True
    assert parse_page("").has_header_marker is False
