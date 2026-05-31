#!/usr/bin/env bash
#
# validate-site-ok.sh — confirm a wiki URL renders OK. Used by the deploy skills
# for the local-verify and prod-smoke steps.
#
# A MediaWiki fatal (e.g. a syntax error in LocalSettings) returns HTTP 500 with
# display_errors OFF on prod — so the body may contain NO "fatal" text. The
# reliable signal is therefore the HTTP STATUS, not a body grep; body markers are
# a secondary check for errors that still return 200.
#
# Usage: bash validate-site-ok.sh <url> [user-agent]
#   <url>         page to fetch
#   [user-agent]  optional UA; prod's edge blocks bare requests, so for prod pass
#                 "$MACCABIPEDIA_UA_SCRIPT"
#
# Exit: 0 = OK (HTTP 200, no error markers)
#       1 = rendered but broken (non-200, or 200 with a PHP error marker)
#       2 = unreachable (no response — network down or edge block)
set -euo pipefail

URL="${1:?usage: validate-site-ok.sh <url> [user-agent]}"
UA="${2:-}"

body="$(mktemp)"
trap 'rm -f "$body"' EXIT

# Deliberately NOT using curl -f: we want the body + status even on HTTP 500 so
# we can tell a fatal (500) apart from an unreachable host (no response). curl's
# -w already prints "000" when there is no response, so `|| true` (not an extra
# echo) keeps set -e happy without doubling the status.
status="$(curl -sS ${UA:+-A "$UA"} -o "$body" -w '%{http_code}' "$URL" 2>/dev/null || true)"
status="${status:-000}"

if [ "$status" = "000" ]; then
    echo "UNREACHABLE: no response from $URL (host down, or prod edge blocking the request)." >&2
    exit 2
fi

if [ "$status" != "200" ]; then
    echo "BROKEN: $URL returned HTTP $status (a PHP fatal returns 500 even with display_errors off)." >&2
    exit 1
fi

if grep -qiE 'MWException|Fatal error|Parse error|Uncaught (Error|Exception)' "$body"; then
    echo "BROKEN: $URL is HTTP 200 but the body contains a PHP error marker." >&2
    exit 1
fi

echo "OK: $URL renders (HTTP 200, no error markers)."
