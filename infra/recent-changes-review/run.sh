#!/bin/bash
# Weekly MaccabiPedia recent-changes review: headless Claude (Sonnet) run from the repo root.
# Called weekly by a local systemd timer; runs the same way by hand.
# prompt.md beside this file is the source of truth. State and reports go to the repo's
# gitignored .cache/recent_changes_review/, because headless Claude refuses every write
# under .claude/.
#
# THE FLAGS BELOW ARE THE WALLS, NOT THE PROMPT. The agent reads edit comments, titles and
# page text written by any wiki user, and it can write and run Python. "Suggest only" in
# prompt.md is a request; these are what hold:
#   --strict-mcp-config  no MCP servers at all. The main checkout's .mcp.json would otherwise
#                        load pre-approved wiki-write tools (create_page, edit_page,
#                        upload_file as the bot) and Trello. The agent only needs the HTTP API.
#   --disallowedTools    nothing that publishes (gh, git writes, curl, web tools), and no
#                        reading or writing Claude's own memory — a run did edit it once, and
#                        memory written after reading hostile text persists into later sessions.
#   --max-budget-usd     a run is $2-4; nothing else bounds one.
# What these do NOT stop: Python the agent writes can still read files and open sockets.
# Only OS confinement on the systemd unit bounds that (see README).
set -u
export PATH="$HOME/.local/bin:$PATH"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="$REPO/.cache/recent_changes_review"
# UTC to the minute: the agent names its report from this, so a second run on one day does
# not overwrite the week's report, and a run near midnight cannot disagree about the date.
STAMP="$(date -u +%FT%H%MZ)"

mkdir -p "$OUT"
# The message is per-run; a leftover one would be re-sent on a quiet week.
rm -f "$OUT/message.txt"
# Scripts a previous run left behind are never re-run: a run steered by a hostile edit
# could leave one for next week. The agent rewrites what it needs; reports and state stay.
rm -f "$OUT"/*.py
cd "$REPO" || exit 1
{ echo "REPORT_STAMP=$STAMP"; echo; cat "$HERE/prompt.md"; } | claude -p --model sonnet \
    --permission-mode acceptEdits --output-format json --strict-mcp-config --max-budget-usd 6 \
    --disallowedTools "Bash(gh:*)" "Bash(curl:*)" "Bash(git commit:*)" "Bash(git add:*)" \
        "Bash(git checkout:*)" "Bash(git rebase:*)" "Bash(git config:*)" "Bash(git stash:*)" \
        "Bash(git restore:*)" "Bash(git mv:*)" "Bash(git update-index:*)" "Bash(git branch:*)" \
        "Bash(git worktree:*)" WebFetch WebSearch "Read(~/.claude/**)" "Edit(~/.claude/**)" \
    > "$OUT/run_$STAMP.json" 2> "$OUT/run_$STAMP.stderr"
rc=$?
echo "recent-changes-review exit=$rc"
if [ "$rc" -ne 0 ]; then
    tail -20 "$OUT/run_$STAMP.stderr"
    exit $rc
fi
# claude exits 0 even when every write was refused and nothing was produced.
if [ ! -s "$OUT/review_$STAMP.md" ]; then
    echo "no report written: $OUT/review_$STAMP.md is missing or empty"
    exit 3
fi
# Publish to the reports shelf (served by maccabipedia-reports.service). Rendered by our own
# script, never by the agent: the page quotes text strangers wrote, and the shelf is public.
SHELF="${RECENT_CHANGES_REVIEW_SHELF:-$HOME/served_reports}"
if [ -d "$SHELF" ]; then
    uv run python "$HERE/render_report.py" "$OUT/review_$STAMP.md" "$SHELF/recent_changes_review.html"
else
    echo "no reports shelf at $SHELF; report stays at $OUT/review_$STAMP.md"
fi
