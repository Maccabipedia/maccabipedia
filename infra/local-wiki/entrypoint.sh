#!/bin/bash
set -euo pipefail

GENERATED_DIR=/generated
INSTALLED_MARKER="${GENERATED_DIR}/.installed"
ACTIVE_LS=/var/www/html/LocalSettings.php
CONFIG_DIR=/mw-config
STUB="${CONFIG_DIR}/LocalSettings.stub.php"

mkdir -p "$GENERATED_DIR"

if [ ! -f "$STUB" ]; then
    echo "[entrypoint] ERROR: $STUB not bind-mounted — check docker-compose.yml" >&2
    exit 1
fi

# First-boot install — writes the MediaWiki schema into the DB. The generated
# LocalSettings.php from install.php goes to /tmp and is discarded; our
# split-config stub is copied into place below. A marker file in the
# persistent /generated volume tracks install state across container
# restarts, so we don't re-run install.php every boot.
if [ ! -f "$INSTALLED_MARKER" ]; then
    echo "[entrypoint] First boot — running MediaWiki install.php"

    php maintenance/install.php \
        --dbtype=mysql \
        --dbserver="${MW_DB_HOST}" \
        --dbname="${MW_DB_NAME}" \
        --dbuser="${MW_DB_USER}" \
        --dbpass="${MW_DB_PASSWORD}" \
        --dbprefix="${MW_DB_PREFIX:-}" \
        --installdbuser="${MW_DB_USER}" \
        --installdbpass="${MW_DB_PASSWORD}" \
        --server="${MW_SITE_SERVER}" \
        --scriptpath="" \
        --lang="${MW_SITE_LANG}" \
        --pass="${MW_ADMIN_PASSWORD}" \
        --confpath=/tmp \
        "${MW_SITE_NAME}" \
        "${MW_ADMIN_USER}"

    touch "$INSTALLED_MARKER"
    echo "[entrypoint] Install complete."
fi

# The stub must be a real file at /var/www/html/LocalSettings.php so PHP's
# __DIR__ resolves to /var/www/html/ — where the env and shared files are
# symlinked as siblings below. /var/www/html/ is image filesystem and resets
# on container recreation, so this must run each time.
cp "$STUB" "$ACTIVE_LS"

# Symlink the env + shared files (mounted as a group under /mw-config/)
# into /var/www/html/ so the stub's __DIR__-relative require_once finds
# them as siblings of LocalSettings.php. Symlinks (not cp) preserve
# live edits from the host.
ln -sf "${CONFIG_DIR}/LocalSettings.env.local.php" /var/www/html/LocalSettings.env.local.php
ln -sf "${CONFIG_DIR}/LocalSettings.shared.php"    /var/www/html/LocalSettings.shared.php

# Safety net: if someone edits the stub and breaks PHP syntax, catch it at
# boot rather than at page load time.
if ! php -l "$ACTIVE_LS" >/dev/null; then
    echo "[entrypoint] ERROR: $ACTIVE_LS failed php -l syntax check" >&2
    exit 1
fi

echo "[entrypoint] Running maintenance/update.php --quick"
php maintenance/update.php --quick

# Dev/test fixture: a non-admin account so the test suite (and manual testing)
# can exercise the regular-user view. --force is idempotent: creates it, or just
# resets the password if it already exists in the persisted DB.
echo "[entrypoint] Ensuring regular test user exists"
php maintenance/createAndPromote.php "${MW_REGULAR_USER:-regular}" "${MW_REGULAR_PASSWORD:-regularpass}" --force

exec "$@"
