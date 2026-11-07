"""Every workflow that can fail outside a pull request must reach the error channel.

`.github/workflows/alert_on_workflow_failure.yaml` watches workflows by name. A new
workflow, or a renamed one, silently drops out of that list, which is how
update_league_table_status stayed red for three weeks. These tests fail instead.
Also pins the message the alert script builds from a real failed run's log.
"""

import importlib.util
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / ".github" / "workflows"
WATCHER = WORKFLOWS / "alert_on_workflow_failure.yaml"

# Alert on their own failure, with a message that knows their steps.
SELF_ALERTING = {"Upload Basketball Games To MaccabiPedia", "Upload Tickets From Telegram"}

_spec = importlib.util.spec_from_file_location(
    "alert_workflow_failure", REPO / ".github" / "scripts" / "alert_workflow_failure.py"
)
alert = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(alert)


def _load(path):
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    # PyYAML reads the bare key `on` as the boolean True.
    triggers = workflow.get("on", workflow.get(True))
    if isinstance(triggers, str):
        triggers = {triggers: None}
    elif isinstance(triggers, list):
        triggers = dict.fromkeys(triggers)
    return workflow["name"], set(triggers), path.read_text(encoding="utf-8")


ALL = {name: (triggers, text) for name, triggers, text in map(_load, sorted(WORKFLOWS.glob("*.y*ml")))}
WATCHER_NAME = _load(WATCHER)[0]
WATCHED = set(yaml.safe_load(WATCHER.read_text(encoding="utf-8"))[True]["workflow_run"]["workflows"])


def test_watched_names_are_real_workflows():
    assert WATCHED - set(ALL) == set(), "watcher names a workflow that does not exist (renamed?)"


@pytest.mark.parametrize("name", sorted(set(ALL) - {WATCHER_NAME}))
def test_every_workflow_that_runs_outside_a_pr_is_alerted(name):
    triggers, text = ALL[name]
    if triggers <= {"pull_request"}:
        assert name not in WATCHED
        return
    if name in SELF_ALERTING:
        assert name not in WATCHED, "alerts on its own; watching it would alert twice"
        assert "if: failure()" in text and "MACCABIPEDIA_ERRORS_TELEGRAM_TO" in text
        return
    assert name in WATCHED, f"add '{name}' to {WATCHER.name} (or to SELF_ALERTING here)"


LOG = """\
2026-11-07T20:22:11.3215044Z ##[group]Run uv run python -m maccabipediabot.volleyball.update_league_table_volleyball
2026-11-07T20:22:11.3216000Z ##[endgroup]
2026-11-07T20:22:17.2919480Z   File "<frozen runpy>", line 88, in _run_code
2026-11-07T20:22:17.2920000Z fetching https://bot:hunter2@example.com/api
2026-11-07T20:22:17.2933818Z KeyError: 'Column not found. Patterns: [\\'נצ\\', \\'נצחונות\\']'
2026-11-07T20:22:17.3728273Z ##[error]Process completed with exit code 1.
2026-11-07T20:22:17.3772929Z ##[group]Run uv run python -m maccabipediabot.basketball.update_league_table_basketball
2026-11-07T20:22:21.0000000Z later step output
"""


def test_tail_stops_at_the_error_and_drops_markers_and_timestamps():
    tail = alert.failure_tail(LOG)
    assert tail.splitlines() == [
        '  File "<frozen runpy>", line 88, in _run_code',
        "fetching https://[redacted]@example.com/api",
        "KeyError: 'Column not found. Patterns: [\\'נצ\\', \\'נצחונות\\']'",
    ]


def test_tail_drops_terminal_color_codes():
    log = "2026-11-07T20:22:17.0Z \x1b[36;1mKeyError\x1b[0m: boom\n2026-11-07T20:22:17.1Z ##[error]exit 1\n"
    assert alert.failure_tail(log) == "KeyError: boom"


def test_tail_without_error_marker_keeps_the_end():
    log = "\n".join(f"2026-11-07T20:22:11.0Z line {i}" for i in range(40))
    assert alert.failure_tail(log).splitlines() == [f"line {i}" for i in range(25, 40)]


RUN = {
    "name": "Update league table status",
    "event": "schedule",
    "head_branch": "master",
    "conclusion": "failure",
    "html_url": "https://github.com/o/r/actions/runs/1",
}


def test_message_names_the_step_escapes_the_log_and_links_the_run():
    jobs = [
        {"id": 7, "name": "upload-league-table-status", "conclusion": "failure", "steps": [
            {"name": "Fetch Football league table", "conclusion": "success"},
            {"name": "Fetch Volleyball league table", "conclusion": "failure"},
        ]},
        {"id": 8, "name": "workflow-keepalive", "conclusion": "skipped", "steps": []},
    ]
    message = alert.build_message(RUN, alert.failed_steps(jobs), {7: alert.failure_tail(LOG)})
    assert "<b>Update league table status</b> failed (schedule, master)" in message
    assert "Failed step: upload-league-table-status › Fetch Volleyball league table" in message
    assert "&lt;frozen runpy&gt;" in message and "<frozen" not in message
    assert "keepalive" not in message
    assert message.endswith("Run: https://github.com/o/r/actions/runs/1")


def test_job_that_failed_without_a_failed_step_still_alerts():
    jobs = [{"id": 9, "name": "build", "conclusion": "timed_out", "steps": []}]
    message = alert.build_message(RUN, alert.failed_steps(jobs), {})
    assert "Failed step: build › (no step marked failed" in message


def test_two_failed_jobs_with_long_logs_fit_one_telegram_message():
    jobs = [
        {"id": job_id, "name": name, "conclusion": "failure",
         "steps": [{"name": "Install dependencies", "conclusion": "failure"}]}
        for job_id, name in ((1, "test"), (2, "lua"))
    ]
    long_tail = "x" * alert.TAIL_MAX_CHARS
    message = alert.build_message(RUN, alert.failed_steps(jobs), {1: long_tail, 2: long_tail})
    assert message.count("<pre>") == 2
    assert len(message) < 4096


def test_hung_job_killed_at_timeout_alerts_as_cancelled():
    # Shape of run 41391378152: the football calendar hung 6 hours and GitHub killed it.
    jobs = [{"id": 3, "name": "update-maccabipedia-calendar", "conclusion": "cancelled", "steps": [
        {"name": "Install dependencies", "conclusion": "success"},
        {"name": "Update MaccabiPedia Calendar", "conclusion": "cancelled"},
    ]}]
    message = alert.build_message({**RUN, "conclusion": "cancelled"}, alert.failed_steps(jobs), {})
    assert "cancelled (timed out, or cancelled by hand)" in message
    assert "› Update MaccabiPedia Calendar" in message


def test_run_with_no_jobs_says_so():
    message = alert.build_message({**RUN, "conclusion": "startup_failure"}, [], {})
    assert "No failed step recorded (conclusion: startup_failure)" in message
