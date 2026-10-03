---
name: maccabipedia-add-feature
description: Use for ANY change to this repo — a feature, a bug fix, a data fix on the wiki, a template or Lua module, the skin, docs. One path from "someone wants X" to "X is merged, live, and announced". Every change is reviewed by an agent that did not write it, tested on the local wiki before it touches prod, and rolled out one page first.
---

# Add a feature to MaccabiPedia

Follow the steps in order. Each has a check; do not skip to the next without it.
`CLAUDE.md` holds the rules this skill assumes (script execution, `uv run`, commit scopes,
version bumps) and, in its "Lessons Learned", why most of them exist.

## 1. Start from a card

- A Trello card describes the task (`.claude/trello.md`). None? Add one, then start.
  Move it to the in-progress list. Anyone may start; nobody waits for permission.
- Work in a worktree on a feature branch — the hooks in `.claude/hooks/` make it.
- **Check the card's facts before building on them.** "Script X does Y wrong" is a claim;
  reproduce it first. Twice a card's diagnosis was wrong and the right fix was a different one.

## 2. Name the shape of the change

Pick the row. It decides what "tested locally", "gradual" and "look at it" mean below.

| Shape | Local wiki test | Gradual rollout | Look at it |
|---|---|---|---|
| **Bot that writes to the wiki** (uploaders, maintenance jobs, tickets, calendar) | `uv run pytest`; a dry run that prints the exact wikitext diff it would save; render that wikitext on the local wiki (`action=parse`) when it feeds a template | dry run → 1 canary page → 5 → the rest, throttled | the canary page; the diff is a merge, not an overwrite |
| **Template or Lua module** (`infra/lua_modules/`, `.claude/lua_modules.md`) | stub tests + `mutate.py`; deploy to the local wiki and run the `compare_*.py` harness old-vs-new on real pages, small pages included | TemplateSandbox parse on prod (no edit) → `switch_template_prod.py` → purge in batches | one page of each kind the template serves |
| **Skin** (`skins/Maccabipedia/`) | the three test categories in `deploy-skin` | — (that skill) | `Special:Version` + the pages it styles |
| **`LocalSettings.shared.php`** | `deploy-localsettings` | — (that skill) | `validate-site-ok.sh` |
| **`maccabistats`** | `uv run pytest`; prove a new stat against a number you already know is right | version bump + changelog (`CLAUDE.md`) | — |
| **Data fix on prod pages** | prove the current value is wrong from a source (scan, record) before touching it | 1 page → the rest | the page |
| **Docs, knowledge files, CI** | — | — | — |

If the change spans rows, every row applies. Unsure which row? The stricter one.

## 3. Plan in one line

If the shape is already decided (a named bug, one file, a clear card): say the row and a
one-line plan, then build. Brainstorm only when all you know is the area. Nobody asked for
design ceremony on a three-line fix.

## 4. Build, and test it on the local wiki

- Unit tests first (`uv run pytest`, Lua stub tests). Then the row's **local wiki test**.
  The local wiki is `infra/local-wiki/` (`docker compose up -d --build`, then
  `restore-db.sh` for real data). Not set up on this machine? That is one-time bootstrap
  in its README — do it; do not skip the test.
- **No PR without local-wiki evidence.** Paste the harness output or the rendered page's
  URL/screenshot into the PR. Docs/CI rows are the only exemption.
- A harness that never fails proves nothing: make it fail once (`--selftest`, a mutation)
  before trusting its pass. Gate and save the same bytes — do not gate a preview and
  save a different render.
- Never invent wiki data (names, dates, scores). A field you cannot source stays empty or
  `לא ידוע`; see `.claude/maccabipedia_data_edge_cases.md`.

## 5. Review — the person, then the agent

The person driving the session reads the whole diff first (`git diff origin/master...HEAD`),
not a summary of it. Then one call to the `reviewer` agent (`.claude/agents/reviewer.md`);
it cannot spawn agents and does not replace the human read.
Its prompt must carry what it cannot see: the diff command (`git fetch origin && git diff
origin/master...HEAD` — local `master` is stale in a worktree and shows other people's work),
the card text, the row from step 2, and the local-wiki evidence. Answer every finding in
writing — fixed, or refuted with the line that proves it. Then re-run the tests the fix
touched. Do not use `/code-review`; it fans out dozens of agents for a one-line fix.

## 6. Open the PR

- Title = the outcome, in plain words. Squash merges make it the line in history everyone
  reads. Good: "Season pages show the coach for every game". Bad: "fix(season): coach col".
- Description, first five lines: what changes, what could break, the local-wiki evidence,
  what you need from a maintainer (nothing / look at canary / deploy). Details below that.
  It is read on a phone.
- Before opening: level with `origin/master` and no conflicts, `uv run pytest` green.
  After: watch CI; fix and push before telling anyone. No real names or local paths
  anywhere in the PR, commits, or code.

## 7. Roll out gradually (rows that write to prod)

- Run the row's **gradual** column exactly: dry run, then **one** page, open it, then five,
  then the rest with a throttle (`time.sleep(3)` per save; prod returns 508 under load).
  Never two pywikibot processes at once.
- Approval covers only the named action. "Go on the canary" is not "go on the batch".
  A maintainer looks at the canary before the batch runs.
- A maintainer's eye is required on any PR that writes to prod; everything else the author
  merges.

## 8. Merge, deploy, look

- Merge only a commit CI passed *itself*: `gh pr merge --squash --match-head-commit <sha>`.
  A green run from before a force-push belongs to another commit.
- Skin or LocalSettings? Run the deploy skill. The FileZilla upload is a person's job.
- Open the result on the wiki and look at it (row's **look at it** column). Passing tests
  are not the feature.

## 9. Finish

- `gh pr view <n> --json state` says MERGED (`git branch --merged` lies about squashes).
  Delete the branch on remote and local; remove the worktree; move the card to done.
- Learned something not written down? Put it in the right `.claude/*.md` file now.

## 10. Announce in the MaccabiPedia Updates Telegram group

Every change that touched the live wiki is announced there; local-only or docs-only
changes are not. 2–3 lines in Hebrew, plain text, bare URLs: what changed, where, and who
made it. One sender, never both: a session that has the queued sender tool from
`CLAUDE.md` ("Telling … What Changed") uses it; any other session writes the text to a
file and runs `uv run python .claude/scripts/notify_updates.py --file <path> --author
<your name>` (sends at once).
