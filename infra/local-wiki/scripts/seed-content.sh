#!/usr/bin/env bash
#
# Import a previously-pulled XML dump into the running local wiki.
#
# Expects:
#   - The stack is up: `docker compose -f <dir>/docker-compose.yml ps`
#   - An XML dump exists at downloaded-pages/<stem>.xml — download one with
#     `uv run python scripts/download_pages_from_prod.py pages <manifest>`.
#
# Usage:
#   bash seed-content.sh               # imports every XML in downloaded-pages/
#   bash seed-content.sh <stem>        # imports only downloaded-pages/<stem>.xml
#
# After import, rebuilds the link tables (parallel refreshLinks workers),
# search index and recent changes, then flushes the job queue. Cargo rows are
# NOT produced by import — run recreate-cargo-tables.sh afterwards.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_WIKI_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PAGES_DIR="${LOCAL_WIKI_DIR}/downloaded-pages"
COMPOSE_FILE="${LOCAL_WIKI_DIR}/docker-compose.yml"
SERVICE="mediawiki"

# Pick up docker-cli privileges. Prefer the unprivileged path; fall back to
# sudo only if the daemon socket isn't reachable for the invoking user.
if docker info >/dev/null 2>&1; then
    DOCKER="docker"
elif sudo -n docker info >/dev/null 2>&1; then
    DOCKER="sudo docker"
else
    echo "ERROR: cannot reach the docker daemon. Either add your user to the" >&2
    echo "       docker group (see scripts/setup-host.sh) or configure" >&2
    echo "       passwordless sudo for docker." >&2
    exit 1
fi

compose_exec() {
    $DOCKER compose -f "$COMPOSE_FILE" exec "$@"
}

if ! compose_exec -T "$SERVICE" true >/dev/null 2>&1; then
    echo "ERROR: the '$SERVICE' container is not running." >&2
    echo "       Start it with:" >&2
    echo "         $DOCKER compose -f $COMPOSE_FILE up -d" >&2
    exit 1
fi

if [ ! -d "$PAGES_DIR" ]; then
    echo "ERROR: no downloaded pages dir at $PAGES_DIR" >&2
    echo "       Download some pages first:" >&2
    echo "         uv run python scripts/download_pages_from_prod.py pages <manifest>" >&2
    exit 1
fi

declare -a xml_files=()
if [ $# -eq 0 ]; then
    while IFS= read -r -d '' xml; do
        xml_files+=("$xml")
    done < <(find "$PAGES_DIR" -maxdepth 1 -type f -name '*.xml' -print0)
else
    stem="$1"
    candidate="${PAGES_DIR}/${stem}.xml"
    if [ ! -f "$candidate" ]; then
        echo "ERROR: no XML dump at $candidate" >&2
        exit 1
    fi
    xml_files+=("$candidate")
fi

if [ ${#xml_files[@]} -eq 0 ]; then
    echo "ERROR: no XML files to import in $PAGES_DIR" >&2
    exit 1
fi

for xml in "${xml_files[@]}"; do
    echo "[$(date +%H:%M:%S)] ==> importDump.php  <  ${xml}"
    # Drop --quiet so per-page import errors are visible rather than hidden
    # behind a uniformly-successful exit code.
    compose_exec -T "$SERVICE" \
        php maintenance/importDump.php --no-updates \
        < "$xml"
done

# Imported <shtml> blocks are HMAC-signed with PROD's SecureHTML secret and
# would all render "invalid hash" locally — re-sign them with the dev key.
echo "[$(date +%H:%M:%S)] ==> resignSecureHtml.php (re-sign shtml with the local key)"
$DOCKER compose -f "$COMPOSE_FILE" cp \
    "${SCRIPT_DIR}/resignSecureHtml.php" "$SERVICE":/var/www/html/maintenance/resignSecureHtml.php
compose_exec -T "$SERVICE" php maintenance/resignSecureHtml.php

# Link rebuild re-parses every page, so two speedups apply:
#  - MW_DISABLE_FOREIGN_IMAGES: image lookups are HTTP round-trips to prod
#    and ~90% of parse wall time; link tables don't need them (file
#    references are recorded either way).
#  - refreshLinks.php is single-threaded — run one worker per page-id range
#    instead of rebuildall.php's serial pass. The refresh phase is per-page
#    so ranges can't conflict; each worker does additionally repeat the
#    delete-links-from-nonexistent sweep over the whole table, which is
#    redundant but idempotent. rebuildall's other two stages (text index,
#    recent changes) run after, they're cheap.
# DB name/credentials are evaluated INSIDE the mariadb container (they're
# container env from docker-compose.yml, not host env); only the MediaWiki
# table prefix has to be restated here.
REBUILD_WORKERS="${SEED_REBUILD_WORKERS:-8}"
max_page_id=$(compose_exec -T mariadb sh -c \
    'exec mysql -N -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COALESCE(MAX(page_id), 0) FROM '"${MW_DB_PREFIX:-MPMW_}"'page"' \
    | tr -d '[:space:]')
echo "[$(date +%H:%M:%S)] ==> refreshLinks.php (${REBUILD_WORKERS} workers over page ids 1..${max_page_id})"
range_size=$(( (max_page_id + REBUILD_WORKERS - 1) / REBUILD_WORKERS ))
declare -a rebuild_pids=()
for (( worker=0; worker<REBUILD_WORKERS; worker++ )); do
    range_start=$(( worker * range_size + 1 ))
    range_end=$(( (worker + 1) * range_size ))
    compose_exec -T -e MW_DISABLE_FOREIGN_IMAGES=1 "$SERVICE" \
        php maintenance/refreshLinks.php "$range_start" --e "$range_end" &
    rebuild_pids+=($!)
done
rebuild_status=0
for pid in "${rebuild_pids[@]}"; do
    wait "$pid" || rebuild_status=1
done
if [ "$rebuild_status" -ne 0 ]; then
    echo "ERROR: a refreshLinks worker failed — check the output above." >&2
    exit 1
fi

echo "[$(date +%H:%M:%S)] ==> rebuildtextindex.php (search index)"
compose_exec -T "$SERVICE" php maintenance/rebuildtextindex.php

echo "[$(date +%H:%M:%S)] ==> rebuildrecentchanges.php"
compose_exec -T "$SERVICE" php maintenance/rebuildrecentchanges.php

echo "[$(date +%H:%M:%S)] ==> runJobs.php (flush deferred work)"
compose_exec -T -e MW_DISABLE_FOREIGN_IMAGES=1 "$SERVICE" php maintenance/runJobs.php --maxjobs 2000

# The parser cache lives in the DB objectcache (CACHE_NONE only disables the
# main cache), so pages rendered before this seed would keep showing imported
# pages as redlinks until touched. Drop it.
echo "[$(date +%H:%M:%S)] ==> purgeParserCache.php (drop stale pre-seed renders)"
compose_exec -T "$SERVICE" php maintenance/purgeParserCache.php --age 0

echo "done — imported ${#xml_files[@]} dump file(s). Reload http://localhost:8080 to see the content."
