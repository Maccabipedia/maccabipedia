#!/usr/bin/env bash
#
# Download wiki PAGES (content) from the production MaccabiPedia site over HTTP
# (Special:Export) into the gitignored infra/local-wiki/downloaded-pages/ dir,
# for optionally seeding real content into the local wiki. NOT needed to render
# or verify the skin — extensions are baked into the Docker image and the skin's
# assets (incl. favicon) are vendored in the repo. Import the result with
# ./seed-content.sh.
#
# Read-only: only fetches page XML via Special:Export; no writes to prod.
# Every invocation appends a timestamped line to DOWNLOAD_LOG.
#
# Optional env:
#   MACCABIPEDIA_WEB_URL  — public site base URL (default: https://maccabipedia.co.il)
#
# Usage:
#   ./download-pages-from-prod.sh <op> [args...]
#
# Allowed <op> values:
#   bootstrap                — download the optional CONTENT for local dev setup:
#                              site-scripts + pages (using
#                              scripts/content-manifests/starter.manifest).
#                              Doesn't touch docker — run `docker compose up -d
#                              --build` and `./scripts/seed-content.sh` after.
#   site-scripts             — download MediaWiki:Common.css + MediaWiki:Common.js
#                              via Special:Export. Common.css backs the
#                              site.styles ResourceLoader bundle; Common.js
#                              carries CanvasJS chart hooks, jump-to-id
#                              scrolling, and the fanzine email form. Output:
#                              downloaded-pages/site-scripts.xml.
#   pages <manifest>         — download page wikitext via Special:Export for
#                              every title in <manifest> (one title per line;
#                              blanks and lines starting with '#' ignored).
#                              Templates referenced by the pages are included
#                              automatically. Output:
#                              downloaded-pages/<manifest-stem>.xml (MW XML dump)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_WIKI_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOWNLOAD_DIR="${LOCAL_WIKI_DIR}/downloaded-pages"

REPO_ROOT="$(cd "${LOCAL_WIKI_DIR}/../.." && pwd)"
DOWNLOAD_LOG="${REPO_ROOT}/.claude/tmp/page-download.log"

# Auto-load local .env if present (gitignored). Only MACCABIPEDIA_WEB_URL is
# honored here; other vars in the file are set but unused by this script.
ENV_FILE="${LOCAL_WIKI_DIR}/.env"
if [ -f "$ENV_FILE" ]; then
    echo "==> sourcing ${ENV_FILE}"
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

usage() {
    # Print the script's leading comment block (everything from line 2 up to
    # but not including the first non-comment statement). Sentinel-based so
    # adding/removing op docs above doesn't silently truncate --help.
    awk 'NR < 2 { next } /^set -euo pipefail/ { exit } { sub(/^# ?/, ""); print }' "$0"
}

log_event() {
    mkdir -p "$(dirname "$DOWNLOAD_LOG")"
    printf '%s  %s  url=%s  local=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        "$1" "$2" "${3:-}" \
        >> "$DOWNLOAD_LOG"
}

# Args: $1 = output stem (downloaded-pages/<stem>.xml)
#       $2 = path to a titles file (one title per line, no comments/blanks)
_export_titles_xml() {
    local stem="$1"
    local titles_file="$2"

    local title_count
    title_count=$(wc -l < "$titles_file")
    if [ "$title_count" -eq 0 ]; then
        echo "ERROR: no page titles to export" >&2
        exit 1
    fi

    local base_url="${MACCABIPEDIA_WEB_URL:-https://maccabipedia.co.il}"
    local export_url="${base_url%/}/index.php?title=Special:Export"
    local out_file="${DOWNLOAD_DIR}/${stem}.xml"

    mkdir -p "$DOWNLOAD_DIR"

    echo "==> GET ${export_url}"
    echo "    titles: ${title_count}  ->  ${out_file}"

    # GET with -G: curl appends --data* as query params. POST was silently
    # returning the HTML form on this site (prod has an edge layer that
    # rejects the POST form submission); GET with the same params works.
    curl -fsSLG \
        --data-urlencode "pages@${titles_file}" \
        --data "curonly=1" \
        --data "templates=1" \
        --data "action=submit" \
        -o "$out_file" \
        "$export_url"

    # Quick sanity check: Special:Export returns MediaWiki XML on success; if
    # the server returned an HTML error page, the root element won't match.
    # Anchor the match to a <mediawiki followed by space/newline/> so we don't
    # accept an HTML page that happens to mention "mediawiki" in its body.
    if ! head -c 512 "$out_file" | grep -Eq '<mediawiki[[:space:]]'; then
        echo "ERROR: response is not a MediaWiki XML dump — check ${out_file}" >&2
        exit 1
    fi

    local size
    size=$(wc -c < "$out_file")
    echo "    OK — ${size} bytes"
    log_event "export" "${export_url}" "${out_file}"
}

op_pages() {
    local manifest="${1-}"
    if [ -z "$manifest" ]; then
        echo "ERROR: 'pages' op requires a manifest file path" >&2
        echo "       example: $0 pages scripts/content-manifests/starter.manifest" >&2
        exit 1
    fi
    if [ ! -f "$manifest" ]; then
        echo "ERROR: manifest not found: $manifest" >&2
        exit 1
    fi

    local stem
    stem="$(basename "$manifest")"
    stem="${stem%.*}"   # strip any extension (.txt, .manifest, …)

    # Strip comments / blanks from the manifest before sending. Special:Export
    # treats each non-empty line as a page title. Use a script-level temp var
    # so the EXIT trap can reference it without tripping `set -u`.
    cleaned="$(mktemp)"
    trap 'rm -f "${cleaned:-}"' EXIT
    grep -vE '^\s*(#|$)' "$manifest" > "$cleaned"

    _export_titles_xml "$stem" "$cleaned"
}

op_site_scripts() {
    # MediaWiki:Common.css backs the site.styles ResourceLoader bundle (used
    # site-wide for layout + skin tweaks). MediaWiki:Common.js carries
    # CanvasJS chart hooks, jump-to-id scrolling, and the fanzine email form.
    # Kept out of starter.manifest because they're site-wide assets, not
    # sample content.
    cleaned="$(mktemp)"
    trap 'rm -f "${cleaned:-}"' EXIT
    printf '%s\n' \
        "MediaWiki:Common.css" \
        "MediaWiki:Common.js" \
        > "$cleaned"

    _export_titles_xml "site-scripts" "$cleaned"
}

if [ $# -lt 1 ]; then
    usage
    exit 1
fi

op="$1"
shift

case "$op" in
    bootstrap)
        op_site_scripts
        op_pages "${SCRIPT_DIR}/content-manifests/starter.manifest"
        ;;
    site-scripts)  op_site_scripts ;;
    pages)         op_pages "$@" ;;
    -h|--help|help)
        usage
        exit 0
        ;;
    *)
        echo "ERROR: unknown op '$op'" >&2
        echo >&2
        usage >&2
        exit 1
        ;;
esac

echo "done."
