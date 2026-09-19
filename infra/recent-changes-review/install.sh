#!/usr/bin/env bash
# Register the weekly review with systemd (user units). Symlinks, not copies: the file in the
# main clone IS the unit, so a merged change to it takes effect on the next daemon-reload and
# the installed unit can never drift from the repo. Safe to re-run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
NAME="maccabipedia-recent-changes-review"

mkdir -p "$UNIT_DIR"
ln -sfn "$SCRIPT_DIR/$NAME.service" "$UNIT_DIR/$NAME.service"
ln -sfn "$SCRIPT_DIR/$NAME.timer" "$UNIT_DIR/$NAME.timer"
systemctl --user daemon-reload
systemctl --user enable --now "$NAME.timer"
systemctl --user list-timers --no-pager "$NAME.timer"
# Without lingering a user timer only runs while you are logged in.
loginctl show-user "$USER" -p Linger
