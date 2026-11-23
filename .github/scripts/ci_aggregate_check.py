"""Verify that the aggregate CI job waits for every other job, so one required check covers the whole run.

Usage (from the repository root):

    python .github/scripts/ci_aggregate_check.py .github/workflows/ci.yml --job ci-ok

Branch protection requires checks by name. The matrix job reports one check per entry (``Tests · orbitdesk``, …),
so the rule names a single aggregate job instead. That only holds while the aggregate job lists every other job in
``needs`` and runs with ``if: always()`` (without it, a red job makes the aggregate job *skipped*, not red). This
script fails with exit code 1 and a GitHub ``::error`` annotation when either is not true.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def problems(workflow: object, job_id: str) -> tuple[list[str], int]:
    """Error messages for the aggregate job, and the number of other jobs it has to wait for."""
    jobs = workflow.get("jobs") if isinstance(workflow, dict) else None
    if not isinstance(jobs, dict) or not jobs:
        return ["the workflow has no jobs mapping"], 0
    if job_id not in jobs:
        return [
            f"aggregate job '{job_id}' not found; jobs are: {', '.join(sorted(map(str, jobs)))}"
        ], 0
    job = jobs[job_id] if isinstance(jobs[job_id], dict) else {}
    others = {str(name) for name in jobs if name != job_id}

    needs = job.get("needs", [])
    listed = {needs} if isinstance(needs, str) else {str(name) for name in needs or []}
    errors = [
        f"'{job_id}' does not wait for job '{name}'; add it to needs"
        for name in sorted(others - listed)
    ]
    errors += [
        f"'{job_id}' needs unknown job '{name}'" for name in sorted(listed - others)
    ]

    condition = str(job.get("if", ""))
    if "always()" not in condition:
        errors.append(
            f"'{job_id}' needs `if: always()`; otherwise a red job skips it instead of failing it"
        )
    return errors, len(others)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check that the aggregate CI job waits for every other job."
    )
    parser.add_argument("workflow", type=Path)
    parser.add_argument("--job", default="ci-ok")
    args = parser.parse_args(argv)

    try:
        workflow = yaml.safe_load(args.workflow.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        print(f"::error file={args.workflow.as_posix()}::cannot read workflow: {error}")
        return 1

    errors, count = problems(workflow, args.job)
    for message in errors:
        print(f"::error file={args.workflow.as_posix()}::{message}")
    if errors:
        return 1
    print(f"{args.job} needs all {count} other jobs and runs with if: always().")
    return 0


if __name__ == "__main__":
    sys.exit(main())
