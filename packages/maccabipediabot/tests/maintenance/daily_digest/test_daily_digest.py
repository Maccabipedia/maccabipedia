import datetime
import json

from maccabipediabot.maintenance.daily_digest import collect, daily_digest, render

BASKETBALL_GAME = "כדורסל:30-09-2026 מכבי תל אביב נגד בשיקטאש - יורוליג"
HISTORIC_GAME = "כדורסל:09-11-1967 מכבי תל אביב נגד אלזאס באניולה - גביע אירופה לאלופות"
FOOTBALL_GAME = "משחק:28-01-1984 מכבי תל אביב נגד הפועל באר שבע - ליגה לאומית"
NOW = datetime.datetime(2026, 10, 3, 9, 0, tzinfo=datetime.timezone.utc)


def _change(title, kind="edit", user="MaccabiBot", comment="", bot=False, **fields):
    return {"type": kind, "title": title, "user": user, "comment": comment, "bot": bot, **fields}


def test_a_bot_run_with_one_comment_collapses_to_one_group():
    changes = [_change(f"כדורסל:דף {n}", comment="refresh", bot=True) for n in range(300)]
    groups = collect.group_changes(changes)
    assert len(groups) == 1
    assert groups[0]["count"] == 300
    assert groups[0]["bot_flag"] is True
    assert len(groups[0]["sample_titles"]) == collect.SAMPLE_TITLES_PER_GROUP


def test_the_same_account_by_hand_stays_its_own_group():
    changes = [_change(f"כדורסל:דף {n}", comment="refresh", bot=True) for n in range(5)]
    changes.append(_change(HISTORIC_GAME, kind="new", comment="יצירת משחק חסר לפי ידיעות אחרונות"))
    groups = collect.group_changes(changes)
    assert [(group["action"], group["count"]) for group in groups] == [("edit", 5), ("new", 1)]


def test_a_move_names_where_the_page_went_and_both_titles_are_linkable():
    move = _change("משחק: 11-11-1939 מכבי תל אביב נגד הכח", kind="log", logtype="move",
                   logaction="move", logparams={"target_title": "משחק:11-11-1939 מכבי תל אביב נגד הכח"})
    activity = collect.build_activity([move], [], NOW, NOW)
    group = activity["change_groups"][0]
    assert group["action"] == "move/move"
    assert group["sample_titles"] == ["משחק: 11-11-1939 מכבי תל אביב נגד הכח → משחק:11-11-1939 מכבי תל אביב נגד הכח"]
    assert collect.link_targets(activity) == {"משחק: 11-11-1939 מכבי תל אביב נגד הכח",
                                              "משחק:11-11-1939 מכבי תל אביב נגד הכח"}


def test_new_games_are_created_game_pages_only_with_their_sport():
    changes = [_change(BASKETBALL_GAME, kind="new", comment="MaccabiBot - Uploading basketball games"),
               _change(FOOTBALL_GAME, kind="edit"),
               _change("תבנית:ארון תארים/הצגת תואר", kind="new", user="אורן המתעפץ"),
               _change("משחק:17-05-1947 מכבי תל אביב נגד מכבי נס ציונה - ליגה א", kind="new")]
    games = collect.new_game_pages(changes)
    assert [(game["sport"], game["title"]) for game in games] == [
        ("basketball", BASKETBALL_GAME),
        ("football", "משחק:17-05-1947 מכבי תל אביב נגד מכבי נס ציונה - ליגה א")]


def test_render_links_only_titles_from_the_data_and_escapes_the_rest():
    text = f"• נוסף [[{BASKETBALL_GAME}|המשחק מול בשיקטאש]] ו-[[דף שהומצא|דף אחר]] <b>\n\nסוף"
    message = render.render_message(text, {BASKETBALL_GAME}, set())
    lines = message.split("\n")
    assert lines[0].startswith(render.RIGHT_TO_LEFT_MARK)
    assert f'<a href="{collect.page_url(BASKETBALL_GAME)}">המשחק מול בשיקטאש</a>' in lines[0]
    assert lines[0].count("<a ") == 1
    assert "ו-דף אחר " in lines[0]
    assert "&lt;b&gt;" in lines[0]
    assert lines[1] == ""
    assert lines[-1] == render.RIGHT_TO_LEFT_MARK + render.SIGNATURE


def test_page_url_keeps_quotes_from_ending_the_link():
    url = collect.page_url("קובץ:סופרגול עונת 2012-13 - כוכבי עבר - יוסל'ה מרימוביץ'.jpg")
    assert "'" not in url and " " not in url
    assert url.startswith("https://www.maccabipedia.co.il/%D7%A7%D7%95%D7%91%D7%A5:")


def test_only_wiki_and_known_pr_urls_survive_as_bare_links():
    pr_url = "https://github.com/Maccabipedia/maccabipedia/pull/259"
    text = (f"• מוזג {pr_url}. ראו https://evil.example/x ו-"
            f"{collect.WIKI_URL}%D7%A2%D7%95%D7%A0%D7%95%D7%AA")
    line = render.render_message(text, set(), {pr_url}).split("\n")[0]
    assert f"{pr_url}." in line
    assert "evil.example" not in line
    assert f"{collect.WIKI_URL}%D7%A2%D7%95%D7%A0%D7%95%D7%AA" in line


def test_render_of_an_empty_reply_is_empty():
    assert render.render_message("\n  \n", set(), set()) == ""


def test_window_starts_a_day_back_on_the_first_run(tmp_path):
    assert daily_digest.window_start(NOW, tmp_path / "missing.json") == NOW - datetime.timedelta(days=1)


def test_window_starts_where_the_last_note_ended(tmp_path):
    state = tmp_path / "state.json"
    daily_digest.save_window_end(NOW - datetime.timedelta(hours=30), state)
    assert daily_digest.window_start(NOW, state) == NOW - datetime.timedelta(hours=30)


def test_window_never_reaches_back_more_than_a_week(tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"last_until": (NOW - datetime.timedelta(days=40)).isoformat()}))
    assert daily_digest.window_start(NOW, state) == NOW - datetime.timedelta(days=7)


def test_a_saved_end_in_the_future_gives_an_empty_window_not_an_inverted_one(tmp_path):
    state = tmp_path / "state.json"
    daily_digest.save_window_end(NOW + datetime.timedelta(hours=2), state)
    assert daily_digest.window_start(NOW, state) == NOW


def test_a_window_with_nothing_has_no_activity():
    assert not daily_digest.has_activity(collect.build_activity([], [], NOW, NOW))
    assert daily_digest.has_activity(collect.build_activity([], [{"number": 1}], NOW, NOW))
