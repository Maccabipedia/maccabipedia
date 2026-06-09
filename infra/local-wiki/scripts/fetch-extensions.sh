#!/usr/bin/env bash
# Clone every extension in the manifest at its pinned commit into <dest-dir>,
# then strip .git to keep the image small. Run at Docker BUILD time.
#
# This is bash (not Python) on purpose: it runs INSIDE the php:7.4-apache build
# image, which has git + jq but no Python — adding a Python runtime just to clone
# repos would bloat the image. The host-side re-pin tool that DOES have Python
# available is scripts/resolve_extension_pins.py.
#
# Fails loudly on any clone/checkout error — never leaves a partial image that
# would fatal at boot. Network + git + jq required.
#
# Usage: fetch-extensions.sh <manifest.json> <dest-dir>
set -euo pipefail

MANIFEST="${1:?usage: fetch-extensions.sh <manifest.json> <dest-dir>}"
DEST="${2:?usage: fetch-extensions.sh <manifest.json> <dest-dir>}"
mkdir -p "$DEST"

jq -r '.extensions[] | [.name, .repo, .commit] | @tsv' "$MANIFEST" \
| while IFS=$'\t' read -r name repo commit; do
    if [ -z "$commit" ] || [ "$commit" = "RESOLVE" ]; then
        echo "ERROR: $name has no pinned commit — run scripts/resolve_extension_pins.py" >&2
        exit 1
    fi
    target="$DEST/$name"
    echo "==> $name @ $commit ($repo)"
    # Shallow-fetch just the pinned commit — far cheaper than a full clone of
    # repos with large histories (Cargo, PageForms). Some servers (e.g. gerrit)
    # disallow fetching an arbitrary SHA; fall back to a full clone for those.
    git init --quiet "$target"
    git -C "$target" remote add origin "$repo"
    if git -C "$target" fetch --quiet --depth 1 origin "$commit" 2>/dev/null; then
        git -C "$target" checkout --quiet FETCH_HEAD
    else
        rm -rf "$target"
        git clone --quiet "$repo" "$target"
        git -C "$target" checkout --quiet "$commit"
    fi
    # Assert we landed on the exact pin before discarding git metadata.
    got="$(git -C "$target" rev-parse HEAD)"
    if [ "$got" != "$commit" ]; then
        echo "ERROR: $name checked out $got, expected $commit" >&2
        exit 1
    fi
    rm -rf "$target/.git"
done

echo "fetched all extensions into $DEST"
