"""Run every basketball check on the games on prod and write the findings.

usage: uv run python -m maccabipediabot.basketball.error_finder [--out findings.tsv]

Read-only: it queries Cargo and edits nothing. The TSV has one row per finding
(check, season, page, detail), written with a BOM so Excel shows the Hebrew.
"""
import argparse
import csv
import logging
from pathlib import Path

from maccabipediabot.basketball.error_finder.error_finder import BasketballErrorsFinder
from maccabipediabot.basketball.error_finder.games import fetch_basketball_games

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("basketball_errors.tsv"))
    args = parser.parse_args()
    logging.basicConfig(format="%(message)s", level=logging.INFO)

    games = fetch_basketball_games()
    results = BasketballErrorsFinder(games).find_all()

    with args.out.open("w", encoding="utf-8-sig", newline="") as out_file:
        writer = csv.writer(out_file, delimiter="\t")
        writer.writerow(["check", "season", "page", "detail"])
        for findings in results.values():
            for finding in findings:
                writer.writerow([finding.check, finding.game.season, finding.game.page_name, finding.detail])

    logger.info("%d games checked", len(games))
    for name, findings in results.items():
        logger.info("  %-62s %d", name, len(findings))
    logger.info("Findings written to %s", args.out)


if __name__ == "__main__":
    main()
