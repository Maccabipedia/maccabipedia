# Weekly recent-changes review

Every Friday 06:00 a headless Claude (Sonnet) reads the wiki's recent changes and looks for
two things: errors our bots made (a human fixing a bot's page, a bot saving over a human's
edit, reverted bot edits) and facts humans type by hand that our data already holds.

- `prompt.md` — the whole brief. **Edit this file to change what the agent does.** When a
  suggestion is rejected, add the reason to its `MANUAL ON PURPOSE` list so it never returns.
- `run.sh` — runs the prompt from the repo root; result JSON lands in `.cache/recent_changes_review/`.
- `maccabipedia-recent-changes-review.{service,timer}` — systemd user units.

## Install

```
cp infra/recent-changes-review/maccabipedia-recent-changes-review.service infra/recent-changes-review/maccabipedia-recent-changes-review.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now maccabipedia-recent-changes-review.timer
```

Run once by hand: `systemctl --user start maccabipedia-recent-changes-review.service` (about 10 minutes,
$3–4). Replay a window: delete `.cache/recent_changes_review/state.json` (default look-back is 7 days).

## Why `.cache/recent_changes_review/` and not `.claude/tmp/`

Headless `claude -p` refuses every write under `.claude/`, even with `acceptEdits` and an
`Edit(.claude/tmp/**)` allow rule (probed 2026-09-19; the first run spent $0.51 on 12 denied
calls and produced nothing). `.cache` is already gitignored.
