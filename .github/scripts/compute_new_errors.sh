#!/usr/bin/env bash
# Diff today's MaccabiPedia error reports against the cached baseline and write the
# new-only reports (new_<segment>.txt) plus has_new_* outputs for the Telegram steps.
# Reads $DATE (today's report filename prefix) and $GITHUB_OUTPUT from the environment.
set -euo pipefail

baseline_dir="error-report-baseline"
script_dir="$(dirname "$0")"

mkdir -p "$baseline_dir"
touch "$baseline_dir/before_1950.txt" "$baseline_dir/after_1950.txt"

write_new_errors() {
  local segment="$1" output_name="$2"
  bash "$script_dir/filter_new_error_lines.sh" \
    "$baseline_dir/${segment}.txt" \
    "${DATE}__maccabipedia_errors_${segment}.txt" > "new_${segment}.txt"
  if [ -s "new_${segment}.txt" ]; then
    echo "${output_name}=true" >> "$GITHUB_OUTPUT"
  else
    echo "${output_name}=false" >> "$GITHUB_OUTPUT"
  fi
}

write_new_errors before_1950 has_new_before
write_new_errors after_1950 has_new_after
