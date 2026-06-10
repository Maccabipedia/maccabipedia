#!/usr/bin/env bash
#
# (Re)create + populate the local Cargo tables from the imported pages.
#
# Why per-table: cargoRecreateData.php with no arguments iterates the
# `cargo_tables` metadata table, which is EMPTY on a fresh local wiki (it is
# only filled when a table is first created), so the no-args run exits
# silently doing nothing. The --table path instead resolves the declaring
# template through page_props, so it works as soon as the declaration
# templates are imported:
#
#   uv run python scripts/download_pages_from_prod.py pages scripts/content-manifests/cargo-declarations.manifest
#   bash scripts/seed-content.sh cargo-declarations
#   bash scripts/recreate-cargo-tables.sh
#
# Usage:
#   bash recreate-cargo-tables.sh                  # every table declared locally
#   bash recreate-cargo-tables.sh <table>...       # only the named tables
#   bash recreate-cargo-tables.sh --populate-only  # skip (re)creating tables
#   bash recreate-cargo-tables.sh --create-only    # skip the populate pass
#
# Populate runs CARGO_POPULATE_WORKERS parallel workers (default 8).

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
CREATE_ONLY=0
if [ "${1:-}" = "--populate-only" ]; then
    POPULATE_ONLY=1
    shift
elif [ "${1:-}" = "--create-only" ]; then
    CREATE_ONLY=1
    shift
fi

declare -a tables=()
if [ $# -gt 0 ]; then
    tables=("$@")
else
    # Every Cargo table declared by an imported template.
    while IFS= read -r table; do
        [ -n "$table" ] && tables+=("$table")
    done < <(compose_exec -T mariadb mysql -N -u root -p"${MYSQL_ROOT_PASSWORD:-devroot}" \
        "${MW_DB_NAME:-maccabipedia}" \
        -e "SELECT DISTINCT pp_value FROM ${MW_DB_PREFIX:-MPMW_}page_props WHERE pp_propname='CargoTableName' ORDER BY pp_value")
fi

if [ ${#tables[@]} -eq 0 ]; then
    echo "ERROR: no Cargo tables declared locally. Import the declaration" >&2
    echo "       templates first:" >&2
    echo "         uv run python scripts/download_pages_from_prod.py pages scripts/content-manifests/cargo-declarations.manifest" >&2
    echo "         bash scripts/seed-content.sh cargo-declarations" >&2
    exit 1
fi

if [ "$POPULATE_ONLY" -eq 0 ]; then
    echo "==> recreating ${#tables[@]} Cargo table(s)"
    for table in "${tables[@]}"; do
        echo "    - ${table}"
        # --quiet also skips the interactive 5s "hit Ctrl-C" grace sleep.
        compose_exec -T mediawiki \
            php extensions/Cargo/maintenance/cargoRecreateData.php --table "$table" --quiet
    done
fi

if [ "$CREATE_ONLY" -eq 1 ]; then
    echo "done — ${#tables[@]} Cargo table(s) created (populate skipped)."
    exit 0
fi

# cargoRecreateData.php only re-parses pages that transclude the declaring /
# attached templates — on MaccabiPedia most #cargo_store calls live in plain
# content templates, so the tables come out of the loop above EMPTY. Replay
# the page-save store for every page to actually fill them (see the header of
# populateLocalCargoData.php).
WORKERS="${CARGO_POPULATE_WORKERS:-8}"
echo "==> populating tables (page-save replay, ${WORKERS} parallel workers)"
$DOCKER compose -f "$COMPOSE_FILE" cp \
    "${SCRIPT_DIR}/populateLocalCargoData.php" mediawiki:/var/www/html/maintenance/populateLocalCargoData.php

# MW_DISABLE_FOREIGN_IMAGES: image lookups are HTTP round-trips to prod and
# ~90% of page-parse wall time, while #cargo_store needs none of them.
WORKER_LOG_DIR="$(mktemp -d /tmp/cargo-populate.XXXXXX)"
declare -a worker_pids=()
for (( worker=0; worker<WORKERS; worker++ )); do
    compose_exec -T -e MW_DISABLE_FOREIGN_IMAGES=1 mediawiki \
        php maintenance/populateLocalCargoData.php --shards "$WORKERS" --shard "$worker" \
        2>&1 | tee "${WORKER_LOG_DIR}/w${worker}.log" &
    worker_pids+=($!)
done

populate_status=0
for pid in "${worker_pids[@]}"; do
    wait "$pid" || populate_status=1
done

if [ "$populate_status" -ne 0 ]; then
    # A page can exhaust its retries when two workers race on the same
    # table's unlocked MAX(_ID)+1 allocation. Nothing else writes now, so a
    # serial second pass converges deterministically.
    mapfile -t failed_titles < <(
        sed -nE 's/.*\] (.*) — ERROR after [0-9]+ attempts.*/\1/p' "${WORKER_LOG_DIR}"/w*.log | sort -u
    )
    if [ ${#failed_titles[@]} -eq 0 ]; then
        echo "ERROR: a populate worker failed but no failed pages were parsed from its log — check ${WORKER_LOG_DIR}." >&2
        exit 1
    fi
    echo "==> re-storing ${#failed_titles[@]} race-failed page(s) serially"
    for title in "${failed_titles[@]}"; do
        compose_exec -T -e MW_DISABLE_FOREIGN_IMAGES=1 mediawiki \
            php maintenance/populateLocalCargoData.php --title "$title"
    done
fi
rm -rf "$WORKER_LOG_DIR"

echo "done — Cargo tables populated."
