"""Post a "what changed" note to the MaccabiPedia Updates Telegram group.

The last step of the `maccabipedia-add-feature` skill. The text is 2-3 lines of Hebrew
with bare URLs; it is sent as-is, HTML-escaped, each line prefixed with a right-to-left
mark so Hebrew and URLs read the same on every Telegram client.

Environment (put them in `.claude/settings.json` -> `env`, never in the repo):
  TELEGRAM_UPDATES_BOT_TOKEN   a bot that is a member of the group
  TELEGRAM_UPDATES_CHAT_ID     the group's chat id (negative for groups)

Usage:
  uv run python .claude/scripts/notify_updates.py "<text>"             # send
  uv run python .claude/scripts/notify_updates.py --dry-run "<text>"   # print only
"""
import argparse
import html
import os
import sys

from maccabipediabot.maintenance.tickets.telegram_api import TelegramApi

RIGHT_TO_LEFT_MARK = "‏"


def format_message(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return "\n".join(RIGHT_TO_LEFT_MARK + html.escape(line) for line in lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("text", help="the message, Hebrew, plain text, bare URLs")
    parser.add_argument("--dry-run", action="store_true", help="print the message, send nothing")
    args = parser.parse_args()

    message = format_message(args.text)
    if not message:
        print("nothing to send: the text is empty", file=sys.stderr)
        return 2
    if args.dry_run:
        print(message)
        return 0

    token = os.environ.get("TELEGRAM_UPDATES_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_UPDATES_CHAT_ID")
    if not token or not chat_id:
        print("set TELEGRAM_UPDATES_BOT_TOKEN and TELEGRAM_UPDATES_CHAT_ID (see the docstring)",
              file=sys.stderr)
        return 2

    TelegramApi(token).send_message(int(chat_id), message)
    print("sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
