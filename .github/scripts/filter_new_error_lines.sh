#!/usr/bin/env bash
# Emit only the error lines in TODAY that are NOT present in BASELINE, each grouped
# under its category header so the alert keeps its context.
#
# Usage: filter_new_error_lines.sh <baseline_report> <today_report>
#
# The MaccabiPedia error report is line-oriented:
#   - category headers start at column 0 (e.g. "Games with missing goals events:")
#   - error entries are indented with a leading space (e.g. "    1947-05-17 ...")
#   - blank lines separate sections
# We compare only the indented entries against the baseline, and print each new entry
# under the header that introduced it. The dynamic summary line
# ("Showing errors for: ... N games (from..to..):") also starts at column 0, so it is
# treated as a header and is overwritten by the real category header before any entry
# is printed -- it never leaks into the output.
set -euo pipefail

baseline="$1"
today="$2"

# NOTE: we preload the baseline via getline rather than the usual `NR==FNR` two-file
# idiom. On the first run (and after a cache eviction) the baseline file is empty, and
# with an empty first file `NR==FNR` stays true while reading the second file, which
# would suppress the entire first-run dump. getline-preload handles an empty/missing
# baseline correctly: nothing is seen, so every entry is reported.
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
