#!/bin/bash
# Weekly MaccabiPedia recent-changes review: headless Claude (Sonnet) run from the repo root.
# prompt.md beside this file is the source of truth. State and reports go to the repo's
# gitignored .cache/rc_review/, because headless Claude refuses every write under .claude/.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="$REPO/.cache/rc_review"
STAMP="$(date +%F)"

mkdir -p "$OUT"
cd "$REPO" || exit 1
"$HOME/.local/bin/claude" -p --model sonnet --permission-mode acceptEdits --output-format json \
    < "$HERE/prompt.md" > "$OUT/run_$STAMP.json" 2> "$OUT/run_$STAMP.stderr"
rc=$?
echo "rc-review exit=$rc result=$OUT/run_$STAMP.json"
exit $rc
