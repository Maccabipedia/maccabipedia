"""Post a failed GitHub Actions run to the MaccabiPedia error channel on Telegram.

Called by `.github/workflows/alert_on_workflow_failure.yaml` for every watched workflow
that ends in failure outside a pull request. Reads the run, its jobs and each failed
job's log through `gh api`, and sends: the workflow, which job and step failed, the
log lines just before the step died, and the run link.

Stdlib + the `gh` CLI only, so the alert job needs no `uv sync`.

Usage:
    python3 .github/scripts/alert_workflow_failure.py <run_id> [--dry-run]

Env: GH_TOKEN (read actions), GITHUB_REPOSITORY, and unless --dry-run,
TELEGRAM_TOKEN and TELEGRAM_TO.
"""

import argparse
import html
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

TAIL_LINES = 15
TAIL_LINE_WIDTH = 200
TAIL_MAX_CHARS = 2500  # Telegram caps a message at 4096; leave room for the header.

_TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z ")
_URL_CREDENTIALS = re.compile(r"(https?://)[^/@\s]+@")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def gh_api(path):
    """GET a GitHub API path through the gh CLI, parsed as JSON."""
    completed = subprocess.run(
        ["gh", "api", path], capture_output=True, text=True, check=True
    )
    return json.loads(completed.stdout)


def job_log(repo, job_id):
    """A job's plain-text log.

    Not through `gh api`: logs carry color codes, and newer gh refuses to print
    them without a flag older gh does not know. The endpoint redirects to a signed
    storage URL; the token is an unredirected header so it is not sent there.
    """
    token = os.environ.get("GH_TOKEN") or subprocess.run(
        ["gh", "auth", "token"], capture_output=True, text=True, check=True
    ).stdout.strip()
    request = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/jobs/{job_id}/logs")
    request.add_unredirected_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def failure_tail(log):
    """The last lines a failed step printed before GitHub's ##[error] marker.

    Timestamps and ##[group] markers are dropped, credentials in URLs redacted. GitHub
    already masks registered secrets in stored logs; this covers user:pass@ URLs a
    script may build itself.
    """
    lines = [_TIMESTAMP.sub("", _ANSI.sub("", line)) for line in log.splitlines()]
    error_at = next(
        (i for i, line in enumerate(lines) if line.startswith("##[error]")), len(lines)
    )
    before_error = [
        line[:TAIL_LINE_WIDTH]
        for line in lines[:error_at]
        if not line.startswith(("##[group]", "##[endgroup]"))
    ]
    tail = "\n".join(before_error[-TAIL_LINES:])
    tail = _URL_CREDENTIALS.sub(r"\1[redacted]@", tail)
    return tail[-TAIL_MAX_CHARS:]


# A job that hits its timeout (timeout-minutes, or GitHub's 6-hour default) ends
# "cancelled", not "timed_out": the football calendar hung that way on 2026-11-02.
# No watched workflow cancels its own superseded runs, so a cancel is a hang or a
# person pressing Cancel; both are worth a line in the channel.
_FAILED = ("failure", "timed_out", "cancelled")


def failed_steps(jobs):
    """(job, step name or None) for every failed job; None when no step is marked."""
    failures = []
    for job in jobs:
        if job.get("conclusion") not in _FAILED:
            continue
        steps = [s["name"] for s in job.get("steps", []) if s.get("conclusion") in _FAILED]
        failures.append((job, steps[0] if steps else None))
    return failures


def build_message(run, failures, tails_by_job_id):
    """Telegram HTML message. Everything from the run is escaped once (Bot API direct).

    The tails share one budget, so a run with several failed jobs (Tests has two)
    still fits Telegram's 4096-character limit.
    """
    branch = run.get("head_branch") or "?"
    outcome = "cancelled (timed out, or cancelled by hand)" if run["conclusion"] == "cancelled" else "failed"
    lines = [
        f"❌ <b>{html.escape(run['name'], quote=False)}</b> {outcome} "
        f"({html.escape(run['event'], quote=False)}, {html.escape(branch, quote=False)})"
    ]
    if not failures:
        lines.append(f"No failed step recorded (conclusion: {html.escape(run['conclusion'], quote=False)}).")
    tail_budget = TAIL_MAX_CHARS // max(1, len(failures))
    for job, step in failures:
        step_text = html.escape(step, quote=False) if step else "(no step marked failed: setup or timeout)"
        lines.append(f"Failed step: {html.escape(job['name'], quote=False)} › {step_text}")
        tail = tails_by_job_id.get(job["id"], "")[-tail_budget:]
        if tail:
            lines.append(f"<pre>{html.escape(tail, quote=False)}</pre>")
    lines.append(f"Run: {run['html_url']}")
    return "\n".join(lines)


def send_telegram(token, chat_id, message, parse_mode="HTML"):
    """Send one message; return None on success, else Telegram's reason."""
    fields = {"chat_id": chat_id, "text": message, "disable_web_page_preview": "true"}
    if parse_mode:
        fields["parse_mode"] = parse_mode
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=urllib.parse.urlencode(fields).encode(),
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            reply = json.loads(response.read())
    except urllib.error.HTTPError as error:
        # The URL carries the bot token: report the status and Telegram's reason only.
        return f"HTTP {error.code} {error.read().decode()[:300]}"
    return None if reply.get("ok") else str(reply)[:300]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id", type=int)
    parser.add_argument("--dry-run", action="store_true", help="print, do not send")
    args = parser.parse_args()

    repo = os.environ["GITHUB_REPOSITORY"]
    run = gh_api(f"repos/{repo}/actions/runs/{args.run_id}")
    jobs = gh_api(f"repos/{repo}/actions/runs/{args.run_id}/jobs?per_page=100")["jobs"]
    failures = failed_steps(jobs)
    tails = {}
    for job, _ in failures:
        try:
            tails[job["id"]] = failure_tail(job_log(repo, job["id"]))
        except (OSError, subprocess.CalledProcessError) as error:
            # A missing log must not cost the alert itself: send the step and link anyway.
            # (urllib's HTTPError/URLError are OSErrors.)
            print(f"could not read log of job {job['id']}: {error}", file=sys.stderr)
    message = build_message(run, failures, tails)

    if args.dry_run:
        print(message)
        return
    token, chat_id = os.environ["TELEGRAM_TOKEN"], os.environ["TELEGRAM_TO"]
    refusal = send_telegram(token, chat_id, message)
    if refusal is None:
        print("alert sent")
        return
    # Nothing watches this workflow, so a refused alert would be silent. Fall back to
    # plain text with no log, which has nothing left for Telegram to reject.
    print(f"Telegram refused the full alert: {refusal}", file=sys.stderr)
    fallback = (
        f"❌ {run['name']} {run['conclusion']} ({run['event']}). "
        f"The detailed alert was refused by Telegram: {refusal[:200]}\nRun: {run['html_url']}"
    )
    second_refusal = send_telegram(token, chat_id, fallback, parse_mode=None)
    sys.exit("sent the short alert instead" if second_refusal is None
             else f"short alert refused too: {second_refusal}")


if __name__ == "__main__":
    main()
