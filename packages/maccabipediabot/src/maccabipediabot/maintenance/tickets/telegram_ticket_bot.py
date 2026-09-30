"""Upload game tickets that were sent as files to the MaccabiPedia tickets Telegram bot.

Runs on a schedule (``.github/workflows/upload_tickets_from_telegram.yaml``). Each run reads
the messages waiting for the bot, and for every ticket file works out the sport and date
from its name (or from a caption / text reply), finds the game, uploads the file under the
sport's canonical name with its tagging template, and sends each sender one summary.

A file it cannot place is sent back to the sender with a question; replying to that
message (or to the original file) with the sport and date, e.g. ``כדורסל 24-09-2020``,
gets it uploaded on the next run. No state is kept anywhere: the reply carries the file.

Photos are refused on purpose — Telegram recompresses them. Tickets must be sent as files.

Environment: ``TELEGRAM_TICKETS_BOT_TOKEN``, ``TELEGRAM_TICKETS_ALLOWED_USER_IDS``
(comma-separated Telegram user ids; everyone else is ignored), plus the usual wiki login.

Usage:
    uv run python -m maccabipediabot.maintenance.tickets.telegram_ticket_bot [--dry-run]
"""
from __future__ import annotations

import argparse
import html
import logging
import os
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Callable
from urllib.parse import quote

from maccabipediabot.common.logging_setup import setup_logging
from maccabipediabot.common.wiki_login import get_site
from maccabipediabot.maintenance.tickets import wiki_tickets
from maccabipediabot.maintenance.tickets.telegram_api import MAX_DOWNLOAD_BYTES, TelegramApi
from maccabipediabot.maintenance.tickets.ticket_names import (
    Sport,
    canonical_file_name,
    find_date,
    find_sport,
    identify,
    is_device_name,
    normalized_extension,
    tagging_template,
)

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "שלחו כרטיסים כקובץ (📎 ← קובץ), לא כתמונה, כדי לשמור על האיכות.\n"
    "שם הקובץ צריך לכלול ענף ותאריך, למשל:\n"
    "כרטיס משחק 23 באוגוסט 2026.jpg (כדורגל)\n"
    "כרטיס משחק כדורסל 24-09-2020.jpg\n"
    "כרטיס משחק כדורעף 08-02-2026.jpg\n"
    "אם אין בשם ענף ותאריך, כתבו אותם בכיתוב של הקובץ, או השיבו לקובץ עם ענף ותאריך."
)
PHOTO_TEXT = "התקבלה תמונה דחוסה. שלחו אותה שוב כקובץ (📎 ← קובץ) כדי שהאיכות תישמר."


@dataclass
class TicketJob:
    chat_id: int
    message_id: int
    file_id: str
    file_name: str
    file_size: int
    hints: list[str] = field(default_factory=list)
    """Texts that may name the sport and date, most trusted first (reply, caption)."""
    question_message_id: int | None = None
    """Set when this job is a press of a sport button: the bot's question message, which
    gets rewritten with the result instead of a new message being sent."""
    callback_id: str | None = None


@dataclass
class Batch:
    jobs: list[TicketJob] = field(default_factory=list)
    notes: dict[int, list[str]] = field(default_factory=dict)
    """Replies that need no processing, per chat (photo refused, help text)."""

    def note(self, chat_id: int, text: str) -> None:
        if text not in self.notes.setdefault(chat_id, []):
            self.notes[chat_id].append(text)


def _job_from_document(message: dict, reply_to_id: int, hints: list[str]) -> TicketJob:
    document = message["document"]
    return TicketJob(
        chat_id=message["chat"]["id"],
        message_id=reply_to_id,
        file_id=document["file_id"],
        file_name=document.get("file_name", ""),
        file_size=document.get("file_size", 0),
        hints=hints,
    )


SPORT_BUTTONS = {Sport.FOOTBALL: "⚽ כדורגל", Sport.BASKETBALL: "🏀 כדורסל", Sport.VOLLEYBALL: "🏐 כדורעף"}
_CALLBACK_PREFIX = "sport"


def sport_buttons(game_date: date) -> list[tuple[str, str]]:
    """One button per sport. The date rides in the button itself (``sport:BASKETBALL:
    2026-09-27``, well under Telegram's 64 bytes), so a press is all the next run needs."""
    return [(label, f"{_CALLBACK_PREFIX}:{sport.name}:{game_date.isoformat()}")
            for sport, label in SPORT_BUTTONS.items()]


def _job_from_button(callback: dict) -> TicketJob | None:
    parts = callback.get("data", "").split(":")
    message = callback.get("message", {})
    if len(parts) != 3 or parts[0] != _CALLBACK_PREFIX or "document" not in message:
        return None
    try:
        sport, game_date = Sport[parts[1]], date.fromisoformat(parts[2])
    except (KeyError, ValueError):
        return None
    job = _job_from_document(message, message["message_id"], [f"{sport.value} {game_date:%d-%m-%Y}"])
    job.question_message_id = message["message_id"]
    job.callback_id = callback["id"]
    return job


def _collect_buttons(updates: list[dict], allowed_user_ids: set[int], batch: Batch) -> None:
    pressed: set[int] = set()
    for update in updates:
        callback = update.get("callback_query")
        if not callback or callback.get("from", {}).get("id") not in allowed_user_ids:
            continue
        job = _job_from_button(callback)
        # Several presses on one question before a run: the first one wins.
        if job and job.question_message_id not in pressed:
            pressed.add(job.question_message_id)  # type: ignore[arg-type]
            batch.jobs.append(job)


def collect(updates: list[dict], allowed_user_ids: set[int]) -> Batch:
    batch = Batch()
    _collect_buttons(updates, allowed_user_ids, batch)
    messages = [
        u["message"] for u in updates
        if "message" in u
        and u["message"].get("chat", {}).get("type") == "private"
        and u["message"].get("from", {}).get("id") in allowed_user_ids
    ]
    # A file answered by a reply in this same batch is handled once, through the reply.
    answered = {m["reply_to_message"]["message_id"] for m in messages
                if "text" in m and "document" in m.get("reply_to_message", {})}

    for message in messages:
        chat_id = message["chat"]["id"]
        if "document" in message:
            if message["message_id"] not in answered:
                hints = [message["caption"]] if message.get("caption") else []
                batch.jobs.append(_job_from_document(message, message["message_id"], hints))
        elif "photo" in message:
            batch.note(chat_id, PHOTO_TEXT)
        elif "text" in message and "document" in message.get("reply_to_message", {}):
            replied = message["reply_to_message"]
            hints = [message["text"]]
            # The sender's own caption still counts; the bot's question caption does not,
            # because its examples are dates.
            own_file = replied.get("from", {}).get("id") == message["from"]["id"]
            if own_file and replied.get("caption"):
                hints.append(replied["caption"])
            job = _job_from_document(replied, message["message_id"], hints)
            if not own_file:
                job.question_message_id = replied["message_id"]
            batch.jobs.append(job)
        else:
            batch.note(chat_id, HELP_TEXT)
    return batch


class Kind(Enum):
    UPLOADED = "✅"
    DUPLICATE = "⏭"
    QUESTION = "❓"
    FAILED = "❌"


@dataclass(frozen=True)
class Outcome:
    kind: Kind
    detail: str
    wiki_name: str = ""
    """Set when the ticket is on the wiki; the summary links it."""
    asked_date: date | None = None
    """For a question: the date is known and only the sport is missing — ask with buttons."""


QUESTION_SUFFIX = (
    "\nהשיבו להודעה הזו עם ענף ותאריך, למשל:\n"
    "כדורגל 23 באוגוסט 2026\nכדורסל 24-09-2020\nכדורעף 08-02-2026"
)
BUTTONS_SUFFIX = (
    "\nבחרו ענף בכפתורים, או השיבו להודעה הזו עם ענף ותאריך אחרים."
    "\nהתשובה תטופל בריצה הבאה של הבוט (עד שעתיים)."
)


def question_caption(outcome: Outcome) -> str:
    return outcome.detail + (BUTTONS_SUFFIX if outcome.asked_date else QUESTION_SUFFIX)


class TicketUploader:
    """Everything that touches the wiki, behind one object so tests can fake it."""

    def __init__(self, dry_run: bool) -> None:
        self._dry_run = dry_run
        self._site = None

    def game_pages_on(self, sport: Sport, game_date: date) -> list[str]:
        return wiki_tickets.game_pages_on(sport, game_date)

    def file_exists(self, file_name: str) -> bool:
        return wiki_tickets.file_exists(file_name)

    def upload(self, file_name: str, data: bytes, text: str) -> None:
        if self._dry_run:
            logger.info("[DRY RUN] would upload %s with %s", file_name, text)
            return
        if self._site is None:
            self._site = get_site()
        wiki_tickets.upload_file(self._site, file_name, data, text, "העלאת כרטיס משחק מבוט הטלגרם")


def process(job: TicketJob, uploader: TicketUploader, download: Callable[[str], bytes]) -> Outcome:
    shown = job.file_name or "(קובץ ללא שם)"
    extension = normalized_extension(job.file_name)
    if extension is None:
        return Outcome(Kind.FAILED, f"{shown}: רק jpg / jpeg / png נתמכים")
    if job.file_size > MAX_DOWNLOAD_BYTES:
        return Outcome(Kind.FAILED, f"{shown}: הקובץ גדול מ-20MB, טלגרם לא מאפשר לבוט להוריד אותו")

    texts = job.hints + ([] if is_device_name(job.file_name) else [job.file_name])
    identity = identify(texts)
    if identity is None:
        return _question(shown, texts)

    pages = uploader.game_pages_on(identity.sport, identity.game_date)
    when = f"{identity.game_date:%d-%m-%Y}"
    if not pages:
        # Buttons again: a wrong sport is fixed with one press; a wrong date by a reply.
        return Outcome(Kind.QUESTION, f"\"{shown}\": אין משחק {identity.sport.value} בתאריך {when}.",
                       asked_date=identity.game_date)
    # Football tickets are tagged by date alone, so a double-header is fine there.
    if len(pages) > 1 and identity.sport is not Sport.FOOTBALL:
        return Outcome(Kind.FAILED, f"{shown}: יש {len(pages)} משחקי {identity.sport.value} ב-{when}, צריך להעלות ידנית")

    wiki_name = canonical_file_name(identity, extension)
    if uploader.file_exists(wiki_name):
        return Outcome(Kind.DUPLICATE, wiki_name, wiki_name)

    uploader.upload(wiki_name, download(job.file_id), tagging_template(identity.sport, pages[0]))
    return Outcome(Kind.UPLOADED, wiki_name, wiki_name)


def _question(shown: str, texts: list[str]) -> Outcome:
    """Say exactly what is missing: a date alone gets sport buttons, anything else asks
    for a text reply with both."""
    found = next((d for d in map(find_date, texts) if d), None)
    if found and not any(map(find_sport, texts)):
        return Outcome(Kind.QUESTION, f"\"{shown}\": התאריך הוא {found.value:%d-%m-%Y}. לאיזה ענף הכרטיס?",
                       asked_date=found.value)
    if found is None:
        return Outcome(Kind.QUESTION, f"\"{shown}\": לא מצאתי תאריך משחק בשם הקובץ או בכיתוב.")
    return Outcome(Kind.QUESTION, f"\"{shown}\": לא זיהיתי את הכרטיס.")


def file_url(file_name: str) -> str:
    return "https://www.maccabipedia.co.il/" + quote("קובץ:" + file_name.replace(" ", "_"))


_HEADINGS = {
    Kind.UPLOADED: "הועלו",
    Kind.DUPLICATE: "כבר היו בוויקי",
    Kind.QUESTION: "ממתינים לתשובה (ראו את ההודעות שנשלחו חזרה)",
    Kind.FAILED: "נכשלו",
}


def _summary_line(outcome: Outcome) -> str:
    if outcome.wiki_name:
        return f'<a href="{file_url(outcome.wiki_name)}">{html.escape(outcome.wiki_name)}</a>'
    return html.escape(outcome.detail)


def summary(outcomes: list[Outcome]) -> str:
    """The per-sender report, as Telegram HTML."""
    sections = []
    for kind, heading in _HEADINGS.items():
        details = [_summary_line(o) for o in outcomes if o.kind is kind]
        if not details:
            continue
        lines = [f"{kind.value} {heading}: {len(details)}"]
        if kind is not Kind.QUESTION:
            lines += [f"‏• {d}" for d in details]
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def _reply_on_the_file(api: TelegramApi, job: TicketJob, outcome: Outcome) -> None:
    """A question is sent as the file itself, so a reply or a button press carries it. When
    the job came from a button, that question message is rewritten in place instead: with
    the result (buttons gone) or with the next question."""
    buttons = sport_buttons(outcome.asked_date) if outcome.asked_date else None
    if job.callback_id:
        api.answer_callback(job.callback_id)
    if job.question_message_id is not None:
        if outcome.kind is Kind.QUESTION:
            caption = question_caption(outcome)
        else:
            caption = f"{outcome.kind.value} {outcome.detail}"
        api.edit_caption(job.chat_id, job.question_message_id, caption, buttons)
    elif outcome.kind is Kind.QUESTION:
        api.send_document(job.chat_id, job.file_id, question_caption(outcome), job.message_id, buttons)


def handle_batch(api: TelegramApi, batch: Batch, uploader: TicketUploader, dry_run: bool) -> None:
    def send(chat_id: int, text: str) -> None:
        if dry_run:
            print(f"[DRY RUN] to {chat_id}:\n{text}\n")
        else:
            api.send_message(chat_id, text)

    outcomes: dict[int, list[Outcome]] = {}
    for job in batch.jobs:
        try:
            outcome = process(job, uploader, api.download)
        except Exception as error:
            logger.exception("Failed on %s", job.file_name)
            outcome = Outcome(Kind.FAILED, f"{job.file_name}: שגיאה בהעלאה ({error})")
        logger.info("%s %s", outcome.kind.name, outcome.detail)
        outcomes.setdefault(job.chat_id, []).append(outcome)
        if dry_run:
            if outcome.kind is Kind.QUESTION:
                print(f"[DRY RUN] would ask about {job.file_name}: {question_caption(outcome)}")
            continue
        try:
            _reply_on_the_file(api, job, outcome)
        except RuntimeError:
            # e.g. "message is not modified" when the same question is asked again; the
            # summary below still reports the outcome.
            logger.warning("Could not update the question for %s", job.file_name, exc_info=True)

    for chat_id in {*batch.notes, *outcomes}:
        notes = [html.escape(n) for n in batch.notes.get(chat_id, [])]
        text = "\n\n".join([*notes, summary(outcomes.get(chat_id, []))]).strip()
        if text:
            send(chat_id, text)


def run(api: TelegramApi, allowed_user_ids: set[int], uploader: TicketUploader, dry_run: bool) -> None:
    """Process waiting messages 100 at a time. Asking for the next page with ``offset``
    confirms the page before it, so a crash re-serves only the unfinished page — and its
    already-uploaded files come back as duplicates, not as second uploads."""
    offset = None
    while updates := api.get_updates(offset=offset):
        logger.info("Processing %d updates", len(updates))
        handle_batch(api, collect(updates, allowed_user_ids), uploader, dry_run)
        if dry_run:
            return
        offset = updates[-1]["update_id"] + 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="identify and look up games, but upload nothing, send nothing and confirm nothing")
    args = parser.parse_args()

    setup_logging(level=logging.INFO)
    allowed = {int(i) for i in os.environ["TELEGRAM_TICKETS_ALLOWED_USER_IDS"].split(",") if i.strip()}
    api = TelegramApi(os.environ["TELEGRAM_TICKETS_BOT_TOKEN"])
    run(api, allowed, TicketUploader(args.dry_run), args.dry_run)


if __name__ == "__main__":
    main()
