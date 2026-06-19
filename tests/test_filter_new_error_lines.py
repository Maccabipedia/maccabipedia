"""Regression tests for the CI dedup helper `.github/scripts/filter_new_error_lines.sh`.

The helper diffs today's MaccabiPedia error report against the previous run's
baseline and emits only the error lines that are new, each under its category
header. The report format is an implicit contract with
`maccabistats.github_actions_scripts.find_maccabipedia_errors`:

  - category headers start at column 0      (e.g. "Games with missing goals events:")
  - error entries are indented with a space (e.g. "    1947-05-17 ...")
  - the dynamic "Showing errors for: ... N games (from..to..):" summary also starts
    at column 0, so it is treated as a header and must never leak into the output.

These tests pin that behavior so a change to either side surfaces here.
"""

import subprocess
from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "filter_new_error_lines.sh"

TODAY = """\
Showing errors for: Source: MaccabiPedia + Official games | 273 games | (from 26-06-1926 to 03-06-1950):


League games with the same season and fixture:
    Season 1930/31 Fixture None: [game a, game b]

Games with missing goals events:
    1926-06-26 מגן שמשון: מכבי ירושלים(1) - (6)מכבי תל אביב
    1930-10-04 הליגה הארצית: מכבי תל אביב(4) - (2)
"""


def _run(baseline_text: str, today_text: str, tmp_path: Path) -> str:
    baseline = tmp_path / "baseline.txt"
    today = tmp_path / "today.txt"
    baseline.write_text(baseline_text, encoding="utf-8")
    today.write_text(today_text, encoding="utf-8")
    result = subprocess.run(
        ["bash", str(HELPER), str(baseline), str(today)],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def test_identical_baseline_emits_nothing(tmp_path):
    assert _run(TODAY, TODAY, tmp_path) == ""


def test_empty_baseline_emits_all_entries_with_headers(tmp_path):
    out = _run("", TODAY, tmp_path)
    entries = [line for line in out.splitlines() if line.startswith("    ")]
    assert len(entries) == 3
    assert "League games with the same season and fixture:" in out
    assert "Games with missing goals events:" in out
    # The volatile summary line must not leak as a "new" line.
    assert "Showing errors for:" not in out


def test_only_new_entry_is_emitted_under_its_header(tmp_path):
    # Baseline is today minus the 1930-10-04 line -> only that line is new.
    baseline = TODAY.replace("    1930-10-04 הליגה הארצית: מכבי תל אביב(4) - (2)\n", "")
    out = _run(baseline, TODAY, tmp_path)
    entries = [line for line in out.splitlines() if line.startswith("    ")]
    assert entries == ["    1930-10-04 הליגה הארצית: מכבי תל אביב(4) - (2)"]
    assert "Games with missing goals events:" in out
    # The unrelated, already-seen category must not be echoed.
    assert "League games with the same season and fixture:" not in out


def test_summary_line_change_alone_emits_nothing(tmp_path):
    # Only the dynamic summary line differs (game count / date range) -> no new errors.
    baseline = TODAY.replace("273 games | (from 26-06-1926 to 03-06-1950)",
                             "271 games | (from 26-06-1926 to 01-06-1950)")
    assert _run(baseline, TODAY, tmp_path) == ""
