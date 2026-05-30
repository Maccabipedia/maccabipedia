#!/usr/bin/env bash
#
# check-skin-version-bump.sh — fail if skins/Maccabipedia/ changed versus a
# base ref but skins/Maccabipedia/skin.json "version" was NOT bumped.
#
# Intended for the pull_request CI gate (base = origin/<PR base>), but runnable
# locally for a sanity check:
#     bash check-skin-version-bump.sh [base-ref]   # default base: origin/master
#
# Requires: git, jq.
set -euo pipefail

BASE="${1:-origin/master}"
SKIN_DIR="skins/Maccabipedia"
SKIN_JSON="$SKIN_DIR/skin.json"

if git diff --quiet "$BASE"...HEAD -- "$SKIN_DIR"; then
    echo "No changes under $SKIN_DIR vs $BASE — version bump not required."
    exit 0
fi

base_version="$(git show "$BASE:$SKIN_JSON" | jq -r '.version')"
head_version="$(jq -r '.version' "$SKIN_JSON")"

if [ "$base_version" = "$head_version" ]; then
    echo "::error::$SKIN_DIR changed but $SKIN_JSON \"version\" is still $head_version — bump it." >&2
    exit 1
fi

echo "skin.json version bumped: $base_version -> $head_version"
