#!/usr/bin/env bash
#
# Snapshot the running local wiki's database into the committed fixture.
#
#   bash infra/local-wiki/scripts/snapshot-db.sh
#
# The fixture is how CI gets a wiki with real data in it: restore-db.sh loads
# it into a freshly booted stack, and the football query harnesses then run
# against real Cargo and real Scribunto instead of a stub.
#
# Why a whole-database dump rather than an XML page dump plus a Cargo rebuild:
# the rebuild path (importDump -> createLocalCargoTables -> populateLocalCargoData)
# takes minutes and does not reproduce rows that were loaded directly, and the
# <shtml> tab strips in the page text are HMAC-signed - a restore keeps them
# verifiable because the dev secret is committed in
# config/LocalSettings.env.local.php, where a re-import would need re-signing.
#
# Regenerate it when the local wiki's content changes in a way the harnesses
# depend on (a new season seeded, a new edge case). It is ~3.6MB gzipped, so
# do not regenerate it casually - every version stays in git history.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_WIKI_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${LOCAL_WIKI_DIR}/docker-compose.yml"
FIXTURE="${LOCAL_WIKI_DIR}/fixtures/wiki-snapshot.sql.gz"

mkdir -p "$(dirname "$FIXTURE")"

if ! docker compose -f "$COMPOSE_FILE" ps --status running --services \
        | grep -q '^mariadb$'; then
    echo "the local wiki is not running: docker compose -f ${COMPOSE_FILE} up -d" >&2
    exit 1
fi

echo "dumping maccabipedia from the running stack..."
docker compose -f "$COMPOSE_FILE" exec -T mariadb \
    mysqldump -umw -pdevpass --single-transaction --routines \
    --default-character-set=binary maccabipedia \
    2>/dev/null | gzip -9 > "${FIXTURE}.tmp"

# A truncated dump restores without error and leaves tables silently missing
# rows, so the fixture is only replaced once it is known to be complete.
if ! gzip -t "${FIXTURE}.tmp"; then
    rm -f "${FIXTURE}.tmp"
    echo "the dump is not a valid gzip stream - fixture left unchanged" >&2
    exit 1
fi
if ! gunzip -c "${FIXTURE}.tmp" | tail -5 | grep -q 'Dump completed'; then
    rm -f "${FIXTURE}.tmp"
    echo "the dump has no completion marker - fixture left unchanged" >&2
    exit 1
fi

mv "${FIXTURE}.tmp" "$FIXTURE"
echo "wrote $(du -h "$FIXTURE" | cut -f1)  ${FIXTURE}"
