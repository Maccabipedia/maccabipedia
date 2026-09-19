"""The game-row icon swap: exactly the three gallery tests change."""
import pytest

from convert_game_row_icons import candidate_of

# The three icon lines as production's template has them, between two of its
# neighbours that must come through untouched.
ROW = (
    '-->{{#תנאי: {{{FullGame|}}}{{{FullGame2|}}} |<i class="fa-solid fa-film"></i>}}<!--\n'
    '-->{{#תנאי: {{הצגת גלריה לפי קטגוריה |שם קטגוריה={{{PageName|}}}/תוכניית משחק '
    '|אין תוצאות=}} |<i class="fa-solid fa-book"></i>}}<!--\n'
    '-->{{#תנאי: {{הצגת גלריה לפי קטגוריה |שם קטגוריה=עיתונות למשחק מה-{{#var: תאריך עבור מדיה}} '
    '|אין תוצאות=}} |<i class="fa-solid fa-newspaper"></i>}}<!--\n'
    '-->{{#תנאי: {{הצגת גלריה לפי קטגוריה |שם קטגוריה={{{PageName|}}}/תמונות '
    '|אין תוצאות=}} |<i class="fa-solid fa-image"></i>}}\n'
    '</div>'
)


def test_each_gallery_test_becomes_a_category_size_test():
    swapped = candidate_of(ROW)
    assert 'הצגת גלריה לפי קטגוריה' not in swapped
    assert ('{{#ifexpr: {{PAGESINCATEGORY:{{{PageName|}}}/תוכניית משחק|all|R}} > 0 '
            '|<i class="fa-solid fa-book"></i>}}') in swapped
    assert ('{{#ifexpr: {{PAGESINCATEGORY:עיתונות למשחק מה-{{#var: תאריך עבור מדיה}}|all|R}} > 0 '
            '|<i class="fa-solid fa-newspaper"></i>}}') in swapped
    assert ('{{#ifexpr: {{PAGESINCATEGORY:{{{PageName|}}}/תמונות|all|R}} > 0 '
            '|<i class="fa-solid fa-image"></i>}}') in swapped


def test_nothing_else_changes():
    swapped = candidate_of(ROW)
    assert swapped.startswith('-->{{#תנאי: {{{FullGame|}}}{{{FullGame2|}}} '
                              '|<i class="fa-solid fa-film"></i>}}<!--\n')
    assert swapped.endswith('</div>')
    assert swapped.count('\n') == ROW.count('\n')


@pytest.mark.parametrize('broken', [
    ROW.replace('/תמונות ', '/תמונה '),                  # a test it was not written for
    ROW + ROW,                                          # every test twice
])
def test_refuses_a_template_it_was_not_written_for(broken):
    with pytest.raises(SystemExit):
        candidate_of(broken)
