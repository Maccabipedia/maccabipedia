#!/usr/bin/env bash
# Download every extension in the manifest at its pinned commit into <dest-dir>.
# Run at Docker BUILD time. Uses HTTPS commit tarballs (curl) — no git needed,
# the same way the Dockerfile fetches MediaWiki core. The commit SHA is in the
# URL, so the host serves exactly that commit's tree (or 404s).
#
# This is bash (not Python) on purpose: it runs INSIDE the php:7.4-apache build
# image, which has curl + jq but no Python — adding a Python runtime just to
# download tarballs would bloat the image. The host-side re-pin tool that DOES
# have Python available is scripts/resolve_extension_pins.py.
#
# Fails loudly on any download/extract error — never leaves a partial image that
# would fatal at boot. Network + curl + jq required.
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

    # Build the commit-tarball URL per host. GitHub archives wrap everything in a
    # top-level <repo>-<sha>/ dir (strip 1); gerrit gitiles archives have no
    # wrapper dir (strip 0).
    case "$repo" in
        https://github.com/*)
            url="${repo}/archive/${commit}.tar.gz"
            strip=1
            ;;
        https://gerrit.wikimedia.org/r/*)
            path="${repo#https://gerrit.wikimedia.org/r/}"
            url="https://gerrit.wikimedia.org/r/plugins/gitiles/${path}/+archive/${commit}.tar.gz"
            strip=0
            ;;
        *)
            echo "ERROR: $name — don't know how to build an archive URL for $repo" >&2
            exit 1
            ;;
    esac

    target="$DEST/$name"
    mkdir -p "$target"
    echo "==> $name @ $commit ($url)"
    curl -fsSL "$url" | tar -xz --strip-components="$strip" -C "$target"

    # Sanity: a successful extract leaves a non-empty dir. curl -f already fails
    # on a 404 (e.g. a bad SHA), so this catches truncated/empty archives.
    if [ -z "$(ls -A "$target")" ]; then
        echo "ERROR: $name extracted to an empty dir from $url" >&2
        exit 1
    fi
done

echo "fetched all extensions into $DEST"
