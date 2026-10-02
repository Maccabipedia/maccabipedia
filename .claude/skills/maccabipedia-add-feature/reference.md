# Why the rules in SKILL.md exist

Steps live in `SKILL.md`. This file is the history behind the ones that cost something.
Add a line here only when a rule was learned the hard way; keep it to one paragraph.

**Check the card's facts first.** A card said a video tool "only reaches 360p"; the real
state was "it reaches nothing", which is a different fix. Measuring before building saved a
day twice.

**Local wiki for everything.** Prod has no undo for a template switch: every page that
transcludes it re-renders on the next view. The local wiki (`infra/local-wiki/`) boots with a
real database snapshot, so a harness can compare old-vs-new on real pages, including the
small and odd ones that break first. Harnesses that sampled only big pages missed a trim the
parser applies to stubs.

**Make the harness fail once.** A comparison harness that passed 10 of 18 mutations once
was trusted anyway; the real review of a module found nine defects the harness never saw.
`--selftest` and `mutate.py` exist so a green run means something.

**Gate and save the same bytes.** A gate that previews one render and a save that writes
another let a wrong page through. Whatever is gated is what is saved.

**One page, then five, then the rest.** A batch of 232 game pages was audited after an
uploader overwrote fields instead of merging them. One canary page, opened and read, would
have shown it. Prod also returns 508 under a tight loop, so batches sleep between saves.

**Approval covers only the named action.** "Yes, do the canary" was once read as "yes, do
all of them". It is not.

**Independent reviewer, one agent.** On two PRs the isolated reviewer found blockers the
author had argued themselves out of, including a test run that would have written to prod.
Claude Code's `/code-review` spawned dozens of agents for a one-line change; the repo's
`reviewer` agent cannot delegate, so the tree stays one level deep.

**Merge the commit CI passed.** `--match-head-commit` makes GitHub refuse the merge if the
branch moved after you checked it. A green check from before a force-push is for a commit
that no longer exists.

**PR title is the outcome.** With squash merges the title is the only line of history most
people read. "fix(season): coach col" tells a reader nothing a year later.

**No names, no local paths.** The repo, the wiki, and PR text are public. People's names,
home-directory paths, and tokens do not go there; see the ticket bot's env-var pattern for
secrets.

**Telegram at the end, not before.** The Updates group reaches people outside the session.
Progress notes and questions do not go there; only "this changed, here is the link", once
the change is live and looked at.
