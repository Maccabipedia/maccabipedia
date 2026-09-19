# Weekly recent-changes review

Once a week a headless Claude (Sonnet) reads the wiki's recent changes and looks for two
things: errors our bots made (a human fixing a bot's page, a bot saving over a human's
edit, reverted bot edits) and facts humans type by hand that our data already holds.

- `prompt.md` — the whole brief. **Edit this file to change what the agent does.** When a
  suggestion is rejected, add the reason to its `MANUAL ON PURPOSE` list so it never returns.
- `run.sh` — runs the prompt from the repo root.

## Scheduling

It runs **locally**, not as a GitHub workflow: it uses the Claude subscription login on the
box. A systemd user timer calls `run.sh` weekly; the units live with the box's other timers,
not in this repo.

## Running it by hand

`bash infra/recent-changes-review/run.sh` — about 10 minutes, $2–4 of usage.

Everything it writes goes to the gitignored `.cache/recent_changes_review/`:

- `review_<date>.md` — the report.
- `message.txt` — written only when there is a suggestion or a live data issue; a short
  plain-text summary for whatever delivers the result. A quiet week writes none.
- `state.json` — where the last run stopped. Missing → a 7-day look-back; delete it to
  replay a window.
- the agent's own fetch scripts, reused by later runs, and `run_<date>.json` (turns, cost,
  refused tool calls).

## Why `.cache/recent_changes_review/` and not `.claude/tmp/`

Headless `claude -p` refuses every write under `.claude/`, even with `acceptEdits` and an
`Edit(.claude/tmp/**)` allow rule (probed 2026-09-19; the first run spent $0.51 on 12 denied
calls and produced nothing). `.cache` is already gitignored.
