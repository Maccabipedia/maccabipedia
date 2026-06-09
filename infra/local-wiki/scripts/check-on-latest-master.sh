#!/usr/bin/env bash
#
# check-on-latest-master.sh — deploy sync gate. Verify the working tree is clean
# and the branch is NOT behind origin/master, so a deploy ships exactly what is
# committed on master (master is the source of truth). Used by the deploy-skin
# and deploy-localsettings skills.
#
# Usage: bash check-on-latest-master.sh
# Exit:  0 = clean + up to date; non-zero = do not deploy.
set -euo pipefail

git fetch origin

if [ -n "$(git status --porcelain)" ]; then
    echo "ERROR: working tree is dirty — commit or stash before deploying." >&2
    git status --short >&2
    exit 1
fi

behind="$(git rev-list --count HEAD..origin/master)"
if [ "$behind" -ne 0 ]; then
    echo "ERROR: branch is $behind commit(s) behind origin/master — rebase/merge first." >&2
    exit 1
fi

echo "OK: clean working tree, up to date with origin/master."
