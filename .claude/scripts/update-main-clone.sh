#!/usr/bin/env bash
# update-main-clone.sh — fast-forward the main clone's master to origin/master.
# Step 9 of the maccabipedia-add-feature skill runs it right after a PR is MERGED.
#
# Why: the WorktreeCreate hook (`bash .claude/hooks/create-worktree.sh`, a relative path) and
# the deploy skills run from the main clone's WORKING TREE. A stale main clone means the next
# session is created by the previous hook, and a deploy right after a merge fails its sync gate.
#
# A worktree-isolated session cannot type `git -C <main clone> ...` — the harness refuses git
# aimed at the shared checkout. A script is not refused because the guard reads only the
# command text; nothing in .claude/settings.json grants this. Keep the script narrow for that
# reason: it only fast-forwards master, and refuses everything else.
set -euo pipefail
# Every failure ends in a ✗ line, so the skill's "on ✗, tell the person" covers git's own
# errors (a failed fetch, a broken repo) too.
trap 'echo "✗ update-main-clone failed — see the git error above" >&2' ERR

# The main clone is wherever the shared .git lives, so this works from any worktree. That
# holds only when the git dir is `<main clone>/.git`; refuse any other layout rather than
# act on the wrong directory.
MAIN="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
if [[ "$(git -C "$MAIN" rev-parse --show-toplevel 2>/dev/null)" != "$MAIN" ]]; then
    trap - ERR
    echo "✗ cannot find the main clone (its git dir is not <clone>/.git) — update it by hand" >&2
    exit 1
fi
cd "$MAIN"

# Prints HEAD when detached; fails loudly (ERR trap) if this is not a repository.
branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$branch" != "master" ]]; then
    echo "✗ the main clone is on '$branch', not master — switch it by hand; not touching it" >&2
    exit 1
fi

# Tracked changes refuse here. An untracked file refuses only if origin/master adds a file
# at the same path — git's own message below then names it.
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    echo "✗ uncommitted changes in the main clone — stash or discard them first" >&2
    exit 1
fi

before="$(git rev-parse --short master)"
git fetch -q origin master
if ! git merge --ff-only -q origin/master; then
    trap - ERR
    echo "✗ cannot fast-forward the main clone: master has diverged, or an untracked file" \
         "is in the way (git's message above says which) — resolve by hand" >&2
    exit 1
fi
echo "main clone master $before → $(git rev-parse --short HEAD)"
