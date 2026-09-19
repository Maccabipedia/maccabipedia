You are reviewing MaccabiPedia's recent wiki edits to find improvements to OUR automation
(this repo: packages/maccabipediabot, packages/maccabistats, packages/maccabipedia-mcp,
.github/workflows). You suggest; you change nothing. No wiki edits, no code edits, no PRs.
Follow CLAUDE.md throughout (scripts in files run with `uv run`, no inline python, no
heredocs).

You run HEADLESS: nobody can approve a prompt, and a question gets no answer.
- Every file you create goes in `.cache/recent_changes_review/` (gitignored). That OVERRIDES
  CLAUDE.md's `.claude/tmp/` convention: writes under `.claude/` are refused here.
- One command per Bash call. No `&&`, `|`, `;` or redirection — put logic in a script.
- MACCABIPEDIA_UA_SCRIPT is already in your environment. Read it with os.environ inside
  the script; do not inspect it from the shell.
- Stay inside this repo and the wiki API. Do not read other worktrees, `/mnt/`, Google
  Drive or source-data folders; if the cause lives outside the repo, say where and stop.
- Scripts already in `.cache/recent_changes_review/` from earlier runs are yours to reuse. Run them
  before writing new ones; rewrite one only if it fails.
- If a tool call is refused, do not retry variants or probe the permission system. Do it
  another allowed way once; if that fails too, skip that step and say so in the report.

1. WINDOW. Read .cache/recent_changes_review/state.json for `last_run_utc`. Missing → look
   back 7 days. Review from that instant to now.

2. FETCH. Write a script in .cache/recent_changes_review/ that pages
   https://www.maccabipedia.co.il/api.php?action=query&list=recentchanges
   (rcprop=title|user|timestamp|comment|sizes|tags|ids|loginfo, rclimit=500, follow
   `rccontinue` until the window is covered), sends the MACCABIPEDIA_UA_SCRIPT user agent,
   checks status 200 and a JSON content type before parsing, saves the full JSON to
   .cache/recent_changes_review/, and prints only counts: by user, by namespace, by title prefix, by
   comment (first 60 chars), by tag.
   The `bot` flag is useless here: MaccabiBot is not bot-flagged. Classify by username.
   Automated = `MaccabiBot`, `MaccabipediaSpecialAgent` (our upload scripts: basketball
   tickets, clippings, court pages) and `יוצר הקטגוריות האוטומטי` (the AutoCreateCategoryPages
   extension; ignore it). Every other account is a human.

3. LOOK FOR THESE SIGNALS, in this order of value:
   a. A human edit to a page AFTER a MaccabiBot edit of the same page. Fetch both
      revisions (prop=revisions, rvslots=main) and diff them. What the human fixed is
      what the bot got wrong.
      The reverse too: a MaccabiBot edit AFTER a human edit of the same page. Check the
      bot did not save stale text over the human's change. If it did, the live page is
      wrong now — that is a LIVE DATA ISSUE (step 5), whatever the count.
   b. MaccabiBot edits tagged `mw-reverted`, or MaccabiBot runs whose comment says it is
      repairing earlier output. Find which run produced the bad data and why.
   c. The same human edit repeated across many pages: identical or templated comments,
      ReplaceText runs ("החלפת טקסט"), same-shaped size deltas on same-prefix titles.
      Either a generator emits something wrong upstream, or it is manual toil a bot
      could do.
      Do NOT find these by grouping on the edit comment alone — some of the most
      active editors never write one, and a comment-ranked run skips them entirely
      (it happened on the first 90-day run). For EVERY human account, group their edits by title prefix / page, and
      for each group of 10 or more edits read at least 3 diffs (action=compare) before
      deciding what the work is. Then ask: which parts of what they typed are facts our
      data already holds (maccabistats, Cargo tables: scorers, records, counts, results)?
      Prose is theirs; a number a query could have produced is a candidate.
   d. Humans hand-creating a kind of page that a bot already creates for another sport.
      Football is the reference implementation; check volleyball and basketball for the gap.
   e. Edits in the Template (תבנית) and Module (יחידה) namespaces. Diff them, then grep
      the repo for the template and parameter names: a renamed or new parameter means
      bot code that emits that template is now stale.

   MANUAL ON PURPOSE — the maintainers have ruled these out; never suggest automating them:
   - Edits by the user `Ticketmaster`: clipping uploads and their `{{תיוג עיתונים}}`
     tagging, historical game data, stub pages. This is hand research by design. Never
     propose automating it. These edits still count for ONE thing: signal (a), a
     correction to a page MaccabiBot wrote, because that is a bot error. The same manual
     work by any other user is still a candidate.
   - Historical research. When a human adds facts they found by reading a source — a
     clipping, an archive, an old season's game (e.g. assistant-referee names for
     2006/07, and the one-line `כדורגל:<name> (שופט)` pages opened for them) — the edit
     IS the work; no machine had that data. Ask of every
     candidate: could a bot have known this without a person reading something? If not,
     drop it. Candidates live where data arrives from a crawled or structured source.
   A rejected suggestion gets added here, with the reason.

4. VERIFY EVERY CANDIDATE before it becomes a suggestion. Drop it if any step fails:
   - You read the actual diff, not just the comment or the size delta.
   - You found the code responsible and can cite it as path:line, or, for a new
     automation, the closest existing module it would sit beside.
   - `git log` since the edit does not already fix it.
   - The code will RUN AGAIN and hit the same problem: a scheduled workflow in
     .github/workflows, or a bot that is run routinely. A one-off import or backfill
     script (most of `maintenance/`, anything new whose batch has already been uploaded)
     whose output a human then tidied once is finished business — a fix there saves
     nobody anything. Check `git log` on the file: new and run once → drop it.
   - No open card already covers it: `uv run python .claude/scripts/trello_list.py <listId>`
     for Backlog, Next Up and In Progress (see .claude/trello.md).
   Say how many pages and edits back each candidate, then sort it:
   - SUGGESTION: 3 or more edits of the same shape, all four checks passed.
   - LEAD: fewer than 3, or a check you could not complete. Report only, never a card.
   - LIVE DATA ISSUE: a page that is wrong right now because of automation. Any count.
   Use Grep on .claude/maccabipedia_structure_knowledge.md for template and Cargo facts;
   never read it whole.

5. REPORT. Write .cache/recent_changes_review/review_<YYYY-MM-DD>.md. Open with "Live data issues"
   (page, revision ids, what is wrong now, the one-line fix) or "none". Then "Suggestions",
   then "Leads" (two lines each). Per suggestion:
   - Title: the change to make, as an imperative
   - Evidence: count, 2–3 example page titles with revision ids, the diff excerpt
   - Where: path:line in this repo
   - Proposed change: two or three sentences, no code
   - Size: small / medium / large, and what could go wrong
   Order by (edits it would have saved) × (confidence). Then a short "Looked at, not
   suggesting" list with one line each, so the next run does not redo it.
   Zero suggestions is a valid result. Do not pad.

6. FILE. THIS IS A DRY RUN: do NOT create, move or comment on any Trello card. Trello is
   read-only for this run. Instead, end the report with a "Cards I would file" section:
   the title `[Recent changes] <title>` for each.

7. STATE. Only after the report is written, set `last_run_utc` in
   .cache/recent_changes_review/state.json to the timestamp of the NEWEST change you
   fetched, not the wall clock.

8. FINAL MESSAGE, at most 6 lines: any live data issue FIRST, then window covered, number of changes read, number of
   suggestions, the top one in a sentence, the report path.
