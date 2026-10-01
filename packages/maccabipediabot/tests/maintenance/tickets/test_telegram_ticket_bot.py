from datetime import date

from maccabipediabot.maintenance.tickets import telegram_ticket_bot as bot
from maccabipediabot.maintenance.tickets.ticket_names import Sport

ME, STRANGER, BOT_ID, GROUP, OTHER_GROUP = 111, 999, 555, -100777, -100888
MINE = frozenset({GROUP})


def _msg(message_id, sender=ME, **fields):
    """A message in the whitelisted group, unless a test moves it."""
    return {"message_id": message_id, "from": {"id": sender, "is_bot": sender == BOT_ID},
            "chat": {"id": GROUP, "type": "supergroup", "title": "כרטיסים"}, **fields}


def _doc(name, file_id="F", size=1000):
    return {"file_id": file_id, "file_name": name, "file_size": size}


def _updates(*messages):
    return [{"update_id": 100 + i, "message": m} for i, m in enumerate(messages)]


class FakeUploader:
    def __init__(self, games=None, existing=()):
        self.games = games or {}
        self.existing = set(existing)
        self.uploaded = []

    def game_pages_on(self, sport, game_date):
        return self.games.get((sport, game_date), [])

    def file_exists(self, name):
        return name in self.existing

    def upload(self, name, data, text):
        self.uploaded.append((name, data, text))
        self.existing.add(name)


class FakeApi:
    def __init__(self, pages):
        self.pages = list(pages)
        self.offsets = []
        self.messages = []
        self.documents = []

    def get_updates(self, offset=None, limit=100):
        self.offsets.append(offset)
        return self.pages.pop(0) if self.pages else []

    def download(self, file_id):
        return b"bytes-of-" + file_id.encode()

    def send_message(self, chat_id, text):
        self.messages.append((chat_id, text))

    def send_document(self, chat_id, file_id, caption, reply_to, buttons=None):
        self.documents.append((chat_id, file_id, caption, reply_to, buttons))

    edits: list
    answered: list

    def edit_caption(self, chat_id, message_id, caption, buttons=None):
        self.__dict__.setdefault("edits", []).append((chat_id, message_id, caption, buttons))

    def answer_callback(self, callback_id):
        self.__dict__.setdefault("answered", []).append(callback_id)


BASKETBALL_GAME = {(Sport.BASKETBALL, date(2020, 9, 24)): ["מכבי נגד פלוני 24-09-2020"]}


class TestCollect:
    def test_any_member_of_the_whitelisted_group_may_upload(self):
        batch = bot.collect(_updates(_msg(1, STRANGER, document=_doc("כרטיס משחק כדורסל 24-09-2020.jpg"))), MINE)
        assert len(batch.jobs) == 1

    def test_private_chats_other_groups_and_channels_are_ignored(self):
        private = _msg(1, document=_doc("a.jpg"))
        private["chat"] = {"id": ME, "type": "private"}
        other = _msg(2, document=_doc("a.jpg"))
        other["chat"]["id"] = OTHER_GROUP
        channel = _msg(3, document=_doc("a.jpg"))
        channel["chat"] = {"id": GROUP, "type": "channel"}
        batch = bot.collect(_updates(private, other, channel), MINE)
        assert batch.jobs == [] and batch.notes == {}

    def test_a_button_pressed_outside_the_group_is_ignored(self):
        question = _question_message()
        question["chat"]["id"] = OTHER_GROUP
        assert bot.collect([_press(1, "sport:BASKETBALL:2026-09-27", message=question)], MINE).jobs == []

    def test_chat_photos_and_other_files_get_no_reaction(self):
        batch = bot.collect(_updates(
            _msg(1, text="מה המצב?"),
            _msg(2, photo=[{"file_id": "p"}], caption="איזה משחק היה"),
            _msg(3, document=_doc("סיכום.pdf")),
        ), MINE)
        assert batch.jobs == [] and batch.notes == {}

    def test_a_photo_captioned_like_a_ticket_is_refused(self):
        batch = bot.collect(_updates(_msg(1, photo=[{"file_id": "p"}], caption="כדורסל 24-09-2020")), MINE)
        assert batch.jobs == [] and batch.notes == {GROUP: [bot.PHOTO_TEXT]}

    def test_help_command(self):
        batch = bot.collect(_updates(_msg(1, text="/help@MaccabiTicketsBot")), MINE)
        assert batch.notes == {GROUP: [bot.HELP_TEXT]}

    def test_a_chatty_reply_to_a_ticket_is_not_an_answer(self):
        original = _msg(1, document=_doc("כרטיס משחק כדורסל 24-09-2020.jpg"))
        jobs = bot.collect(_updates(original, _msg(2, STRANGER, reply_to_message=original, text="איזה כרטיס!")), MINE).jobs
        assert [j.message_id for j in jobs] == [1]

    def test_caption_is_a_hint(self):
        [job] = bot.collect(_updates(_msg(1, document=_doc("132321.jpg"), caption="כדורסל 24-09-2020")), MINE).jobs
        assert job.hints == ["כדורסל 24-09-2020"] and job.file_name == "132321.jpg"

    def test_reply_to_the_bots_question_uses_only_the_reply_text(self):
        question = _msg(7, BOT_ID, document=_doc("132321.jpg", "F7"), caption="כדורגל 23 באוגוסט 2026 ...")
        [job] = bot.collect(_updates(_msg(8, reply_to_message=question, text="כדורסל 24-09-2020")), MINE).jobs
        assert (job.file_id, job.hints, job.message_id) == ("F7", ["כדורסל 24-09-2020"], 8)

    def test_file_answered_in_the_same_batch_is_handled_once(self):
        original = _msg(1, document=_doc("132321.jpg"))
        jobs = bot.collect(_updates(original, _msg(2, reply_to_message=original, text="כדורסל 24-09-2020")), MINE).jobs
        assert [j.hints for j in jobs] == [["כדורסל 24-09-2020"]]


def _job(name, hints=(), size=1000):
    return bot.TicketJob(GROUP, 1, "F", name, size, list(hints))


class TestProcess:
    def test_uploads_under_the_canonical_name_with_the_template(self):
        uploader = FakeUploader(BASKETBALL_GAME)
        outcome = bot.process(_job("132321.jpg", ["כדורסל 24-09-2020"]), uploader, lambda f: b"x")
        assert outcome.kind is bot.Kind.UPLOADED
        assert uploader.uploaded == [("כרטיס משחק כדורסל 24-09-2020.jpg", b"x",
                                      "{{תיוג כרטיס משחק כדורסל|משחק=מכבי נגד פלוני 24-09-2020}}")]

    def test_football_uses_the_plain_template(self):
        uploader = FakeUploader({(Sport.FOOTBALL, date(2026, 8, 23)): ["g"]})
        bot.process(_job("כרטיס משחק 23 באוגוסט 2026.JPG"), uploader, lambda f: b"x")
        assert uploader.uploaded[0][0::2] == ("כרטיס משחק 23 באוגוסט 2026.jpg", "{{תיוג כרטיס משחק}}")

    def test_football_underscore_name_is_uploaded_under_the_spaced_hebrew_date_name(self):
        uploader = FakeUploader({(Sport.FOOTBALL, date(1994, 12, 3)): ["g"]})
        outcome = bot.process(_job("כרטיס_משחק_3_בדצמבר_1994.jpg"), uploader, lambda f: b"x")
        assert outcome.kind is bot.Kind.UPLOADED
        assert uploader.uploaded == [("כרטיס משחק 03 בדצמבר 1994.jpg", b"x", "{{תיוג כרטיס משחק}}")]

    def test_unknown_name_becomes_a_question(self):
        assert bot.process(_job("132321.jpg"), FakeUploader(), lambda f: b"x").kind is bot.Kind.QUESTION

    def test_date_without_a_game_becomes_a_question(self):
        outcome = bot.process(_job("כרטיס משחק כדורסל 24-09-2040.jpg"), FakeUploader(), lambda f: b"x")
        assert outcome.kind is bot.Kind.QUESTION and "24-09-2040" in outcome.detail

    def test_existing_file_is_a_duplicate_and_not_downloaded(self):
        uploader = FakeUploader(BASKETBALL_GAME, existing={"כרטיס משחק כדורסל 24-09-2020.jpg"})
        outcome = bot.process(_job("כרטיס משחק כדורסל 24-09-2020.jpg"), uploader, lambda f: 1 / 0)
        assert outcome.kind is bot.Kind.DUPLICATE and uploader.uploaded == []

    def test_two_basketball_games_on_the_date_fail(self):
        uploader = FakeUploader({(Sport.BASKETBALL, date(2020, 9, 24)): ["a", "b"]})
        assert bot.process(_job("כרטיס משחק כדורסל 24-09-2020.jpg"), uploader, lambda f: b"x").kind is bot.Kind.FAILED

    def test_pdf_and_oversized_files_fail(self):
        assert bot.process(_job("כרטיס משחק כדורסל 24-09-2020.pdf"), FakeUploader(BASKETBALL_GAME), bytes).kind is bot.Kind.FAILED
        big = _job("כרטיס משחק כדורסל 24-09-2020.jpg", size=21 * 1024 * 1024)
        assert bot.process(big, FakeUploader(BASKETBALL_GAME), bytes).kind is bot.Kind.FAILED


def test_run_sends_one_summary_questions_back_and_confirms_every_page():
    api = FakeApi([_updates(
        _msg(1, document=_doc("כרטיס משחק כדורסל 24-09-2020.jpg", "A")),
        _msg(2, document=_doc("כרטיס משחק כדורסל 24-09-2020.jpg", "B")),
        _msg(3, document=_doc("132321.jpg", "C")),
    )])
    uploader = FakeUploader(BASKETBALL_GAME)

    bot.run(api, MINE, uploader, dry_run=False)

    assert [u[0] for u in uploader.uploaded] == ["כרטיס משחק כדורסל 24-09-2020.jpg"]
    assert [(d[1], d[3]) for d in api.documents] == [("C", 3)]
    [(chat, text)] = api.messages
    assert chat == GROUP and "✅ הועלו: 1" in text and "⏭ כבר היו בוויקי: 1" in text and "❓" in text
    assert api.offsets == [None, 103]


WHATSAPP = "WhatsApp Image 2026-09-27 at 20.31.24.jpg"


def _question_message(message_id=50, file_id="W"):
    question = _msg(message_id, BOT_ID, document=_doc(WHATSAPP, file_id), caption="...")
    return question


def _press(update_id, data, sender=ME, message=None):
    return {"update_id": update_id, "callback_query": {
        "id": f"cb{update_id}", "from": {"id": sender}, "data": data, "message": message or _question_message()}}


class TestSportButtons:
    def test_date_only_caption_is_asked_with_three_sport_buttons(self):
        api = FakeApi([_updates(_msg(1, document=_doc(WHATSAPP, "W"), caption="27/09/2026"))])
        bot.run(api, MINE, FakeUploader(), dry_run=False)
        [(_, file_id, caption, reply_to, buttons)] = api.documents
        assert (file_id, reply_to) == ("W", 1) and "27-09-2026" in caption
        assert [data for _, data in buttons] == [
            "sport:FOOTBALL:2026-09-27", "sport:BASKETBALL:2026-09-27", "sport:VOLLEYBALL:2026-09-27"]

    def test_the_date_in_a_whatsapp_name_is_not_the_game_date(self):
        outcome = bot.process(_job(WHATSAPP), FakeUploader(), bytes)
        assert outcome.kind is bot.Kind.QUESTION and outcome.asked_date is None

    def test_a_press_uploads_and_rewrites_the_question_without_buttons(self):
        uploader = FakeUploader({(Sport.BASKETBALL, date(2026, 9, 27)): ["g"]})
        api = FakeApi([[_press(1, "sport:BASKETBALL:2026-09-27")]])
        bot.run(api, MINE, uploader, dry_run=False)
        assert uploader.uploaded[0][0] == "כרטיס משחק כדורסל 27-09-2026.jpg"
        assert api.edits == [(GROUP, 50, "✅ כרטיס משחק כדורסל 27-09-2026.jpg", None)]
        assert api.answered == ["cb1"]

    def test_only_the_first_press_counts_whoever_in_the_group_pressed(self):
        batch = bot.collect([
            _press(1, "garbage"),
            _press(2, "sport:FOOTBALL:2026-09-27", sender=STRANGER),
            _press(3, "sport:BASKETBALL:2026-09-27"),
        ], MINE)
        assert [j.hints for j in batch.jobs] == [["כדורגל 27-09-2026"]]

    def test_a_sport_without_a_game_that_day_asks_again_with_buttons(self):
        api = FakeApi([[_press(1, "sport:VOLLEYBALL:2026-09-27")]])
        bot.run(api, MINE, FakeUploader(), dry_run=False)
        [(_, message_id, caption, buttons)] = api.edits
        assert message_id == 50 and "אין משחק כדורעף" in caption and len(buttons) == 3

    def test_a_text_reply_to_the_question_rewrites_it(self):
        uploader = FakeUploader({(Sport.BASKETBALL, date(2026, 9, 27)): ["g"]})
        api = FakeApi([_updates(_msg(8, reply_to_message=_question_message(), text="כדורסל 27-09-2026"))])
        bot.run(api, MINE, uploader, dry_run=False)
        assert [e[1] for e in api.edits] == [50] and uploader.uploaded


def test_summary_links_wiki_files_and_escapes_errors():
    text = bot.summary([
        bot.Outcome(bot.Kind.UPLOADED, "כרטיס משחק כדורסל 24-09-2020.jpg", "כרטיס משחק כדורסל 24-09-2020.jpg"),
        bot.Outcome(bot.Kind.FAILED, "x.jpg: error <html>"),
    ])
    assert '<a href="https://www.maccabipedia.co.il/%D7%A7' in text
    assert "&lt;html&gt;" in text and "<html>" not in text


def test_dry_run_uploads_sends_and_confirms_nothing(capsys):
    api = FakeApi([_updates(_msg(1, document=_doc("כרטיס משחק כדורסל 24-09-2020.jpg")))])
    uploader = bot.TicketUploader(dry_run=True)
    uploader.game_pages_on = lambda sport, day: ["g"]
    uploader.file_exists = lambda name: False

    bot.run(api, MINE, uploader, dry_run=True)

    assert api.messages == [] and api.documents == [] and api.offsets == [None]
    assert "[DRY RUN]" in capsys.readouterr().out
