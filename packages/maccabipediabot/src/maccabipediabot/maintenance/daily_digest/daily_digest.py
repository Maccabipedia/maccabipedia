"""Post the daily "what's new on MaccabiPedia" note to the founders' Updates Telegram group.

Collects everything since the last note (wiki recent changes of every kind, new game pages,
merged PRs), has Claude write a short Hebrew summary of it, and posts that. Nothing new, no
message. The window starts where the last sent note ended, capped at a week back, so a day the
machine was off is covered by the next note rather than lost.

The daily schedule lives outside this repo, in one maintainer's personal scheduler, so no
clone posts on its own. Anyone can run it by hand from the repo root:
  uv run python -m maccabipediabot.maintenance.daily_digest.daily_digest --dry-run --hours 24
  uv run python -m maccabipediabot.maintenance.daily_digest.daily_digest
Needs `.env` with TELEGRAM_UPDATES_BOT_TOKEN and TELEGRAM_UPDATES_CHAT_ID (see `.env.example`),
MACCABIPEDIA_BOT_USERNAME in the environment (pywikibot's user-config reads it at import), a
logged-in `claude` CLI, and `gh` for the merged PRs. Without --dry-run it records where the sent
note ended in ~/.local/state/maccabipedia/, so a hand run moves the scheduled window too.
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from maccabipediabot.common.wiki_login import get_site
from maccabipediabot.maintenance.daily_digest.collect import (
    build_activity, fetch_changes, fetch_edit_details, fetch_merged_prs, link_targets, link_urls)
from maccabipediabot.maintenance.daily_digest.render import render_message
from maccabipediabot.maintenance.tickets.telegram_api import TelegramApi

PROMPT_FILE = Path(__file__).with_name("prompt.md")
STATE_FILE = Path.home() / ".local" / "state" / "maccabipedia" / "daily_digest.json"
DEFAULT_WINDOW = datetime.timedelta(days=1)
MAX_WINDOW = datetime.timedelta(days=7)
CLAUDE_MODEL = "sonnet"
CLAUDE_TIMEOUT_SECONDS = 600


def window_start(now: datetime.datetime, state_file: Path) -> datetime.datetime:
    """Where the last sent note ended; a day back on the first run; never more than a week.

    A saved end later than ``now`` (the clock stepped back) gives an empty window rather than
    an inverted one, which the wiki API would refuse on every run until the clock caught up.
    """
    try:
        last_until = datetime.datetime.fromisoformat(json.loads(state_file.read_text())["last_until"])
    except FileNotFoundError:
        return now - DEFAULT_WINDOW
    return min(max(last_until, now - MAX_WINDOW), now)


def save_window_end(until: datetime.datetime, state_file: Path) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({"last_until": until.isoformat()}))


def has_activity(activity: dict) -> bool:
    return bool(activity["total_changes"] or activity["merged_prs"])


def write_digest(activity: dict) -> str:
    """Claude's Hebrew digest. No tools, no project settings: it only reads the prompt."""
    prompt = PROMPT_FILE.read_text(encoding="utf-8") + "\n" + json.dumps(activity, ensure_ascii=False, indent=1)
    with tempfile.TemporaryDirectory() as empty_dir:
        result = subprocess.run(
            ["claude", "-p", "--model", CLAUDE_MODEL, "--tools", "", "--safe-mode",
             "--no-session-persistence", "--output-format", "text"],
            input=prompt, cwd=empty_dir, capture_output=True, text=True,
            timeout=CLAUDE_TIMEOUT_SECONDS)
    if result.returncode != 0:
        raise RuntimeError(f"claude -p failed ({result.returncode}): {result.stderr.strip()[:500]}")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="print the message instead of sending it, and leave the window state alone")
    parser.add_argument("--hours", type=float,
                        help="cover the last N hours instead of the time since the last note")
    parser.add_argument("--save-activity", type=Path, help="also write the collected JSON here")
    args = parser.parse_args()
    logging.basicConfig(format="%(asctime)s : %(levelname)s : %(message)s", level=logging.INFO)
    load_dotenv(find_dotenv(usecwd=True))

    until = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    since = until - datetime.timedelta(hours=args.hours) if args.hours else window_start(until, STATE_FILE)
    if since >= until:
        logging.info(f"Empty window: the last note ended at {since}, after now ({until})")
        return 0
    site = get_site()
    changes = fetch_changes(site, since, until)
    activity = build_activity(changes, fetch_merged_prs(since, until), since, until,
                              fetch_edit_details(site, changes))
    logging.info(f"{activity['total_changes']} changes, {len(activity['new_games'])} new games, "
                 f"{len(activity['merged_prs'])} merged PRs from {since} to {until}")
    if args.save_activity:
        args.save_activity.write_text(json.dumps(activity, ensure_ascii=False, indent=1), encoding="utf-8")

    if not has_activity(activity):
        logging.info("Nothing new; no message")
        if not args.dry_run:
            save_window_end(until, STATE_FILE)
        return 0

    message = render_message(write_digest(activity), link_targets(activity), link_urls(activity))
    if not message:
        raise RuntimeError("Claude returned an empty digest")
    if args.dry_run:
        print(message)
        return 0

    TelegramApi(os.environ["TELEGRAM_UPDATES_BOT_TOKEN"].strip()).send_message(
        int(os.environ["TELEGRAM_UPDATES_CHAT_ID"].strip()), message)
    save_window_end(until, STATE_FILE)
    logging.info("Sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
