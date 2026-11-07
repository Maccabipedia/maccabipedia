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


def gh_api(path, raw=False):
    """GET a GitHub API path through the gh CLI; JSON unless raw."""
    completed = subprocess.run(
        ["gh", "api", path], capture_output=True, text=True, check=True
    )
    return completed.stdout if raw else json.loads(completed.stdout)


def failure_tail(log):
    """The last lines a failed step printed before GitHub's ##[error] marker.

    Timestamps and ##[group] markers are dropped, credentials in URLs redacted. GitHub
    already masks registered secrets in stored logs; this covers user:pass@ URLs a
    script may build itself.
    """
    lines = [_TIMESTAMP.sub("", line) for line in log.splitlines()]
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


def failed_steps(jobs):
    """(job, step name or None) for every failed job; None when no step is marked."""
    failures = []
    for job in jobs:
        if job.get("conclusion") not in ("failure", "timed_out"):
            continue
        steps = [s["name"] for s in job.get("steps", []) if s.get("conclusion") == "failure"]
        failures.append((job, steps[0] if steps else None))
    return failures


def build_message(run, failures, tails_by_job_id):
    """Telegram HTML message. Everything from the run is escaped once (Bot API direct)."""
    branch = run.get("head_branch") or "?"
    lines = [
        f"❌ <b>{html.escape(run['name'], quote=False)}</b> failed "
        f"({html.escape(run['event'], quote=False)}, {html.escape(branch, quote=False)})"
    ]
    if not failures:
        lines.append(f"No failed step recorded (conclusion: {html.escape(run['conclusion'], quote=False)}).")
    for job, step in failures:
        step_text = html.escape(step, quote=False) if step else "(no step marked failed: setup or timeout)"
        lines.append(f"Failed step: {html.escape(job['name'], quote=False)} › {step_text}")
        tail = tails_by_job_id.get(job["id"])
        if tail:
            lines.append(f"<pre>{html.escape(tail, quote=False)}</pre>")
    lines.append(f"Run: {run['html_url']}")
    return "\n".join(lines)


def send_telegram(token, chat_id, message):
    body = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": message, "parse_mode": "HTML",
         "disable_web_page_preview": "true"}
    ).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=body
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            reply = json.loads(response.read())
    except urllib.error.HTTPError as error:
        # The URL carries the bot token: report the status and Telegram's reason only.
        sys.exit(f"Telegram refused the alert: HTTP {error.code} {error.read().decode()[:300]}")
    if not reply.get("ok"):
        sys.exit(f"Telegram refused the alert: {reply}")


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
            tails[job["id"]] = failure_tail(gh_api(f"repos/{repo}/actions/jobs/{job['id']}/logs", raw=True))
        except subprocess.CalledProcessError as error:
            # A missing log must not cost the alert itself: send the step and link anyway.
            print(f"could not read log of job {job['id']}: {error.stderr.strip()}", file=sys.stderr)
    message = build_message(run, failures, tails)

    if args.dry_run:
        print(message)
        return
    send_telegram(os.environ["TELEGRAM_TOKEN"], os.environ["TELEGRAM_TO"], message)
    print("alert sent")


if __name__ == "__main__":
    main()
