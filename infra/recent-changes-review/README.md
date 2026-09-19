# Weekly recent-changes review

Once a week a headless Claude (Sonnet) reads the wiki's recent changes and looks for two
things: errors our bots made (a human fixing a bot's page, a bot saving over a human's
edit, reverted bot edits) and facts humans type by hand that our data already holds.

- `prompt.md` — the whole brief. **Edit this file to change what the agent does.** When a
  suggestion is rejected, add the reason to its `MANUAL ON PURPOSE` list so it never returns.
- `run.sh` — runs the prompt from the repo root, and holds the limits on what the agent can do.
- `render_report.py` — after each run, `run.sh` renders the report to
  `~/served_reports/recent_changes_review.html` on the reports shelf
  (`maccabipedia-reports.service`). Our script renders it, not the agent, with raw HTML
  escaped: the page quotes text strangers wrote, and the shelf is public.

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

The agent can still write and run Python, and no Claude flag governs what that Python does.
The systemd unit does: `InaccessiblePaths=` hides `~/.ssh`, `~/.secrets`, `gh`'s token, this
repo's `.mcp.json`, `infra/local-wiki/.env` and pywikibot's `user-password.py`, the other
projects on the box and the Windows user folders. Probed under the full list: claude starts,
`uv run` works, a write into `.cache/` lands, and the hidden paths cannot be listed.

**Not covered:** the network is open (the job needs the wiki API), so whatever the agent can
still read it could send. And running `run.sh` by hand gets the flags but not the unit's
confinement.

## Scheduling

It runs **locally**, not as a GitHub workflow: it uses the Claude subscription login on the
box. A systemd user timer (`maccabipedia-recent-changes-review.timer`, Fridays 06:00,
persistent) starts the service, which runs `run.sh` from the main clone.

Register it once, from the main clone: `bash infra/recent-changes-review/install.sh`. It
symlinks the two unit files into `~/.config/systemd/user/`, so the file in the repo is the
unit — a merged change takes effect after `systemctl --user daemon-reload`. Start a run now
with `systemctl --user start maccabipedia-recent-changes-review.service`.

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
