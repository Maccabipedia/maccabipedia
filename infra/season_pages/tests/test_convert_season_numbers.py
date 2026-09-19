"""מספרים עונתיים: the container primes, each tab reads - nothing else moves."""
import pytest

from convert_season_numbers import QUERIES, container_candidate, tab_candidate

TAB_CALL = ('{{עונת כדורגל/הצגת מספרים עונתיים/הצגה לפי מפעל |עונה={{{עונה|}}} '
            '|קטגוריית מפעל=%s}}')
CONTAINER = ('<includeonly><!--\n\n--><div class="season-statistics-container">\n'
             '<div class="title" id="מספרי העונה">מספרים עונתיים</div>\n'
             + '\n'.join(TAB_CALL % tab for tab in ('רשמי', 'ליגה', 'גביע', 'בינלאומי'))
             + '\n</div></includeonly>')
# Each query line as production's tab template has it, between neighbours
# that must come through untouched.
TAB = ('<includeonly><!--\n\n-->'
       + '<!--\n-->'.join('{{#vardefine: x |' + query + ' }}' for query in QUERIES)
       + '<!--\n-->{{#vardefine: אחוז ניצחונות |{{#number_format: {{סטטיסטיקה/אחוזים '
         '|{{#var: כמות ניצחונות}} |{{#var: כמות משחקים}} }} }} }}</includeonly>')


def test_container_primes_both_blocks_before_its_strip():
    swapped = container_candidate(CONTAINER)
    assert ('-->{{#invoke:FootballStatsBlock|prime|בלוק=season-results}}'
            '{{#invoke:FootballStatsBlock|prime|בלוק=season-cards}}'
            '<div class="season-statistics-container">') in swapped
    assert swapped.replace('{{#invoke:FootballStatsBlock|prime|בלוק=season-results}}'
                           '{{#invoke:FootballStatsBlock|prime|בלוק=season-cards}}',
                           '') == CONTAINER


def test_sandbox_container_calls_the_sandbox_tab():
    swapped = container_candidate(CONTAINER, sandbox=True)
    assert swapped.count('/הצגה לפי מפעל/ארגז חול |') == 4
    assert '/הצגה לפי מפעל |' not in swapped


def test_each_query_becomes_its_cell():
    swapped = tab_candidate(TAB)
    assert 'סטטיסטיקה/שליפות' not in swapped
    for block, cell in QUERIES.values():
        assert (f'{{{{#invoke:FootballStatsBlock|value|בלוק={block}|תא={cell}'
                '|עונה={{{עונה|}}}|קטגוריית מפעל={{{קטגוריית מפעל|}}}}}') in swapped
    assert 'סטטיסטיקה/אחוזים' in swapped, 'the formatting stays in the template'


def test_the_eight_cells_are_the_blocks_cells():
    assert sorted(QUERIES.values()) == sorted([
        ('season-results', 'wins'), ('season-results', 'draws'),
        ('season-results', 'losses'), ('season-results', 'goalsFor'),
        ('season-results', 'goalsAgainst'), ('season-results', 'cleanSheets'),
        ('season-cards', 'yellows'), ('season-cards', 'reds')])


@pytest.mark.parametrize('broken', [
    TAB.replace('תוצאה=תיקו', 'תוצאה=ת'),          # a query it was not written for
    TAB + TAB,                                   # every query twice
])
def test_tab_refuses_a_template_it_was_not_written_for(broken):
    with pytest.raises(SystemExit):
        tab_candidate(broken)


@pytest.mark.parametrize('broken', [
    CONTAINER.replace(TAB_CALL % 'גביע', ''),     # three tabs
    CONTAINER + CONTAINER,                       # opened twice
])
def test_container_refuses_a_template_it_was_not_written_for(broken):
    with pytest.raises(SystemExit):
        container_candidate(broken)
