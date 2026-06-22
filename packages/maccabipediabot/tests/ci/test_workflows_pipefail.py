"""Guard against the silent-failure-via-`tee` gotcha in CI workflows.

GitHub's implicit default shell for a `run:` step is ``bash -e {0}`` — it does
NOT enable ``pipefail``. So a step like::

    uv run python -m some.module 2>&1 | tee -a /tmp/log

takes its exit code from ``tee`` (always 0), masking a non-zero exit from the
python command. A failed upload then looks like a green step, the job's
``if: failure()`` alert chain never fires, and the missed game vanishes
silently. This actually happened to the basketball uploader: a transient wiki
login failure crashed the uploader, but the run stayed green and no alert went
out.

This test fails for any ``run:`` step that pipes through ``tee`` unless the job
opts into ``pipefail`` — via ``defaults.run.shell: bash`` (which uses
``bash --noprofile --norc -eo pipefail {0}``), a step-level ``shell: bash``, or
an inline ``set -o pipefail`` / ``set -eo pipefail``.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def _find_workflows_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".github" / "workflows"
        if candidate.is_dir():
            return candidate
    raise AssertionError("Could not locate .github/workflows from the test file")


def _shell_enables_pipefail(shell: object) -> bool:
    # GitHub runs an explicit `shell: bash` as `bash --noprofile --norc -eo pipefail {0}`.
    # A custom shell string that spells out pipefail also counts.
    if shell == "bash":
        return True
    return isinstance(shell, str) and "pipefail" in shell


def _iter_piped_tee_steps(workflow: dict):
    """Yield (job_id, step, job_defaults_shell) for run-steps that pipe through tee."""
    for job_id, job in (workflow.get("jobs") or {}).items():
        job_shell = ((job.get("defaults") or {}).get("run") or {}).get("shell")
        for step in job.get("steps") or []:
            run = step.get("run")
            if isinstance(run, str) and "| tee" in run:
                yield job_id, step, job_shell


def _step_is_protected(step: dict, job_shell: object, workflow_shell: object) -> bool:
    if _shell_enables_pipefail(step.get("shell")):
        return True
    if _shell_enables_pipefail(job_shell):
        return True
    if _shell_enables_pipefail(workflow_shell):
        return True
    run = step.get("run", "")
    return "set -o pipefail" in run or "set -eo pipefail" in run


def _collect_violations():
    violations = []
    for path in sorted(_find_workflows_dir().glob("*.y*ml")):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(workflow, dict):
            continue
        workflow_shell = ((workflow.get("defaults") or {}).get("run") or {}).get("shell")
        for job_id, step, job_shell in _iter_piped_tee_steps(workflow):
            if not _step_is_protected(step, job_shell, workflow_shell):
                violations.append(f"{path.name}:{job_id}:{step.get('name', step.get('id', '?'))}")
    return violations


def test_piped_tee_run_steps_enable_pipefail():
    violations = _collect_violations()
    assert not violations, (
        "These run-steps pipe through `tee` without pipefail, so a failing "
        "command's exit code is masked by tee (exit 0) and the failure is "
        "silent. Add `defaults.run.shell: bash` to the job (or `set -o "
        "pipefail`):\n  " + "\n  ".join(violations)
    )
