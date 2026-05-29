#!/usr/bin/env bash
#
# prepare-skin-for-upload.sh — assemble one or both MaccabiPedia skins
# (vendored source + binary banner assets) at a path OUTSIDE this repo,
# ready to drag into an FTP client and upload to prod.
#
# Each run snapshots into its OWN timestamped directory so previous
# preparations stay around for rollback / audit:
#
#     <base>/<UTC timestamp with ms>/{Metrolook,Maccabipedia}/...
#
# Default base: ~/maccabipedia_skins/
# Override:     ./prepare-skin-for-upload.sh /path/to/output-base
#               (use a /mnt/c/... base on WSL if you want the snapshots
#               on the Windows desktop where FileZilla can see them)
#
# Skin selection (flag is positional-friendly — order doesn't matter):
#     --skin=maccabipedia  (default) — the Maccabipedia skin
#     --skin=metrolook     the legacy skin (deprecated)
#     --skin=both          both
#
# What goes into each skin's snapshot directory:
#   <repo-root>/skins/<Name>/   — tracked source, including its vendored
#                                 assets/ (each skin ships its own; there is
#                                 NO prod pull). A skin with an empty assets/
#                                 cannot be packaged.
#
# Local-only artefacts stripped per snapshot:
#   - .gitkeep (assets/ mountpoint marker)
#   - .gitattributes (git CRLF/EOL directive — irrelevant on prod)

set -euo pipefail

usage() {
    awk 'NR < 2 { next } /^set -euo pipefail/ { exit } { sub(/^# ?/, ""); print }' "$0"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_WIKI_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${LOCAL_WIKI_DIR}/../.." && pwd)"

DEFAULT_BASE="${HOME}/maccabipedia_skins"
BASE=""
SKIN_SELECTION="maccabipedia"

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --skin=metrolook|--skin=maccabipedia|--skin=both)
            SKIN_SELECTION="${1#--skin=}"; shift ;;
        --skin=*)
            echo "ERROR: --skin must be one of: metrolook, maccabipedia, both" >&2
            exit 1 ;;
        -*)        echo "ERROR: unknown flag: $1" >&2; usage >&2; exit 1 ;;
        *)
            if [ -n "$BASE" ]; then
                echo "ERROR: multiple base paths given (got $BASE and $1)" >&2
                exit 1
            fi
            BASE="$1"; shift
            ;;
    esac
done

BASE="${BASE:-$DEFAULT_BASE}"

case "$BASE" in
    "$REPO_ROOT"|"$REPO_ROOT"/*)
        echo "WARN: base path is inside the repo ($BASE)." >&2
        echo "      That's allowed but defeats the 'outside the repo' intent." >&2
        ;;
esac

# Resolve which skin(s) to package.
case "$SKIN_SELECTION" in
    both)         skins=( Metrolook Maccabipedia ) ;;
    metrolook)    skins=( Metrolook ) ;;
    maccabipedia) skins=( Maccabipedia ) ;;
esac

# Verify every requested skin's source exists.
for skin in "${skins[@]}"; do
    if [ ! -d "$REPO_ROOT/skins/$skin" ]; then
        echo "ERROR: skin source not found at $REPO_ROOT/skins/$skin" >&2
        exit 1
    fi
done

# ISO-8601-style UTC timestamp with milliseconds, with `:` swapped for `-`
# so the path is valid on Windows filesystems (relevant when BASE is on
# /mnt/c/...). Example: 2026-04-25T07-58-31-742Z
TIMESTAMP="$(date -u +"%Y-%m-%dT%H-%M-%S-%3NZ")"
SNAPSHOT_DIR="${BASE}/${TIMESTAMP}"

mkdir -p "$SNAPSHOT_DIR"

echo "==> assembling skin upload snapshot"
echo "    skins:    ${skins[*]}"
echo "    snapshot: $SNAPSHOT_DIR"

for skin in "${skins[@]}"; do
    src="$REPO_ROOT/skins/$skin"
    out="$SNAPSHOT_DIR/$skin"

    mkdir -p "$out"

    # Copy the tracked skin source. cp -a preserves perms and timestamps.
    cp -a "$src/." "$out/"

    # Strip git-only directives that have no purpose on prod.
    rm -f "$out/assets/.gitkeep" "$out/.gitattributes"

    # The skin must ship its own assets (vendored under skins/<Name>/assets/).
    # There is no prod pull — an empty assets/ means the skin can't be packaged.
    if [ -z "$(find "$out/assets" -type f 2>/dev/null | head -1)" ]; then
        echo "ERROR: skin '$skin' ships no assets under skins/$skin/assets/." >&2
        echo "  Vendor its banner assets there before packaging it." >&2
        exit 1
    fi
    echo "    $skin: using vendored assets (skins/$skin/assets)"
done

echo
echo "==> summary"
for skin in "${skins[@]}"; do
    out="$SNAPSHOT_DIR/$skin"
    printf "  [%s]\n" "$skin"
    printf "    %-30s %s\n" "files:"   "$(find "$out" -type f | wc -l)"
    printf "    %-30s %s\n" "size:"    "$(du -sh "$out" | awk '{print $1}')"
    printf "    %-30s %s\n" "assets/ binary count:" \
        "$(find "$out/assets" -type f 2>/dev/null | wc -l)"
done

# Show the few most recent snapshots so the user can see history at a
# glance (and remember to clean old ones up if too many accumulate).
existing=$(find "$BASE" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
echo
printf "  %-32s %s\n" "snapshots in $BASE:" "$existing"
if [ "$existing" -gt 1 ]; then
    echo "  recent snapshots:"
    find "$BASE" -mindepth 1 -maxdepth 1 -type d -printf '    %f\n' \
        2>/dev/null | sort -r | head -5
fi

echo
echo "==> next steps for upload"
echo "  Local snapshot: $SNAPSHOT_DIR"
echo
for skin in "${skins[@]}"; do
    echo "  $skin → /public_html/skins/$skin/"
done
echo
echo "  Safest pattern (atomic via remote rename, repeat per skin):"
echo "    1. Upload <skin>/ to /public_html/skins/<skin>_new/"
echo "    2. On the FTP server: rename <skin> → <skin>_old"
echo "    3. On the FTP server: rename <skin>_new → <skin>"
echo "    4. Smoke-test the live site, then delete <skin>_old later."
echo
echo "  Simpler pattern (overwrite in place, repeat per skin):"
echo "    Drag the CONTENTS of $SNAPSHOT_DIR/<skin> into /public_html/skins/<skin>/"
echo
if [[ " ${skins[*]} " == *" Maccabipedia "* ]]; then
    echo "  After uploading Maccabipedia for the first time, also update"
    echo "  prod's LocalSettings.php — add (keep \$wgDefaultSkin unchanged):"
    echo "      wfLoadSkin('Maccabipedia');"
    echo "  Maccabipedia is then opt-in via ?useskin=maccabipedia and"
    echo "  Special:Preferences. Flip the default in a follow-up after soak."
    echo
fi
echo "  Smoke test against prod:"
echo "    MACCABIPEDIA_LOCAL_URL=https://www.maccabipedia.co.il \\"
echo "      uv run pytest -m integration infra/local-wiki/tests"
