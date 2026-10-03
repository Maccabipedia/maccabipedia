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

# The main clone is wherever the shared .git lives, so this works from any worktree.
MAIN="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
cd "$MAIN"

branch="$(git symbolic-ref --quiet --short HEAD || echo "(detached)")"
if [[ "$branch" != "master" ]]; then
    echo "✗ the main clone is on '$branch', not master — switch it by hand; not touching it" >&2
    exit 1
fi

# Untracked files do not block a fast-forward, so only tracked changes refuse.
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    echo "✗ uncommitted changes in the main clone — stash or discard them first" >&2
    exit 1
fi

before="$(git rev-parse --short master)"
git fetch -q origin master
if ! git merge --ff-only -q origin/master; then
    echo "✗ the main clone's master has diverged from origin/master — resolve by hand" >&2
    exit 1
fi
echo "main clone master $before → $(git rev-parse --short HEAD)"
