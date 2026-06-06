#!/usr/bin/env bash
#
# check-prod-skin-version.sh — compare the live prod Maccabipedia skin version
# against the repo's skins/Maccabipedia/skin.json before a deploy.
#
# On Special:Version the skin is listed under its DISPLAY name "Maccabipedia"
# (from namemsg/skinname-maccabipedia), not the manifest name "MaccabipediaSkin".
#
# Policy: gate when readable, warn when blocked.
#   - prod readable and repo version NOT strictly newer  -> exit 1 (gate: stop)
#   - prod readable and repo strictly newer              -> exit 0 (proceed)
#   - prod unreadable (edge block / unparseable)         -> exit 0 (warn only)
#
# Usage: bash check-prod-skin-version.sh
#   No UA needed: curl's default UA satisfies MediaWiki's UA policy, and prod's
#   edge block (when it triggers) is IP-based, not UA-based.
set -euo pipefail

SKIN_JSON="skins/Maccabipedia/skin.json"
URL="https://www.maccabipedia.co.il/index.php/Special:Version"

repo_version="$(jq -r '.version' "$SKIN_JSON")"

html="$(curl -sS "$URL" 2>/dev/null || true)"
if [ -z "$html" ]; then
    echo "WARN: could not read $URL (empty response — prod edge likely blocking automation)."
    echo "      Verify the live skin version in a browser. Repo version: $repo_version. Proceeding."
    exit 0
fi

# Grab the first version-looking token in the rows around the skin's display name.
prod_version="$(printf '%s' "$html" | grep -iA3 '>Maccabipedia<' | grep -oiE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
if [ -z "$prod_version" ]; then
    echo "WARN: reached Special:Version but could not parse the Maccabipedia skin version."
    echo "      Verify it in a browser. Repo version: $repo_version. Proceeding."
    exit 0
fi

if [ "$prod_version" = "$repo_version" ]; then
    echo "GATE: prod already shows $prod_version == repo $repo_version — nothing to deploy, or you forgot to bump skin.json." >&2
    exit 1
fi

newest="$(printf '%s\n%s\n' "$repo_version" "$prod_version" | sort -V | tail -1)"
if [ "$newest" = "$prod_version" ]; then
    echo "GATE: prod $prod_version is NEWER than repo $repo_version — your branch is behind. Stop." >&2
    exit 1
fi

echo "OK: repo $repo_version > prod $prod_version — proceeding."
