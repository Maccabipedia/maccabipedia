#!/usr/bin/env bash
#
# (Re)create + populate the local Cargo tables from the imported pages.
# Why Cargo's own tooling can't do this here: see the header of
# populateLocalCargoData.php. Prerequisite — the declaration templates
# (listed at runtime from prod, so new tables are picked up automatically):
#
#   uv run python scripts/download_pages_from_prod.py cargo-declarations
#   bash scripts/seed-content.sh cargo-declarations
#   bash scripts/recreate-cargo-tables.sh
#
# Usage:
#   bash recreate-cargo-tables.sh                  # recreate + populate everything
#   bash recreate-cargo-tables.sh --populate-only  # skip (re)creating tables
#
# Populate runs CARGO_POPULATE_WORKERS parallel workers (default 8). The run
# is idempotent — if a worker fails, fix the cause and re-run --populate-only.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_WIKI_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${LOCAL_WIKI_DIR}/docker-compose.yml"

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

if ! compose_exec -T mediawiki true >/dev/null 2>&1; then
    echo "ERROR: the 'mediawiki' container is not running." >&2
    echo "       Start it with:" >&2
    echo "         $DOCKER compose -f $COMPOSE_FILE up -d" >&2
    exit 1
fi

POPULATE_ONLY=0
if [ "${1:-}" = "--populate-only" ]; then
    POPULATE_ONLY=1
    shift
fi

if [ "$POPULATE_ONLY" -eq 0 ]; then
    echo "==> recreating Cargo tables (single batched process)"
    $DOCKER compose -f "$COMPOSE_FILE" cp \
        "${SCRIPT_DIR}/createLocalCargoTables.php" mediawiki:/var/www/html/maintenance/createLocalCargoTables.php
    compose_exec -T mediawiki php maintenance/createLocalCargoTables.php
fi

# Populate by replaying the page-save store for every store-capable page —
# see the header of populateLocalCargoData.php for why Cargo's own recreate
# tooling can't do this here.
WORKERS="${CARGO_POPULATE_WORKERS:-8}"
echo "==> populating tables (page-save replay, ${WORKERS} parallel workers)"
$DOCKER compose -f "$COMPOSE_FILE" cp \
    "${SCRIPT_DIR}/populateLocalCargoData.php" mediawiki:/var/www/html/maintenance/populateLocalCargoData.php

# MW_DISABLE_FOREIGN_IMAGES: image lookups are HTTP round-trips to prod and
# ~90% of page-parse wall time, while #cargo_store needs none of them.
FAILED_LIST=/tmp/cargo-populate-failed.txt
compose_exec -T mediawiki rm -f "$FAILED_LIST"
declare -a worker_pids=()
for (( worker=0; worker<WORKERS; worker++ )); do
    compose_exec -T -e MW_DISABLE_FOREIGN_IMAGES=1 mediawiki \
        php maintenance/populateLocalCargoData.php --shards "$WORKERS" --shard "$worker" \
        --failed-to "$FAILED_LIST" &
    worker_pids+=($!)
done

populate_status=0
for pid in "${worker_pids[@]}"; do
    wait "$pid" || populate_status=1
done

# Second pass, foreign images ON, for what the fast pass could not store. A
# page that uses a קובץ: page existing locally (the season manifests import
# the games' media description pages) fails to store with foreign images off
# - "Call to a member function getSha1() on bool" - and stores with them on.
if [ "$populate_status" -ne 0 ]; then
    mapfile -t failed_titles < <(compose_exec -T mediawiki cat "$FAILED_LIST" 2>/dev/null)
    echo "==> re-storing ${#failed_titles[@]} page(s) with foreign images on"
    populate_status=0
    for title in "${failed_titles[@]}"; do
        compose_exec -T mediawiki php maintenance/populateLocalCargoData.php \
            --title "$title" || populate_status=1
    done
    if [ "${#failed_titles[@]}" -eq 0 ]; then
        populate_status=1  # a worker failed without listing a page: not a store failure
    fi
fi
if [ "$populate_status" -ne 0 ]; then
    echo "ERROR: a populate worker failed — see the output above. The run is" >&2
    echo "       idempotent: fix the cause (or just retry) with:" >&2
    echo "         bash scripts/recreate-cargo-tables.sh --populate-only" >&2
    exit 1
fi

echo "done — Cargo tables populated."

# Links again, now that Cargo has data. seed-content.sh refreshes links right
# after the import, when the Cargo tables are still empty, and some pages pick
# their CATEGORIES from Cargo: a press clipping's file page files itself under
# "עיתונות למשחק מה-<date>" only if it finds the game, and otherwise under
# "…עם שיוך לא תקין למשחק". The games list tests exactly those categories, so
# without this pass every press icon is missing locally (1939: 2 icons, 15 on
# production). Same parallel page-id ranges as seed-content.sh.
REBUILD_WORKERS="${SEED_REBUILD_WORKERS:-8}"
max_page_id=$(compose_exec -T mariadb sh -c \
    'exec mysql -N -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COALESCE(MAX(page_id), 0) FROM '"${MW_DB_PREFIX:-MPMW_}"'page"' \
    | tr -d '[:space:]')
echo "==> refreshLinks.php now that Cargo is populated (${REBUILD_WORKERS} workers, page ids 1..${max_page_id})"
range_size=$(( (max_page_id + REBUILD_WORKERS - 1) / REBUILD_WORKERS ))
declare -a link_pids=()
for (( worker=0; worker<REBUILD_WORKERS; worker++ )); do
    compose_exec -T -e MW_DISABLE_FOREIGN_IMAGES=1 mediawiki \
        php maintenance/refreshLinks.php $(( worker * range_size + 1 )) --e $(( (worker + 1) * range_size )) &
    link_pids+=($!)
done
links_status=0
for pid in "${link_pids[@]}"; do
    wait "$pid" || links_status=1
done
if [ "$links_status" -ne 0 ]; then
    echo "ERROR: a refreshLinks worker failed — check the output above." >&2
    exit 1
fi
compose_exec -T mediawiki php maintenance/purgeParserCache.php --age 0 >/dev/null
echo "done — links refreshed against the populated Cargo tables."
