from datetime import date

import pytest

from maccabipediabot.maintenance.tickets.ticket_names import (
    Sport,
    TicketIdentity,
    canonical_file_name,
    find_date,
    identify,
    normalized_extension,
    tagging_template,
)


@pytest.mark.parametrize("text, expected", [
    ("כרטיס משחק כדורסל 24-09-2020.jpg", date(2020, 9, 24)),
    ("כרטיס משחק כדורסל 19.01.2006.jpg", date(2006, 1, 19)),
    ("2020-09-24", date(2020, 9, 24)),
    ("כרטיס משחק 23 באוגוסט 2026.jpg", date(2026, 8, 23)),
    ("כדורגל 1 במרץ 1999", date(1999, 3, 1)),
])
def test_find_date(text, expected):
    assert find_date(text).value == expected


@pytest.mark.parametrize("text", ["132321.jpg", "24092020.jpg", "31-02-2020.jpg", "IMG_20200924.jpg", "", "1-1-20"])
def test_find_date_refuses_anything_that_is_not_clearly_a_date(text):
    assert find_date(text) is None


def test_find_date_skips_an_impossible_date_for_a_real_one():
    assert find_date("31-02-2020 24-09-2020").value == date(2020, 9, 24)


@pytest.mark.parametrize("texts, expected", [
    (["כרטיס משחק כדורסל 24-09-2020.jpg"], TicketIdentity(Sport.BASKETBALL, date(2020, 9, 24))),
    (["כרטיס משחק כדורעף 08-02-2026.jpg"], TicketIdentity(Sport.VOLLEYBALL, date(2026, 2, 8))),
    (["כרטיס משחק 23 באוגוסט 2026.jpg"], TicketIdentity(Sport.FOOTBALL, date(2026, 8, 23))),
    (["כדורגל 23-08-2026", "132321.jpg"], TicketIdentity(Sport.FOOTBALL, date(2026, 8, 23))),
    # the reply fixes the date, the name still gives the sport
    (["24-09-2020", "כרטיס משחק כדורסל 132321.jpg"], TicketIdentity(Sport.BASKETBALL, date(2020, 9, 24))),
    # the reply beats a wrong name
    (["כדורעף 08-02-2026", "כרטיס משחק כדורסל 01-01-2001.jpg"], TicketIdentity(Sport.VOLLEYBALL, date(2026, 2, 8))),
])
def test_identify(texts, expected):
    assert identify(texts) == expected


@pytest.mark.parametrize("texts", [["132321.jpg"], ["כרטיס 24-09-2020.jpg"], ["כדורסל"], []])
def test_identify_asks_when_sport_or_date_is_missing(texts):
    assert identify(texts) is None


def test_canonical_names_follow_each_sports_wiki_convention():
    assert canonical_file_name(TicketIdentity(Sport.FOOTBALL, date(2026, 8, 3)), ".jpg") == "כרטיס משחק 03 באוגוסט 2026.jpg"
    assert canonical_file_name(TicketIdentity(Sport.BASKETBALL, date(2006, 1, 19)), ".png") == "כרטיס משחק כדורסל 19-01-2006.png"
    assert canonical_file_name(TicketIdentity(Sport.VOLLEYBALL, date(2026, 2, 8)), ".jpg") == "כרטיס משחק כדורעף 08-02-2026.jpg"


def test_tagging_templates():
    assert tagging_template(Sport.FOOTBALL, "whatever") == "{{תיוג כרטיס משחק}}"
    assert tagging_template(Sport.BASKETBALL, "P") == "{{תיוג כרטיס משחק כדורסל|משחק=P}}"
    assert tagging_template(Sport.VOLLEYBALL, "כדורעף:08-02-2026 X") == "{{תיוג כרטיס משחק כדורעף|משחק=כדורעף:08-02-2026 X}}"


@pytest.mark.parametrize("name, expected", [("a.JPG", ".jpg"), ("a.jpeg", ".jpeg"), ("a.png", ".png"), ("a.pdf", None), ("noext", None)])
def test_normalized_extension(name, expected):
    assert normalized_extension(name) == expected
