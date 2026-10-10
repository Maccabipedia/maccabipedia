from datetime import date

import pytest

from maccabipediabot.maintenance.papers.newspaper_names import NewspaperClip, NewspaperClipError, check_cap
from maccabipediabot.maintenance.tickets.ticket_names import Sport

RED_STAR = dict(
    paper="ידיעות אחרונות", publish_date=date(1998, 10, 30), classification="סיקור משחק",
    sport=Sport.BASKETBALL, opponent="הכוכב האדום בלגרד", game_date=date(1998, 10, 29),
    game_page="כדורסל:29-10-1998 הכוכב האדום בלגרד נגד מכבי תל אביב - פיבא יורוליג",
)


def clip(**changes):
    return NewspaperClip(**{**RED_STAR, **changes})


def test_file_name_is_built_from_the_params():
    assert clip().file_name == "ידיעות אחרונות 30-10-1998 סיקור משחק כדורסל הכוכב האדום בלגרד (29.10.1998).jpg"


def test_second_piece_gets_its_description_after_the_game_date():
    assert clip(description="תגובות קטש").file_name.endswith("(29.10.1998) תגובות קטש.jpg")


def test_page_text_uses_the_sports_template_and_exact_game_page():
    assert clip().page_text == (
        "{{תיוג עיתוני כדורסל\n|שם עיתון=ידיעות אחרונות\n|תאריך פרסום=30-10-1998\n"
        "|סיווג=סיקור משחק\n|שיוך משחק=" + RED_STAR["game_page"] + "\n}}")


@pytest.mark.parametrize("description", ["(2)", "2", "עיתון2", "עמוד 68", "reactions"])
def test_numbered_or_non_hebrew_description_is_refused(description):
    with pytest.raises(NewspaperClipError):
        clip(description=description)


@pytest.mark.parametrize("changes", [
    {"paper": "ידיעות אחרונת"},                       # typo of a known paper
    {"classification": "תגובות"},                      # not a template value
    {"opponent": 'צסק"א מוסקבה'},                      # quote mark in a file name
    {"opponent": "הכוכב האדום"},                       # only part of the name in the title
    {"publish_date": date(1998, 12, 30)},              # report two months after the game
    {"classification": "לקראת משחק"},                  # preview published after the game
    {"game_date": date(1998, 10, 28)},                 # game page is on another date
    {"game_page": "משחק:29-10-1998 הכוכב האדום בלגרד נגד מכבי תל אביב"},  # football prefix
])
def test_broken_params_are_refused(changes):
    with pytest.raises(NewspaperClipError):
        clip(**changes)


def test_cap_counts_existing_files():
    check_cap(["קובץ:א.jpg"], 1, special=False)
    with pytest.raises(NewspaperClipError, match="up to 2"):
        check_cap(["קובץ:א.jpg", "קובץ:ב.jpg"], 1, special=False)
    check_cap(["קובץ:א.jpg", "קובץ:ב.jpg"], 1, special=True)
    with pytest.raises(NewspaperClipError, match="up to 5"):
        check_cap([f"קובץ:{n}.jpg" for n in range(5)], 1, special=True)
