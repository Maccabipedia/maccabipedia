#!/usr/bin/env bash
#
# Put a run's images on the visual-diffs branch and post (or update) the one
# before/after comment on the pull request. Called by visual_diff.yaml.
#
#   publish.sh <images dir> <path on the branch> <PR number>
#
# Needs GH_TOKEN (contents: write, pull-requests: write) and GITHUB_REPOSITORY.
# GitHub has no API for attaching an image to a comment, so the images live on
# an orphan branch of this public repo and the comment points at their raw
# URLs. Each run adds a folder; nothing on the branch is ever rewritten, so
# the images in older comments keep working.
set -euo pipefail

IMAGES="$(cd "$1" && pwd)"
DEST="$2"
PR="$3"
BRANCH=visual-diffs
MARKER='<!-- visual-diff -->'

if compgen -G "${IMAGES}/*.jpg" >/dev/null; then
    WORK="$(mktemp -d)"
    git -C "$WORK" init -q
    git -C "$WORK" config user.name "github-actions[bot]"
    git -C "$WORK" config user.email "41898282+github-actions[bot]@users.noreply.github.com"
    git -C "$WORK" remote add origin "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"

    # Another PR's run may push between our fetch and our push; start again
    # from the branch as it now is, rather than rebasing a shallow history.
    for attempt in 1 2 3 4 5; do
        if git -C "$WORK" fetch -q --depth 1 origin "$BRANCH"; then
            git -C "$WORK" checkout -q -B "$BRANCH" FETCH_HEAD
        else
            git -C "$WORK" checkout -q --orphan "$BRANCH"
        fi
        mkdir -p "${WORK}/${DEST}"
        cp "${IMAGES}"/*.jpg "${WORK}/${DEST}/"
        git -C "$WORK" add -A
        git -C "$WORK" commit -q -m "Before/after images for PR #${PR} (${DEST})"
        if git -C "$WORK" push -q origin "$BRANCH"; then
            break
        fi
        if [ "$attempt" = 5 ]; then
            echo "could not push the images after 5 attempts" >&2
            exit 1
        fi
        sleep $((attempt * 3))
    done
fi

EXISTING="$(gh api --paginate "repos/${GITHUB_REPOSITORY}/issues/${PR}/comments" \
    --jq ".[] | select(.user.login == \"github-actions[bot]\" and (.body | startswith(\"${MARKER}\"))) | .id" \
    | head -n 1)"
if [ -n "$EXISTING" ]; then
    gh api -X PATCH "repos/${GITHUB_REPOSITORY}/issues/comments/${EXISTING}" \
        -F "body=@${IMAGES}/comment.md" --jq .html_url
else
    gh api "repos/${GITHUB_REPOSITORY}/issues/${PR}/comments" \
        -F "body=@${IMAGES}/comment.md" --jq .html_url
fi
