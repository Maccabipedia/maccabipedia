#!/usr/bin/env bash
# Resolve the symbolic ref (column 3) of extensions.lock to an exact commit SHA
# (column 4) via `git ls-remote`. Run this to create or bump pins. Network req'd.
# Comment/blank lines are preserved verbatim.
set -euo pipefail

LOCK="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/extensions.lock}"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
        ''|\#*) printf '%s\n' "$line" >> "$tmp"; continue ;;
    esac
    IFS=$'\t' read -r name repo ref _ <<< "$line"
    if printf '%s' "$ref" | grep -qiE '^[0-9a-f]{40}$'; then
        # ref is already a full commit SHA (e.g. a pin to a commit that isn't a
        # branch/tag tip — used when REL1_39's tip drops something we need).
        sha="$ref"
    else
        # Resolve against a branch first, then a tag, qualifying the namespace so
        # we never match an unrelated ref. For annotated tags, prefer the peeled
        # commit (^{}) over the tag object.
        sha="$(git ls-remote "$repo" "refs/heads/$ref" | awk 'NR==1{print $1}')"
        if [ -z "$sha" ]; then
            sha="$(git ls-remote "$repo" "refs/tags/$ref^{}" | awk 'NR==1{print $1}')"
            [ -z "$sha" ] && sha="$(git ls-remote "$repo" "refs/tags/$ref" | awk 'NR==1{print $1}')"
        fi
    fi
    if [ -z "$sha" ]; then
        echo "ERROR: could not resolve $name ($repo @ $ref)" >&2
        exit 1
    fi
    printf '%s\t%s\t%s\t%s\n' "$name" "$repo" "$ref" "$sha" >> "$tmp"
    echo "resolved $name -> $sha" >&2
done < "$LOCK"

mv "$tmp" "$LOCK"
trap - EXIT
echo "extensions.lock updated."
