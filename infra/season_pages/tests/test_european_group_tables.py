"""European group tables: the data holds together, and the three wiki texts come out as rolled out."""
import pytest

from european_group_tables import (GROUP_CALL, load, problems, renderer_candidate, season_template_candidate,
                                   shown_rows, table_call, template_text)

# The parts of production's תבנית:עונת כדורגל the candidate hooks onto, between neighbours.
SEASON_TEMPLATE = (
    '<includeonly><!--\n-->{{#vardefine: עונה בפורמט שליפה |{{#replace: {{#var: עונה להצגה}} |/|-}} }}<!--\n'
    '-->{{#vardefine: תמונה קבוצתית |x}}<!--\n'
    '-->{{#arraydefine: רשימה לתוכן עניינים |סגל שחקנים, \n'
    '{{#קיים: תבנית: טבלת ליגת כדורגל {{#var: עונה להצגה}} |טבלת הליגה}}, שיאנים, משחקים }}<!--\n'
    '-->{{#קיים: תבנית: טבלת ליגת כדורגל {{#var: עונה להצגה}} |{{פרק\n|כותרת=טבלת הליגה\n'
    '|טקסט={{טבלת ליגת כדורגל {{#var: עונה להצגה}} }}\n}}\n}}<!--\n\n'
    '--><div class="players-records-container" id="שיאנים"></div></includeonly>')

# The row loop of production's תבנית:טבלת ליגת כדורגל, as far as the candidate touches it.
RENDERER = (
    '| {{#arraydefine: קבוצה נוכחית|{{#arrayindex: טבלת ליגה |{{#var: מיקום בלולאה}} }} |^}}<!--\n'
    '-->{{#תנאי: {{#arraysize: פלייאופים}}\n|x}}<!--\n'
    '--><div class="row <!--\n-->{{#שווה: {{#var: מיקום בלולאה}} |0 | champion}} y">\n'
    '<span class="position">{{#expr: {{#var: מיקום בלולאה}} + 1}}</span>\n')

GROUPS = load()


@pytest.mark.parametrize('season', sorted(GROUPS))
def test_every_season_holds_together(season):
    assert problems(season, GROUPS[season]) == []


def test_problems_catches_points_that_do_not_follow():
    group = {**GROUPS['2016/17'], 'rows': [dict(row) for row in GROUPS['2016/17']['rows']]}
    group['rows'][0]['points'] += 1
    assert any('points do not follow' in problem for problem in problems('2016/17', group))


def test_a_group_is_shown_whole():
    first, rows = shown_rows(GROUPS['2016/17'])
    assert (first, len(rows)) == (1, 4)
    assert 'מיקום ראשון' not in table_call(GROUPS['2016/17'])


def test_a_league_phase_shows_seven_rows_around_maccabi():
    first, rows = shown_rows(GROUPS['2024/25'])
    assert first == 26
    assert [row['team'] for row in rows].index('מכבי תל אביב') == 3
    call = table_call(GROUPS['2024/25'])
    assert '|מיקום ראשון=26\n' in call
    assert 'מוצגים המקומות 26-32 מתוך 36.' in call


def test_last_place_keeps_the_window_inside_the_table():
    first, rows = shown_rows(GROUPS['2025/26'])
    assert (first, len(rows), rows[-1]['team']) == (30, 7, 'מכבי תל אביב')


def test_template_returns_the_title_or_the_table():
    text = template_text(GROUPS['2016/17'])
    assert text.startswith("{{#switch: {{{1|}}}\n|כותרת=הליגה האירופית - בית ד'\n|#default={{טבלת ליגת כדורגל\n")
    assert 'מכבי תל אביב^6^2^1^3^7^9^7,\nדאנדלק^6^1^1^4^5^8^4\n}}\n}}<noinclude>' in text


def test_season_template_looks_the_title_up_once_and_adds_toc_and_section():
    candidate = season_template_candidate(SEASON_TEMPLATE)
    assert candidate.count('{{#קיים: תבנית: ' + GROUP_CALL) == 1
    assert '|טבלת הליגה}}, {{#var: טבלת בית בינלאומי}}, שיאנים' in candidate
    section = candidate.index('{{#תנאי: {{#var: טבלת בית בינלאומי}} |{{פרק')
    assert candidate.index('|כותרת=טבלת הליגה') < section < candidate.index('players-records-container')


def test_season_template_refuses_to_apply_twice():
    with pytest.raises(ValueError):
        season_template_candidate(season_template_candidate(SEASON_TEMPLATE))


def test_renderer_numbers_from_the_first_position_and_crowns_only_first_place():
    candidate = renderer_candidate(RENDERER)
    assert '{{#vardefine: מיקום מוצג |{{#expr: {{#var: מיקום בלולאה}} + {{{מיקום ראשון|1}}} }} }}' in candidate
    assert '{{#שווה: {{#var: מיקום מוצג}} |1 | champion}}' in candidate
    assert '<span class="position">{{#var: מיקום מוצג}}</span>' in candidate
    with pytest.raises(ValueError):
        renderer_candidate(candidate)
