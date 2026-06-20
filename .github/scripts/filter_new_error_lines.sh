#!/usr/bin/env bash
# Print the error lines in <today_report> not present in <baseline_report>, each under
# its category header. Report lines: headers at column 0, error entries indented, blanks
# between sections. The volatile "Showing errors for: ..." summary line is a column-0
# line, so it is treated as a header and never leaks as a "new" error.
# Usage: filter_new_error_lines.sh <baseline_report> <today_report>
set -euo pipefail

baseline="$1"
today="$2"

# getline-preload, not NR==FNR: on the first run the baseline is empty, and NR==FNR would
# then stay true for the second file and suppress the entire first-run dump.
awk -v base="$baseline" '
  BEGIN { while ((getline line < base) > 0) seen[line] = 1 }
  /^$/  { next }
  /^ /  {
          if (!($0 in seen)) {
            if (!printed_header) { if (emitted) print ""; print header; printed_header = 1; emitted = 1 }
            print
          }
          next
        }
        { header = $0; printed_header = 0 }
' "$today"
