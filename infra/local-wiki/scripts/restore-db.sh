#!/usr/bin/env bash
#
# Restore the committed database snapshot into a running local wiki.
#
#   bash infra/local-wiki/scripts/restore-db.sh
#
# This REPLACES the local wiki's database with the fixture. It is what CI runs
# after booting the stack, and what a developer runs to get back to the known
# dataset the football query harnesses assert against.
#
# The stack installs an empty wiki on first boot; this drops that database and
# loads the snapshot over it, so the page text, the Cargo tables and the Cargo
# metadata (cargo_tables, cargo_pages) all arrive together and consistent.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_WIKI_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${LOCAL_WIKI_DIR}/docker-compose.yml"
FIXTURE="${LOCAL_WIKI_DIR}/fixtures/wiki-snapshot.sql.gz"

if [[ ! -f "$FIXTURE" ]]; then
    echo "no snapshot at ${FIXTURE} - create one with snapshot-db.sh" >&2
    exit 1
fi

echo "restoring ${FIXTURE} ($(du -h "$FIXTURE" | cut -f1))..."
gunzip -c "$FIXTURE" | docker compose -f "$COMPOSE_FILE" exec -T mariadb \
    mysql -umw -pdevpass --default-character-set=binary maccabipedia

# MediaWiki caches parser output and messages in the database and in APCu. The
# restored rows are someone else's cache entries, so they are dropped rather
# than served: a stale parser cache would hand the harness the OLD rendering of
# a template and the comparison would pass while the modules were wrong.
docker compose -f "$COMPOSE_FILE" exec -T mariadb \
    mysql -umw -pdevpass maccabipedia \
    -e 'TRUNCATE TABLE MPMW_objectcache; TRUNCATE TABLE MPMW_parsercache;' \
    2>/dev/null || true
docker compose -f "$COMPOSE_FILE" restart mediawiki >/dev/null

# The snapshot can carry pages signed with PRODUCTION's SecureHTML secret, and
# a strip whose hash does not validate renders "שגיאה:גיבוב (hash) לא חוקי"
# instead of tabs. Locally that turned every tab comparison into a comparison
# of two identical error messages - reported HOLLOW, proving nothing - and it
# would do the same in CI.
echo "re-signing <shtml> blocks with the local secret..."
docker cp "${LOCAL_WIKI_DIR}/scripts/resignSecureHtml.php" \
    "$(docker compose -f "$COMPOSE_FILE" ps -q mediawiki)":/var/www/html/maintenance/resignSecureHtml.php
docker compose -f "$COMPOSE_FILE" exec -T mediawiki \
    php maintenance/resignSecureHtml.php 2>/dev/null | tail -1

echo "waiting for the wiki to answer..."
for _ in $(seq 1 60); do
    if curl -fsS -o /dev/null http://localhost:8080/api.php 2>/dev/null; then
        echo "restored"
        exit 0
    fi
    sleep 2
done

echo "the wiki did not come back after the restore" >&2
exit 1
