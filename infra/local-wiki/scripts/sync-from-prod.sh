#!/usr/bin/env bash
#
# Pull selected files/directories from the production MaccabiPedia FTP server
# into the (gitignored) infra/local-wiki/synced/ directory.
#
# Security model:
#   - Only the named operations below are supported — no arbitrary paths.
#   - Download-only. lftp mirror is invoked without -R; no `put`/`rm`/reverse
#     sync is available through this script. A scoped read-only FTP account
#     is recommended but not enforced here.
#   - Credentials come from env vars; never hardcoded, never logged.
#   - Every invocation appends a timestamped line to SYNC_LOG.
#
# Required for FTP-based ops (maccabipedia-skin-assets, extensions,
# logo-assets, localsettings, versions):
#   MACCABIPEDIA_FTP_HOST        — FTP hostname (e.g. ftp.maccabipedia.co.il)
#   MACCABIPEDIA_FTP_USER        — FTP username
#   MACCABIPEDIA_FTP_PASS        — FTP password
#   MACCABIPEDIA_FTP_REMOTE_ROOT — absolute path of the MediaWiki webroot on
#                                  the FTP server (e.g. /public_html)
#
# Required for HTTP-based ops (pages):
#   MACCABIPEDIA_WEB_URL         — public site base URL
#                                  (default: https://maccabipedia.co.il)
#
# Optional:
#   MACCABIPEDIA_FTP_REQUIRE_TLS=1   — fail unless the control channel is TLS
#   MACCABIPEDIA_FTP_TLS_VERIFY=1    — require a system-trusted FTP TLS cert
#
# Usage:
#   ./sync-from-prod.sh <op> [args...]
#
# Allowed <op> values:
#   bootstrap                — run every FTP+HTTP pull needed for first-time
#                              local dev setup: maccabipedia-skin-assets +
#                              extensions + favicon + site-scripts + pages
#                              (using scripts/content-manifests/starter.manifest).
#                              Doesn't touch docker — run `docker compose up
#                              -d` and `./scripts/seed-content.sh` afterwards.
#   maccabipedia-skin-assets — mirror <root>/skins/Metrolook/assets/
#                              → synced/skins/Metrolook/assets/
#                              (binary banners only, shared by both skins;
#                              the skin sources themselves — the default
#                              Maccabipedia skin at <repo-root>/skins/Maccabipedia/
#                              and the legacy Metrolook fallback at
#                              <repo-root>/skins/Metrolook/ — are NOT pulled
#                              by this script).
#   extensions               — mirror <root>/extensions/ → synced/extensions/
#   favicon                  — fetch  <root>/favicon.ico → synced/favicon.ico
#   localsettings            — fetch  <root>/LocalSettings.php
#                              → synced/LocalSettings.prod-snapshot.php
#                              (diagnostic only — not needed for boot)
#   logo-assets              — mirror <root>/resources/assets/
#                              → synced/resources/assets/
#                              (diagnostic only — not mounted by the dev stack)
#   versions                 — list remote directory names under the webroot
#                              for audit (no downloads; prints listing only)
#   site-scripts             — pull MediaWiki:Common.css + MediaWiki:Common.js
#                              via Special:Export. Common.css backs the
#                              site.styles ResourceLoader bundle; Common.js
#                              carries CanvasJS chart hooks, jump-to-id
#                              scrolling, and the fanzine email form. Output:
#                              synced/pages/site-scripts.xml.
#   pages <manifest>         — pull page wikitext via Special:Export (HTTP)
#                              for every title in <manifest> (one title per
#                              line; blanks and lines starting with '#'
#                              ignored). Templates referenced by the pages
#                              are included automatically. Output:
#                              synced/pages/<manifest-stem>.xml (MW XML dump)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_WIKI_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SYNCED_DIR="${LOCAL_WIKI_DIR}/synced"

REPO_ROOT="$(cd "${LOCAL_WIKI_DIR}/../.." && pwd)"
SYNC_LOG="${REPO_ROOT}/.claude/tmp/ftp-sync.log"

# Auto-load local .env if present. It's gitignored; intended for FTP creds.
# Only MACCABIPEDIA_FTP_* vars are honored downstream, other vars in the file
# will be set but not used by this script.
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

require_env() {
    local missing=()
    for var in "$@"; do
        if [ -z "${!var-}" ]; then
            missing+=("$var")
        fi
    done
    if [ ${#missing[@]} -gt 0 ]; then
        echo "ERROR: missing required env var(s): ${missing[*]}" >&2
        exit 1
    fi
}

log_event() {
    mkdir -p "$(dirname "$SYNC_LOG")"
    printf '%s  %s  remote=%s  local=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        "$1" "$2" "${3:-}" \
        >> "$SYNC_LOG"
}

run_lftp() {
    local script="$1"
    # Shared hosts often present self-signed / untrusted TLS certs. Default is
    # TLS encryption *without* strict cert verification — encrypts password on
    # the wire, accepts untrusted cert. Set MACCABIPEDIA_FTP_TLS_VERIFY=1 to
    # require a system-trusted cert. Set MACCABIPEDIA_FTP_REQUIRE_TLS=1 to
    # refuse the connection entirely if the server does not offer TLS.
    local tls_line="set ftp:ssl-allow yes; set ftp:ssl-force no; set ssl:verify-certificate no;"
    if [ "${MACCABIPEDIA_FTP_REQUIRE_TLS:-0}" = "1" ]; then
        tls_line="set ftp:ssl-allow yes; set ftp:ssl-force yes; set ssl:verify-certificate no;"
    fi
    if [ "${MACCABIPEDIA_FTP_TLS_VERIFY:-0}" = "1" ]; then
        tls_line="${tls_line//verify-certificate no/verify-certificate yes}"
    else
        echo "WARN: FTP cert verification is OFF — TLS encrypts the password but" >&2
        echo "      cannot detect an active MITM. Set MACCABIPEDIA_FTP_TLS_VERIFY=1" >&2
        echo "      in infra/local-wiki/.env once your host's FTP cert is trusted." >&2
    fi
    # cmd:fail-exit makes lftp exit non-zero on any command failure inside
    # the -e script (auth fail, mirror error, missing remote path, etc.);
    # without it, a partial or failed transfer silently exits 0.
    lftp -u "${MACCABIPEDIA_FTP_USER},${MACCABIPEDIA_FTP_PASS}" \
         "${MACCABIPEDIA_FTP_HOST}" \
         -e "set cmd:fail-exit yes; ${tls_line} set net:max-retries 3; set net:timeout 20; ${script}; bye"
}

op_mirror_dir() {
    require_env MACCABIPEDIA_FTP_HOST MACCABIPEDIA_FTP_USER MACCABIPEDIA_FTP_PASS MACCABIPEDIA_FTP_REMOTE_ROOT
    local remote_sub="$1"
    local local_sub="$2"
    local remote="${MACCABIPEDIA_FTP_REMOTE_ROOT%/}/${remote_sub}"
    local local_dir="${SYNCED_DIR}/${local_sub}"

    mkdir -p "$local_dir"
    echo "==> lftp mirror  ${remote}  ->  ${local_dir}"
    # Drop --only-missing: we want upstream file updates picked up on re-sync.
    # lftp still compares size/mtime and skips unchanged files, so a re-sync
    # after no prod changes is fast without leaving stale content behind.
    run_lftp "mirror --verbose --parallel=4 '${remote}' '${local_dir}'"
    log_event "mirror" "${remote}" "${local_dir}"
}

op_localsettings() {
    require_env MACCABIPEDIA_FTP_HOST MACCABIPEDIA_FTP_USER MACCABIPEDIA_FTP_PASS MACCABIPEDIA_FTP_REMOTE_ROOT
    local remote="${MACCABIPEDIA_FTP_REMOTE_ROOT%/}/LocalSettings.php"
    local local_file="${SYNCED_DIR}/LocalSettings.prod-snapshot.php"

    mkdir -p "${SYNCED_DIR}"
    echo "==> lftp get  ${remote}  ->  ${local_file}"
    run_lftp "get '${remote}' -o '${local_file}'"
    log_event "get" "${remote}" "${local_file}"
    echo "   snapshot saved. Scrub secrets before committing anything derived from it."
}

op_favicon() {
    require_env MACCABIPEDIA_FTP_HOST MACCABIPEDIA_FTP_USER MACCABIPEDIA_FTP_PASS MACCABIPEDIA_FTP_REMOTE_ROOT
    local remote="${MACCABIPEDIA_FTP_REMOTE_ROOT%/}/favicon.ico"
    local local_file="${SYNCED_DIR}/favicon.ico"

    mkdir -p "${SYNCED_DIR}"
    echo "==> lftp get  ${remote}  ->  ${local_file}"
    run_lftp "get '${remote}' -o '${local_file}'"
    log_event "get" "${remote}" "${local_file}"
}

op_versions() {
    require_env MACCABIPEDIA_FTP_HOST MACCABIPEDIA_FTP_USER MACCABIPEDIA_FTP_PASS MACCABIPEDIA_FTP_REMOTE_ROOT
    local remote="${MACCABIPEDIA_FTP_REMOTE_ROOT%/}"
    echo "==> lftp cls -l  ${remote}"
    run_lftp "cls -l '${remote}'"
    log_event "list" "${remote}" ""
}

# Args: $1 = output stem (synced/pages/<stem>.xml)
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
    local out_dir="${SYNCED_DIR}/pages"
    local out_file="${out_dir}/${stem}.xml"

    mkdir -p "$out_dir"

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
        op_mirror_dir "skins/Metrolook/assets" "skins/Metrolook/assets"
        op_mirror_dir "extensions"             "extensions"
        op_favicon
        op_site_scripts
        op_pages "${SCRIPT_DIR}/content-manifests/starter.manifest"
        ;;
    maccabipedia-skin-assets)
        op_mirror_dir "skins/Metrolook/assets" "skins/Metrolook/assets" ;;
    extensions)    op_mirror_dir "extensions"        "extensions" ;;
    favicon)       op_favicon ;;
    logo-assets)   op_mirror_dir "resources/assets"  "resources/assets" ;;
    localsettings) op_localsettings ;;
    versions)      op_versions ;;
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
