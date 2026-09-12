"""Pure-logic tests for the perf benchmark: no network."""
import pytest

from benchmark_server import TEMPLATE_ROW, PageResult

# One real line from a prod NewPP transclusion expansion report.
REAL_ROW = " 62.89%  544.038      1 תבנית:עמוד_ראשי/משחקי_היום"
TOTAL_ROW = "100.00%  865.127      1 -total"


def test_template_row_parses_a_real_report_line():
    match = TEMPLATE_ROW.match(REAL_ROW)
    assert match is not None
    assert match.group("pct") == "62.89"
    assert match.group("ms") == "544.038"
    assert match.group("calls") == "1"
    assert match.group("template") == "תבנית:עמוד_ראשי/משחקי_היום"


def test_template_row_matches_the_total_line_so_callers_must_filter_it():
    # The runner drops "-total" explicitly; if this ever stops matching, that
    # filter becomes dead code and the ranking silently gains a bogus entry.
    match = TEMPLATE_ROW.match(TOTAL_ROW)
    assert match is not None
    assert match.group("template") == "-total"


def test_template_row_ignores_prose():
    assert TEMPLATE_ROW.match("Transclusion expansion time report (%,ms,calls,template)") is None


def test_db_wait_is_real_minus_cpu():
    result = PageResult(label="player_max", title="שרן ייני")
    result.counters = {"cpu_time": "1.296", "real_time": "3.944"}
    assert result.db_wait == pytest.approx(2.648)


def test_db_wait_is_none_when_the_page_has_no_limit_report():
    # Special:, search and category pages are never parser-cached.
    result = PageResult(label="search", title="מיוחד:חיפוש")
    result.counters = {"unavailable": "no limit report"}
    assert result.db_wait is None


def test_ttfb_median_and_p90_from_samples():
    result = PageResult(label="home", title="עמוד ראשי")
    result.ttfb_samples = [0.169, 0.185, 0.171, 0.180, 2.919]
    assert result.ttfb_median == pytest.approx(0.180)
    # p90 must surface the cold-parse outlier, not average it away.
    assert result.ttfb_p90 == pytest.approx(2.919)
