#!/usr/bin/env bash
#
# validate-site-ok.sh — confirm a wiki URL renders OK. Used by the deploy skills
# for the local-verify and prod-smoke steps.
#
# A MediaWiki fatal surfaces TWO different ways depending on display_errors, so
# both signals are needed (verified by inducing a real LocalSettings break):
#   - prod (display_errors OFF): HTTP 500, body may have NO error text -> STATUS
#     catches it.
#   - local dev (display_errors ON): HTTP 200 with "Fatal error"/"Warning" in the
#     body -> the BODY GREP catches it (status alone would miss it).
# Neither check is secondary.
#
# Usage: bash validate-site-ok.sh <url>
#   <url>  page to fetch
#
# No User-Agent is set: curl's default UA already satisfies MediaWiki's UA
# policy, and prod's edge block is IP-based (a custom UA does not bypass it), so
# passing $MACCABIPEDIA_UA_SCRIPT here added nothing. That env var is for
# pywikibot/API bot calls, not for reading public pages.
#
# Exit: 0 = OK (HTTP 200, no error markers)
#       1 = rendered but broken (non-200, or 200 with a PHP error marker)
#       2 = unreachable (no response — network down or edge block)
set -euo pipefail

URL="${1:?usage: validate-site-ok.sh <url>}"

body="$(mktemp)"
trap 'rm -f "$body"' EXIT

# Deliberately NOT using curl -f: we want the body + status even on HTTP 500 so
# we can tell a fatal (500) apart from an unreachable host (no response). curl's
# -w already prints "000" when there is no response, so `|| true` (not an extra
# echo) keeps set -e happy without doubling the status.
status="$(curl -sS -o "$body" -w '%{http_code}' "$URL" 2>/dev/null || true)"
status="${status:-000}"

if [ "$status" = "000" ]; then
    echo "UNREACHABLE: no response from $URL (host down, or prod edge blocking the request)." >&2
    exit 2
fi

if [ "$status" != "200" ]; then
    echo "BROKEN: $URL returned HTTP $status (a PHP fatal returns 500 even with display_errors off)." >&2
    exit 1
fi

# Match PHP's *rendered* error HTML (display_errors on) and MediaWiki's own
# exception page — NOT the bare string "Fatal error", which legitimately appears
# inside page JS and would false-positive on a healthy wiki.
if grep -qiE '<b>(Fatal error|Parse error)</b>|MWException|MediaWiki internal error' "$body"; then
    echo "BROKEN: $URL is HTTP 200 but the body contains a rendered PHP/MediaWiki error." >&2
    exit 1
fi

echo "OK: $URL renders (HTTP 200, no error markers)."
