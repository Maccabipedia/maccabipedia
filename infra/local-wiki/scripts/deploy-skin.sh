#!/usr/bin/env bash
#
# deploy-skin.sh — assemble a ready-to-upload skin snapshot from the repo.
#
# Fully local: each skin vendors its own assets (skins/<Name>/assets/), so
# there is NO prod pull. The upload itself is MANUAL (FileZilla) — this script
# stops at a snapshot under ~/maccabipedia_skins/<ts>/ and prints the upload
# steps (those come from prepare-skin-for-upload.sh, which it calls).
#
# Usage:
#   bash deploy-skin.sh                       # default skin (maccabipedia)
#   bash deploy-skin.sh --skin=maccabipedia
#
# Optional args pass through to prepare-skin-for-upload.sh (skin selection,
# snapshot base path — see its header).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Fully local — the skin vendors its own assets, so there is no prod pull.
echo "==> assembling upload snapshot (local; assets vendored in repo)"
bash "${SCRIPT_DIR}/prepare-skin-for-upload.sh" "$@"
