"""Post a "what changed" note to the MaccabiPedia Updates Telegram group.

The `maccabipedia-add-feature` skill runs `--check` before any work and sends the note as
its last step. The text is 2-3 lines of Hebrew with bare URLs; it is sent as-is,
HTML-escaped, each line prefixed with a right-to-left mark so Hebrew and URLs read the
same on every Telegram client, and ends with who made the change.

Setup, once per clone: copy `.env.example` to `.env` at the repo root (gitignored; the
worktree hook copies it into every worktree) and fill in:
  TELEGRAM_UPDATES_BOT_TOKEN   the Updates bot's token — ask a maintainer
  TELEGRAM_UPDATES_CHAT_ID     the group's chat id (negative) — ask a maintainer
  MACCABIPEDIA_AUTHOR          your name, as the group should read it

Usage — write the message to a file first (a multi-line argv string needs a multi-line
command, which CLAUDE.md forbids):
  uv run python .claude/scripts/notify_updates.py --check                  # setup is complete
  uv run python .claude/scripts/notify_updates.py --file <path> --dry-run  # print the note
  uv run python .claude/scripts/notify_updates.py --file <path>            # send it
"""
import argparse
import html
import os
import pathlib
import sys

from dotenv import load_dotenv

from maccabipediabot.maintenance.tickets.telegram_api import TelegramApi

REPO = pathlib.Path(__file__).resolve().parents[2]
RIGHT_TO_LEFT_MARK = "‏"
REQUIRED = ("TELEGRAM_UPDATES_BOT_TOKEN", "TELEGRAM_UPDATES_CHAT_ID", "MACCABIPEDIA_AUTHOR")


class SetupError(Exception):
    pass


def format_message(text: str, author: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return ""
    lines.append(f"— {author.strip()}")
    return "\n".join(RIGHT_TO_LEFT_MARK + html.escape(line) for line in lines)


def load_settings() -> tuple[str, int, str]:
    """Token, chat id and author from `.env`; raises SetupError naming what is wrong."""
    load_dotenv(REPO / ".env")
    missing = [name for name in REQUIRED if not os.environ.get(name, "").strip()]
    if missing:
        raise SetupError(f"missing in {REPO / '.env'}: {', '.join(missing)}")
    chat_id = os.environ["TELEGRAM_UPDATES_CHAT_ID"].strip()
    if not chat_id.lstrip("-").isdigit():
        raise SetupError("TELEGRAM_UPDATES_CHAT_ID must be a number")
    return (os.environ["TELEGRAM_UPDATES_BOT_TOKEN"].strip(), int(chat_id),
            os.environ["MACCABIPEDIA_AUTHOR"].strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true",
                        help="verify .env is complete and the bot can reach the group")
    action.add_argument("--file", type=pathlib.Path,
                        help="file holding the message: Hebrew, plain text, bare URLs")
    parser.add_argument("--dry-run", action="store_true", help="print the note, send nothing")
    args = parser.parse_args()

    try:
        token, chat_id, author = load_settings()
    except SetupError as error:
        print(f"STOP: {error}. Setup is in this script's docstring and .env.example.",
              file=sys.stderr)
        return 2

    api = TelegramApi(token)
    if args.check:
        try:
            chat = api.get_chat(chat_id)
        except RuntimeError as error:
            print(f"STOP: the bot cannot reach the group ({error}). Ask a maintainer.",
                  file=sys.stderr)
            return 2
        print(f"ok: posting to '{chat.get('title', chat_id)}' as {author}")
        return 0

    message = format_message(args.file.read_text(encoding="utf-8"), author)
    if not message:
        print(f"nothing to send: {args.file} is empty", file=sys.stderr)
        return 2
    if args.dry_run:
        print(message)
        return 0
    api.send_message(chat_id, message)
    print("sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
