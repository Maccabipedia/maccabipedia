#!/usr/bin/env bash
# Install the daily-digest systemd user timer on this machine (WSL with systemd, linger on).
# Run from the repo: bash infra/daily-digest/install.sh
# Check it with: systemctl --user list-timers maccabipedia-daily-digest.timer
# Run it now:    systemctl --user start maccabipedia-daily-digest.service
# Its log:       journalctl --user -u maccabipedia-daily-digest.service
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"

if [ ! -f "$HOME/code/maccabipedia_mediawikibot/.env" ]; then
    echo "ERROR: the service runs from ~/code/maccabipedia_mediawikibot and needs its .env" >&2
    exit 1
fi

mkdir -p "$UNIT_DIR"
cp "$SCRIPT_DIR/maccabipedia-daily-digest.service" "$SCRIPT_DIR/maccabipedia-daily-digest.timer" "$UNIT_DIR/"
systemctl --user daemon-reload
systemctl --user enable --now maccabipedia-daily-digest.timer
systemctl --user list-timers maccabipedia-daily-digest.timer --no-pager
