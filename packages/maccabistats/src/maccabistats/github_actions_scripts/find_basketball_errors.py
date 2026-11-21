"""Run every basketball check on the games on MaccabiPedia and write the findings.

usage: uv run python -m maccabistats.github_actions_scripts.find_basketball_errors [--out findings.tsv]
           [--baseline previous_findings.tsv --new-out new_findings.txt]

Read-only: it queries Cargo and edits nothing. The TSV has one row per finding
(check, season, page, detail), written with a BOM so Excel shows the Hebrew.

With --baseline (a TSV an earlier run wrote) it also writes the findings that were not there
before to --new-out, grouped by check, for the daily job to send. When the baseline file does
not exist nothing is new: the first run only records what is there, so it does not send every
long-standing finding at once.
"""
import argparse
import csv
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from maccabistats import BasketballErrorsFinder, load_basketball_from_maccabipedia
from maccabistats.basketball.error_finder import Finding
from maccabistats.maccabilogging import remove_live_logging

logger = logging.getLogger(__name__)

# The daily job keeps a file of this shape in its cache as the baseline. Changing the columns makes
# every cached baseline unreadable and the job fail each day: bump the cache key in
# .github/workflows/show_basketball_errors.yaml (-v1- to -v2-) in the same change.
_HEADER = ["check", "season", "page", "detail"]
# What makes a finding the same finding the next day
FindingKey = Tuple[str, str, str]


def _row(finding: Finding) -> List[str]:
    return [finding.check, finding.season or "", finding.page_name, finding.detail]


def _key(row: List[str]) -> FindingKey:
    check, _season, page, detail = row
    return check, page, detail


def write_findings(results: Dict[str, List[Finding]], out_path: Path) -> None:
    with out_path.open("w", encoding="utf-8-sig", newline="") as out_file:
        writer = csv.writer(out_file, delimiter="\t")
        writer.writerow(_HEADER)
        for findings in results.values():
            writer.writerows(_row(finding) for finding in findings)


def read_baseline(baseline_path: Path) -> Optional[Set[FindingKey]]:
    """The findings of an earlier run, or None when there is no earlier run to compare with."""
    if not baseline_path.is_file():
        return None
    with baseline_path.open(encoding="utf-8-sig", newline="") as baseline_file:
        rows = list(csv.reader(baseline_file, delimiter="\t"))
    if not rows or rows[0] != _HEADER:
        raise ValueError(f"{baseline_path} is not a findings file written by this script")
    return {_key(row) for row in rows[1:]}


def new_findings_report(results: Dict[str, List[Finding]], baseline: Optional[Set[FindingKey]]) -> str:
    """The findings that are not in the baseline, grouped under their check's name. Empty when none."""
    if baseline is None:
        return ""

    sections = []
    for name, findings in results.items():
        new_rows = [_row(finding) for finding in findings if _key(_row(finding)) not in baseline]
        if new_rows:
            lines = [f"    {page}: {detail}" for _check, _season, page, detail in new_rows]
            sections.append("\n".join([f"{name} ({len(new_rows)}):"] + lines))
    return "\n\n".join(sections)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("basketball_errors.tsv"))
    parser.add_argument("--baseline", type=Path, help="The TSV of an earlier run")
    parser.add_argument("--new-out", type=Path, help="Where to write the findings the baseline does not have")
    args = parser.parse_args()
    if (args.baseline is None) != (args.new_out is None):
        parser.error("--baseline and --new-out go together")

    logging.basicConfig(format="%(message)s", level=logging.INFO)
    # maccabistats logs to stderr by itself; without this every one of its lines shows twice
    remove_live_logging()

    basketball_games = load_basketball_from_maccabipedia()
    results = BasketballErrorsFinder(basketball_games).find_all()
    write_findings(results, args.out)

    logger.info(f"{len(basketball_games)} games checked")
    for name, findings in results.items():
        logger.info(f"  {name:<62} {len(findings)}")
    logger.info(f"Findings written to {args.out}")

    if args.baseline is None:
        return

    baseline = read_baseline(args.baseline)
    if baseline is None:
        logger.info(f"No baseline at {args.baseline}: this run only records the findings, nothing is new")
    report = new_findings_report(results, baseline)
    args.new_out.write_text(report, encoding="utf-8")
    logger.info(f"{len(report.splitlines())} lines of new findings written to {args.new_out}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as github_output_file:
            github_output_file.write(f"has_new={'true' if report else 'false'}\n")


if __name__ == "__main__":
    main()
