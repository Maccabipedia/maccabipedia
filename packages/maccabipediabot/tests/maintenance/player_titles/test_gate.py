"""The gate: the six title lists a live profile computes, against the lists the credits give."""
from maccabipediabot.maintenance.football.player_titles import gate
from maccabipediabot.maintenance.football.player_titles.gate import (
    Profile,
    credit_lists,
    live_lists,
    profile_from_wikitext,
    run_gate,
)
from maccabipediabot.maintenance.football.player_titles.rule import Credit

KINDS = {
    "ליגה": {"ליגת העל", "ליגה לאומית"},
    "גביע": {"גביע המדינה"},
    "גביע הטוטו": {"גביע הטוטו", "גביע הטוטו לליגת העל"},
    "אלוף האלופים": {"אלוף האלופים"},
    "גביע ליליאן": set(),
    "גביע אסיה לאלופות": set(),
}
NIMNI = Profile("אבי נמני", display_name=None, add={}, remove={})
NIMNI_CREDITS = [
    Credit("אבי נמני", "1995/96", "ליגה לאומית"),
    Credit("אבי נמני", "2002/03", "ליגת העל"),
    Credit("אבי נמני", "2000/01", "גביע המדינה"),
]
NIMNI_LISTS = {
    "ליגה": ["1995/96", "2002/03"], "גביע": ["2000/01"], "גביע הטוטו": [],
    "אלוף האלופים": [], "גביע ליליאן": [], "גביע אסיה לאלופות": [],
}


def expansion_of(*lists_per_profile: list[str]) -> dict:
    """An expandtemplates answer: per profile, the six outputs in KINDS order."""
    chunks = []
    for profile_index, outputs in enumerate(lists_per_profile):
        for kind_index, output in enumerate(outputs):
            chunks.append(f"@@{profile_index}@@{kind_index}@@{output}")
    return {"expandtemplates": {"wikitext": "\n".join(chunks)}}


class ExpandApi:
    def __init__(self, answer: dict):
        self.answer = answer
        self.calls: list[dict] = []

    def __call__(self, **params) -> dict:
        self.calls.append(params)
        return self.answer


NIMNI_OUTPUTS = ["1995/96, 2002/03", "2000/01", "", "", "", ""]


def test_profile_fields_are_read_from_the_profile_call():
    wikitext = (
        "{{פרופיל כדורגל\n|שם להצגה=אסטר סוקלר\n|הסרת זכיות באלוף האלופים כשחקן=2026/27\n"
        "|הוספת זכיות באליפות כשחקן= 1995/96, 1996/97 \n|הוספת זכיות בגביע המדינה כשחקן=\n}}"
    )

    profile = profile_from_wikitext("אסטר סוקלר (כדורגלן)", wikitext)

    assert profile == Profile(
        "אסטר סוקלר (כדורגלן)", display_name="אסטר סוקלר",
        add={"ליגה": "1995/96, 1996/97"}, remove={"אלוף האלופים": "2026/27"},
    )


def test_a_page_without_the_profile_call_is_a_plain_profile():
    assert profile_from_wikitext("אבי נמני", "טקסט חופשי") == NIMNI


def test_live_request_uses_pagename_for_a_plain_profile_and_the_display_name_when_set():
    api = ExpandApi(expansion_of(NIMNI_OUTPUTS, NIMNI_OUTPUTS))
    renamed = Profile("אסטר סוקלר (כדורגלן)", display_name="אסטר סוקלר", add={}, remove={"אלוף האלופים": "2026/27"})

    live_lists(api, [NIMNI, renamed])

    text = api.calls[0]["text"]
    assert api.calls[0]["action"] == "expandtemplates"
    assert (
        "@@0@@0@@{{פרופיל כדורגל/הרכבת רשימת זכיות/שחקן |זכיות להוספה= |זכיות להסרה="
        " |קטגוריית מפעל=ליגה |שם={{PAGENAME:אבי נמני}}}}"
    ) in text
    assert (
        "@@1@@3@@{{פרופיל כדורגל/הרכבת רשימת זכיות/שחקן |זכיות להוספה= |זכיות להסרה=2026/27"
        " |שם מפעל=אלוף האלופים |שם=אסטר סוקלר}}"
    ) in text


def test_live_answer_is_split_per_profile_and_kind():
    other = Profile("שרן ייני", display_name=None, add={}, remove={})
    api = ExpandApi(expansion_of(NIMNI_OUTPUTS, ["2012/13", "", "2008/09, 2014/15", "", "", ""]))

    result = live_lists(api, [NIMNI, other])

    assert result["אבי נמני"].lists == NIMNI_LISTS and result["אבי נמני"].error is None
    assert result["שרן ייני"].lists["ליגה"] == ["2012/13"]
    assert result["שרן ייני"].lists["גביע הטוטו"] == ["2008/09", "2014/15"]


def test_live_text_that_is_not_a_season_is_an_error():
    outputs = ['<div class="error">Error 1064: You have an error in your SQL syntax</div>', "", "", "", "", ""]
    api = ExpandApi(expansion_of(outputs))

    result = live_lists(api, [NIMNI])

    assert "Error 1064" in result["אבי נמני"].error


def test_a_missing_chunk_in_the_answer_is_an_error():
    api = ExpandApi({"expandtemplates": {"wikitext": "@@0@@0@@1995/96"}})

    assert live_lists(api, [NIMNI])["אבי נמני"].error is not None


def test_credit_lists_count_a_competition_under_every_kind_it_matches():
    kinds = dict(KINDS, **{"גביע": {"גביע המדינה", "גביע הטוטו"}})
    player_credits = [Credit("שרן ייני", "2008/09", "גביע הטוטו"), Credit("שרן ייני", "2008/09", "גביע הטוטו")]

    lists = credit_lists(player_credits, kinds)

    assert lists["גביע"] == ["2008/09"] and lists["גביע הטוטו"] == ["2008/09"] and lists["ליגה"] == []


def test_gate_passes_when_every_profile_matches():
    api = ExpandApi(expansion_of(NIMNI_OUTPUTS))

    assert run_gate(api, [NIMNI], NIMNI_CREDITS, KINDS) == 0


def test_gate_fails_on_a_difference():
    api = ExpandApi(expansion_of(NIMNI_OUTPUTS))

    assert run_gate(api, [NIMNI], NIMNI_CREDITS[:2], KINDS) == 1


def test_gate_fails_on_a_live_error():
    api = ExpandApi(expansion_of(["שגיאה", "", "", "", "", ""]))

    assert run_gate(api, [NIMNI], [], KINDS) == 1


def test_gate_looks_up_credits_by_the_display_name():
    renamed = Profile("אבי נמני (כדורגלן)", display_name="אבי נמני", add={}, remove={})
    api = ExpandApi(expansion_of(NIMNI_OUTPUTS))

    assert run_gate(api, [renamed], NIMNI_CREDITS, KINDS) == 0


def test_selftest_must_fail():
    """One player's live lists against another player's credits: a gate that passes this compares nothing."""
    api = ExpandApi(expansion_of(NIMNI_OUTPUTS))
    credits = NIMNI_CREDITS + [Credit(gate.SELFTEST_OTHER_PLAYER, "2012/13", "ליגת העל")]

    assert run_gate(api, [NIMNI], credits, KINDS, credits_name_override=gate.SELFTEST_OTHER_PLAYER) == 1


class WikiReadApi:
    """Category members in two continued pages, then page texts."""

    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, **params) -> dict:
        self.calls.append(params)
        if params.get("list") == "categorymembers":
            if "cmcontinue" not in params:
                return {"continue": {"cmcontinue": "page|2"}, "query": {"categorymembers": [{"title": "אבי נמני"}]}}
            return {"query": {"categorymembers": [{"title": "אסטר סוקלר (כדורגלן)"}]}}
        return {"query": {"pages": {
            "1": {"title": "אבי נמני", "revisions": [{"slots": {"main": {"*": "{{פרופיל כדורגל}}"}}}]},
            "2": {"title": "אסטר סוקלר (כדורגלן)",
                  "revisions": [{"slots": {"main": {"*": "{{פרופיל כדורגל|שם להצגה=אסטר סוקלר}}"}}}]},
        }}}


def test_profiles_follow_the_category_continuation_and_read_each_page():
    api = WikiReadApi()

    found = gate.profiles(api)

    assert found == [NIMNI, Profile("אסטר סוקלר (כדורגלן)", display_name="אסטר סוקלר", add={}, remove={})]
    assert api.calls[0]["cmtitle"] == "קטגוריה:פרופילי כדורגל" and api.calls[0]["cmnamespace"] == 0
    assert api.calls[2]["titles"] == "אבי נמני|אסטר סוקלר (כדורגלן)"
