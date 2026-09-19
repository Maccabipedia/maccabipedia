#!/bin/bash
# Weekly MaccabiPedia recent-changes review: headless Claude (Sonnet) run from the repo root.
# Called weekly by a local systemd timer; runs the same way by hand.
# prompt.md beside this file is the source of truth. State and reports go to the repo's
# gitignored .cache/recent_changes_review/, because headless Claude refuses every write
# under .claude/.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="$REPO/.cache/recent_changes_review"
STAMP="$(date +%F)"
CLAUDE="$(command -v claude || echo "$HOME/.local/bin/claude")"

mkdir -p "$OUT"
# The message is per-run; a leftover one would be re-sent on a quiet week.
rm -f "$OUT/message.txt"
cd "$REPO" || exit 1
"$CLAUDE" -p --model sonnet --permission-mode acceptEdits --output-format json \
    < "$HERE/prompt.md" > "$OUT/run_$STAMP.json" 2> "$OUT/run_$STAMP.stderr"
rc=$?
echo "recent-changes-review exit=$rc"
if [ "$rc" -ne 0 ]; then
    tail -20 "$OUT/run_$STAMP.stderr"
fi
exit $rc
