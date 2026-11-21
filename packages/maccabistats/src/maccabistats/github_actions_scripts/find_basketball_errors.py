"""Run every basketball check on the games on MaccabiPedia and write the findings.

usage: uv run python -m maccabistats.github_actions_scripts.find_basketball_errors [--out findings.tsv]

Read-only: it queries Cargo and edits nothing. The TSV has one row per finding
(check, season, page, detail), written with a BOM so Excel shows the Hebrew.
"""
import argparse
import csv
import logging
from pathlib import Path

from maccabistats import BasketballErrorsFinder, load_basketball_from_maccabipedia
from maccabistats.maccabilogging import remove_live_logging

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("basketball_errors.tsv"))
    args = parser.parse_args()
    logging.basicConfig(format="%(message)s", level=logging.INFO)
    # maccabistats logs to stderr by itself; without this every one of its lines shows twice
    remove_live_logging()

    basketball_games = load_basketball_from_maccabipedia()
    results = BasketballErrorsFinder(basketball_games.games).find_all()

    with args.out.open("w", encoding="utf-8-sig", newline="") as out_file:
        writer = csv.writer(out_file, delimiter="\t")
        writer.writerow(["check", "season", "page", "detail"])
        for findings in results.values():
            for finding in findings:
                writer.writerow([finding.check, finding.game.season, finding.game.page_name, finding.detail])

    logger.info(f"{len(basketball_games)} games checked")
    for name, findings in results.items():
        logger.info(f"  {name:<62} {len(findings)}")
    logger.info(f"Findings written to {args.out}")


if __name__ == "__main__":
    main()
