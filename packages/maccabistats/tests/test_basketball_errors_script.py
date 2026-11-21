"""The daily basketball-errors job: what it writes, and what it calls new against the previous run."""
import sys

import pytest

from maccabistats.basketball.error_finder import BasketballErrorsFinder, Finding
from maccabistats.basketball.parse import game_from_cargo
from maccabistats.basketball.stats import BasketballGamesStats
from maccabistats.github_actions_scripts import find_basketball_errors as script

PAGE = "כדורסל:01-04-1969 הפועל תל אביב נגד מכבי תל אביב - הליגה הלאומית"
HAPOEL_1969 = game_from_cargo({"_pageName": PAGE, "Date": "1969-04-01", "Season": "1968/69",
                               "Competition": "הליגה הלאומית", "Opponent": "הפועל תל אביב", "HomeAway": "חוץ",
                               "TotalPointsMaccabi": 65, "TotalPointsOpponent": 67, "ResultOpt": 3}, {})
TIE = Finding("tie_result", HAPOEL_1969, "65:65, leg ''")
MISSING_OVERTIME = Finding("missing_overtime", HAPOEL_1969, "halves add up to 60:60, final 65:67, no overtime points")
ORPHAN_ROW = Finding("player_row_without_game", None, "חיים תור, Team 0", page_name_without_game="כדורסל:משחק שנמחק")
RESULTS = {"get_games_missing_overtime": [MISSING_OVERTIME], "get_games_with_tie_result": [TIE],
           "get_player_rows_without_game": [ORPHAN_ROW], "get_games_without_result": []}


def test_findings_file_reads_back_as_the_same_findings(tmp_path):
    out_path = tmp_path / "errors.tsv"

    script.write_findings(RESULTS, out_path)

    assert out_path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert script.read_baseline(out_path) == {
        ("missing_overtime", PAGE, MISSING_OVERTIME.detail), ("tie_result", PAGE, TIE.detail),
        ("player_row_without_game", "כדורסל:משחק שנמחק", "חיים תור, Team 0")}


def test_first_run_with_no_baseline_calls_nothing_new(tmp_path):
    assert script.read_baseline(tmp_path / "no-such-file.tsv") is None
    assert script.new_findings_report(RESULTS, None) == ""


def test_only_findings_the_baseline_lacks_are_new(tmp_path):
    baseline_path = tmp_path / "baseline.tsv"
    script.write_findings({"get_games_missing_overtime": [MISSING_OVERTIME]}, baseline_path)

    report = script.new_findings_report(RESULTS, script.read_baseline(baseline_path))

    assert report == (f"get_games_with_tie_result (1):\n    {PAGE}: 65:65, leg ''\n\n"
                      "get_player_rows_without_game (1):\n    כדורסל:משחק שנמחק: חיים תור, Team 0")


def test_same_findings_as_the_baseline_give_an_empty_report(tmp_path):
    baseline_path = tmp_path / "baseline.tsv"
    script.write_findings(RESULTS, baseline_path)

    assert script.new_findings_report(RESULTS, script.read_baseline(baseline_path)) == ""


def test_empty_baseline_file_of_a_clean_run_makes_every_finding_new(tmp_path):
    baseline_path = tmp_path / "baseline.tsv"
    script.write_findings({}, baseline_path)

    assert script.new_findings_report(RESULTS, script.read_baseline(baseline_path)).count("\n    ") == 3


def test_file_that_is_not_a_findings_file_is_refused(tmp_path):
    baseline_path = tmp_path / "baseline.tsv"
    baseline_path.write_text("something else\n", encoding="utf-8")

    with pytest.raises(ValueError, match="not a findings file"):
        script.read_baseline(baseline_path)


def _run_main(monkeypatch, tmp_path, arguments: list[str]) -> str:
    github_output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))
    monkeypatch.setattr(script, "load_basketball_from_maccabipedia", lambda: BasketballGamesStats([HAPOEL_1969]))
    monkeypatch.setattr(script, "remove_live_logging", lambda: None)
    monkeypatch.setattr(sys, "argv", ["find_basketball_errors"] + arguments)
    script.main()
    return github_output.read_text() if github_output.exists() else ""


def test_job_sends_nothing_on_its_first_run_and_only_the_new_finding_after(monkeypatch, tmp_path):
    out_path, baseline_path, new_path = tmp_path / "today.tsv", tmp_path / "baseline.tsv", tmp_path / "new.txt"
    arguments = ["--out", str(out_path), "--baseline", str(baseline_path), "--new-out", str(new_path)]

    assert _run_main(monkeypatch, tmp_path, arguments) == "has_new=false\n"
    assert new_path.read_text(encoding="utf-8") == ""
    expected_checks = len(BasketballErrorsFinder([HAPOEL_1969]).find_all())
    assert expected_checks == 28 and "no_box_score" in out_path.read_text(encoding="utf-8-sig")

    # The next day's baseline lacks one of today's findings
    kept_lines = [line for line in out_path.read_text(encoding="utf-8-sig").splitlines() if "no_box_score" not in line]
    baseline_path.write_text("\n".join(kept_lines) + "\n", encoding="utf-8-sig")

    assert _run_main(monkeypatch, tmp_path, arguments).endswith("has_new=true\n")
    assert new_path.read_text(encoding="utf-8") == f"get_games_without_box_score (1):\n    {PAGE}: no players on either side"


def test_baseline_without_new_out_is_refused(monkeypatch, tmp_path):
    with pytest.raises(SystemExit):
        _run_main(monkeypatch, tmp_path, ["--baseline", str(tmp_path / "baseline.tsv")])
