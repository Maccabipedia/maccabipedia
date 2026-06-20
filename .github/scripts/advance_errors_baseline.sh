#!/usr/bin/env bash
# Overwrite the cached baseline with today's full report so persistent errors are not
# re-sent next run. Run only after the Telegram sends succeed, so a failed delivery
# leaves the baseline unchanged and the errors are retried next run.
# Reads $DATE (today's report filename prefix) from the environment.
set -euo pipefail

baseline_dir="error-report-baseline"

cp "${DATE}__maccabipedia_errors_before_1950.txt" "$baseline_dir/before_1950.txt"
cp "${DATE}__maccabipedia_errors_after_1950.txt" "$baseline_dir/after_1950.txt"
