#!/usr/bin/env bash
# Clone every extension listed in the manifest at its pinned commit into
# <dest-dir>, then strip .git to keep the image small. Run at Docker build time.
# Fails loudly on any clone/checkout error — never leaves a partial image that
# would fatal at boot. Network + git required.
#
# Usage: fetch-extensions.sh <manifest> <dest-dir>
set -euo pipefail

MANIFEST="${1:?usage: fetch-extensions.sh <manifest> <dest-dir>}"
DEST="${2:?usage: fetch-extensions.sh <manifest> <dest-dir>}"
mkdir -p "$DEST"

while IFS=$'\t' read -r name repo ref commit || [ -n "$name" ]; do
    case "$name" in
        ''|\#*) continue ;;
    esac
    if [ -z "${commit:-}" ] || [ "$commit" = "RESOLVE" ]; then
        echo "ERROR: $name has no pinned commit — run resolve-extension-pins.sh" >&2
        exit 1
    fi
    target="$DEST/$name"
    echo "==> $name @ $commit ($repo)"
    git clone --quiet "$repo" "$target"
    git -C "$target" checkout --quiet "$commit"
    rm -rf "$target/.git"
done < "$MANIFEST"

echo "fetched all extensions into $DEST"
