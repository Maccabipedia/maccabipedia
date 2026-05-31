#!/usr/bin/env bash
#
# install-playwright-browser.sh — install the Playwright Chromium browser used by
# the skin's browser test (infra/local-wiki/tests/test_maccabipedia_interactive.py).
# Run once on a deploy machine so that test runs instead of silently skipping
# (it does importorskip("playwright")). Idempotent.
#
# Usage: bash install-playwright-browser.sh
set -euo pipefail

uv run --with playwright playwright install chromium
echo "Chromium installed for Playwright — the interactive skin test will now run (not skip)."
