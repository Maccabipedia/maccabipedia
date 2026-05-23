#!/usr/bin/env bash
#
# deploy-skin.sh — one-command prep for a skin deploy: pull prod's banner
# assets (read-only), then assemble the ready-to-upload snapshot.
#
# The upload itself is MANUAL (FileZilla) — this script stops at a snapshot
# under ~/maccabipedia_skins/<ts>/ and prints the upload steps (those come
# from prepare-skin-for-upload.sh, which it calls).
#
# Usage:
#   bash deploy-skin.sh                       # both skins, default output base
#   bash deploy-skin.sh --skin=maccabipedia
#
# Optional args pass through to prepare-skin-for-upload.sh (skin selection,
# snapshot base path — see its header). FTP creds are read from
# infra/local-wiki/.env by sync-from-prod.sh, not the shell environment.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> [1/2] pulling prod banner assets (read-only)"
bash "${SCRIPT_DIR}/sync-from-prod.sh" maccabipedia-skin-assets

echo
echo "==> [2/2] assembling upload snapshot"
bash "${SCRIPT_DIR}/prepare-skin-for-upload.sh" "$@"
