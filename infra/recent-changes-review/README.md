# Weekly recent-changes review

Once a week a headless Claude (Sonnet) reads the wiki's recent changes and looks for two
things: errors our bots made (a human fixing a bot's page, a bot saving over a human's
edit, reverted bot edits) and facts humans type by hand that our data already holds.

- `prompt.md` — the whole brief. **Edit this file to change what the agent does.** When a
  suggestion is rejected, add the reason to its `MANUAL ON PURPOSE` list so it never returns.
- `run.sh` — runs the prompt from the repo root, and holds the limits on what the agent can do.

## What keeps it safe

The agent reads edit comments, titles and page text that any wiki user can write, so the
prompt's "suggest only" is a request, not a limit. The limits are flags in `run.sh`, each
measured on 2026-09-19 with a probe run from the main checkout:

- `--strict-mcp-config` — without it the main checkout's `.mcp.json` loads the `maccabipedia`
  server with its wiki-write tools (`create_page`, `edit_page`, `upload_file`, as the bot)
  pre-approved: 20 MCP tools. With it: none. The agent only needs the public HTTP API.
- `--disallowedTools` — `gh`, `curl`, git writes and the web tools are refused, and so is
  reading or writing `~/.claude/` (an early run edited Claude's memory, which would let a
  hostile edit persist into later sessions).
- `--max-budget-usd 6`, and scripts left in the cache by an earlier run are deleted, not re-run.

**Not covered:** the agent can still write and run Python, which can read files and open
sockets. Only OS confinement bounds that — the systemd unit should carry `ProtectHome=`-style
options (`InaccessiblePaths=` for `~/.ssh`, pywikibot's `user-password.py`, other repos).

## Scheduling

It runs **locally**, not as a GitHub workflow: it uses the Claude subscription login on the
box. A systemd user timer calls `run.sh` weekly; the units live with the box's other timers,
not in this repo.

## Running it by hand

`bash infra/recent-changes-review/run.sh` — about 10 minutes, $2–4 of usage. It exits
non-zero when no report was written (`claude` itself exits 0 even then).

Everything it writes goes to the gitignored `.cache/recent_changes_review/`:

- `review_<UTC stamp>.md` — the report; the stamp is to the minute, so a second run on one
  day never overwrites the first.
- `message.txt` — written only when there is a suggestion or a live data issue; a short
  plain-text summary for whatever delivers the result. A quiet week writes none.
- `state.json` — where the last run stopped. Missing → a 7-day look-back; delete it to
  replay a window.
- `run_<UTC stamp>.json` — turns, cost and refused tool calls — and the agent's own
  scripts for that run.

## Why `.cache/recent_changes_review/` and not `.claude/tmp/`

Headless `claude -p` refuses every write under `.claude/`, even with `acceptEdits` and an
`Edit(.claude/tmp/**)` allow rule (probed 2026-09-19; the first run spent $0.51 on 12 denied
calls and produced nothing). `.cache` is already gitignored.
