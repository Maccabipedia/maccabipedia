#!/usr/bin/env bash
#
# deploy-skin.sh — assemble a ready-to-upload snapshot of the Maccabipedia
# skin (tracked source + vendored assets) at a path OUTSIDE this repo, ready
# to drag into an FTP client and upload to prod.
#
# Fully local: the skin vendors its own banner assets under
# skins/Maccabipedia/assets/, so there is NO prod pull and no special
# permission is needed. The upload itself is MANUAL (FileZilla) — this script
# stops at a snapshot and prints the upload steps.
#
# Each run snapshots into its OWN timestamped directory so previous
# preparations stay around for rollback / audit:
#     <base>/<UTC timestamp with ms>/Maccabipedia/...
#
# Usage:
#   bash deploy-skin.sh                 # default base ~/maccabipedia_skins/
#   bash deploy-skin.sh /path/to/base   # custom output base
#       (use a /mnt/c/... base on WSL if you want the snapshot on the Windows
#        desktop where FileZilla can see it)
#
# Local-only artefact stripped from the snapshot:
#   - .gitattributes (git CRLF/EOL directive — irrelevant on prod)

set -euo pipefail

usage() {
    awk 'NR < 2 { next } /^set -euo pipefail/ { exit } { sub(/^# ?/, ""); print }' "$0"
}

SKIN="Maccabipedia"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"  # scripts → local-wiki → infra → repo

DEFAULT_BASE="${HOME}/maccabipedia_skins"
BASE=""

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        -*) echo "ERROR: unknown flag: $1" >&2; usage >&2; exit 1 ;;
        *)
            if [ -n "$BASE" ]; then
                echo "ERROR: multiple base paths given (got $BASE and $1)" >&2
                exit 1
            fi
            BASE="$1"; shift ;;
    esac
done

BASE="${BASE:-$DEFAULT_BASE}"

case "$BASE" in
    "$REPO_ROOT"|"$REPO_ROOT"/*)
        echo "WARN: base path is inside the repo ($BASE)." >&2
        echo "      That's allowed but defeats the 'outside the repo' intent." >&2
        ;;
esac

src="$REPO_ROOT/skins/$SKIN"
if [ ! -d "$src" ]; then
    echo "ERROR: skin source not found at $src" >&2
    exit 1
fi

# ISO-8601-style UTC timestamp with milliseconds, with `:` swapped for `-` so
# the path is valid on Windows filesystems (relevant when BASE is on /mnt/c/).
# Example: 2026-04-25T07-58-31-742Z
TIMESTAMP="$(date -u +"%Y-%m-%dT%H-%M-%S-%3NZ")"
SNAPSHOT_DIR="${BASE}/${TIMESTAMP}"
out="$SNAPSHOT_DIR/$SKIN"

mkdir -p "$out"

echo "==> assembling $SKIN skin upload snapshot"
echo "    snapshot: $SNAPSHOT_DIR"

# Copy the tracked skin source (cp -a preserves perms/timestamps), then strip
# the git-only .gitattributes that has no purpose on prod.
cp -a "$src/." "$out/"
rm -f "$out/.gitattributes"

# The skin must ship its own vendored assets — there is no prod pull, so an
# empty assets/ means it cannot be packaged.
if [ -z "$(find "$out/assets" -type f 2>/dev/null | head -1)" ]; then
    echo "ERROR: $SKIN ships no assets under skins/$SKIN/assets/." >&2
    echo "  Vendor its banner assets there before packaging it." >&2
    exit 1
fi

echo
echo "==> summary"
printf "    %-18s %s\n" "files:"            "$(find "$out" -type f | wc -l)"
printf "    %-18s %s\n" "size:"             "$(du -sh "$out" | awk '{print $1}')"
printf "    %-18s %s\n" "assets/ binaries:" "$(find "$out/assets" -type f | wc -l)"

# Recent snapshots, so stale ones can be cleaned up at a glance.
existing=$(find "$BASE" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
echo
printf "  %-28s %s\n" "snapshots in $BASE:" "$existing"
if [ "$existing" -gt 1 ]; then
    echo "  recent snapshots:"
    find "$BASE" -mindepth 1 -maxdepth 1 -type d -printf '    %f\n' \
        2>/dev/null | sort -r | head -5
fi

echo
echo "==> next steps for upload (manual, FileZilla)"
echo "  Local snapshot: $out"
echo
echo "  Safest pattern (atomic via remote rename):"
echo "    1. Upload $SKIN/ to /public_html/skins/${SKIN}_new/"
echo "    2. On the FTP server: rename $SKIN -> ${SKIN}_old"
echo "    3. On the FTP server: rename ${SKIN}_new -> $SKIN"
echo "    4. Smoke-test the live site, then delete ${SKIN}_old later."
echo
echo "  Simpler pattern (overwrite in place):"
echo "    Drag the CONTENTS of $out into /public_html/skins/$SKIN/"
echo
echo "  Ensure prod's LocalSettings.php loads the skin and sets it as default:"
echo "      wfLoadSkin('$SKIN');"
echo "      \$wgDefaultSkin = '$SKIN';"
echo "  Metrolook stays loaded as an opt-in fallback (?useskin=metrolook)."
echo
echo "  Smoke test against prod:"
echo "    MACCABIPEDIA_LOCAL_URL=https://www.maccabipedia.co.il \\"
echo "      uv run pytest -m integration infra/local-wiki/tests"
