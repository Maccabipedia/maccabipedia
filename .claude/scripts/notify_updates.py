"""Post a "what changed" note to the MaccabiPedia Updates Telegram group.

The last step of the `maccabipedia-add-feature` skill. The text is 2-3 lines of Hebrew
with bare URLs; it is sent as-is, HTML-escaped, each line prefixed with a right-to-left
mark so Hebrew and URLs read the same on every Telegram client.

Environment (put them in `.claude/settings.local.json` -> `env`; that file is gitignored,
`.claude/settings.json` is tracked):
  TELEGRAM_UPDATES_BOT_TOKEN   a bot that is a member of the group
  TELEGRAM_UPDATES_CHAT_ID     the group's chat id (negative for groups)

Usage — write the message to a file first (a multi-line argv string needs a multi-line
command, which CLAUDE.md forbids). Several people change the wiki, so the note ends with
who made this change:
  uv run python .claude/scripts/notify_updates.py --file <path> --author <name>             # send
  uv run python .claude/scripts/notify_updates.py --file <path> --author <name> --dry-run   # print
"""
import argparse
import html
import os
import pathlib
import sys

from maccabipediabot.maintenance.tickets.telegram_api import TelegramApi

RIGHT_TO_LEFT_MARK = "‏"


def format_message(text: str, author: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return ""
    lines.append(f"— {author.strip()}")
    return "\n".join(RIGHT_TO_LEFT_MARK + html.escape(line) for line in lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", required=True, type=pathlib.Path,
                        help="file holding the message: Hebrew, plain text, bare URLs")
    parser.add_argument("--author", required=True, help="who made the change; ends the note")
    parser.add_argument("--dry-run", action="store_true", help="print the message, send nothing")
    args = parser.parse_args()

    message = format_message(args.file.read_text(encoding="utf-8"), args.author)
    if not message:
        print(f"nothing to send: {args.file} is empty", file=sys.stderr)
        return 2
    if args.dry_run:
        print(message)
        return 0

    token = os.environ.get("TELEGRAM_UPDATES_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_UPDATES_CHAT_ID", "")
    if not token or not chat_id.lstrip("-").isdigit():
        print("set TELEGRAM_UPDATES_BOT_TOKEN and a numeric TELEGRAM_UPDATES_CHAT_ID "
              "(see the docstring)", file=sys.stderr)
        return 2

    TelegramApi(token).send_message(int(chat_id), message)
    print("sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
