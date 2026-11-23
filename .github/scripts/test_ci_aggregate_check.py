"""Tests for ci_aggregate_check.py. Run from the repository root: python -m pytest -q .github/scripts"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ci_aggregate_check as aggregate  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

COMPLETE = """\
name: CI
on:
  push:
jobs:
  secrets:
    runs-on: ubuntu-latest
  python-tests:
    needs: secrets
    strategy:
      matrix:
        name: [a, b]
  sonos-demo:
    needs: secrets
  ci-ok:
    name: ci ok
    needs: [secrets, python-tests, sonos-demo]
    if: always()
    runs-on: ubuntu-latest
"""


def workflow(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "ci.yml"
    path.write_text(text, encoding="utf-8")
    return path


def run(path: Path, capsys, job: str = "ci-ok") -> tuple[int, str]:
    code = aggregate.main([str(path), "--job", job])
    return code, capsys.readouterr().out


def test_complete_needs_pass(tmp_path, capsys):
    code, out = run(workflow(tmp_path, COMPLETE), capsys)
    assert code == 0
    assert "ci-ok needs all 3 other jobs" in out


def test_missing_job_fails_and_is_named(tmp_path, capsys):
    text = COMPLETE.replace(
        "needs: [secrets, python-tests, sonos-demo]", "needs: [secrets, python-tests]"
    )
    code, out = run(workflow(tmp_path, text), capsys)
    assert code == 1
    assert "::error" in out
    assert "sonos-demo" in out


def test_unknown_need_fails(tmp_path, capsys):
    text = COMPLETE.replace(
        "needs: [secrets, python-tests, sonos-demo]",
        "needs: [secrets, python-tests, sonos-demo, deploy]",
    )
    code, out = run(workflow(tmp_path, text), capsys)
    assert code == 1
    assert "deploy" in out


def test_needs_as_single_string(tmp_path, capsys):
    text = (
        "jobs:\n  secrets:\n    runs-on: ubuntu-latest\n"
        "  ci-ok:\n    needs: secrets\n    if: always()\n"
    )
    code, out = run(workflow(tmp_path, text), capsys)
    assert code == 0
    assert "ci-ok needs all 1 other jobs" in out


def test_missing_always_fails(tmp_path, capsys):
    code, out = run(
        workflow(tmp_path, COMPLETE.replace("    if: always()\n", "")), capsys
    )
    assert code == 1
    assert "always()" in out


def test_other_if_condition_fails(tmp_path, capsys):
    code, out = run(
        workflow(tmp_path, COMPLETE.replace("if: always()", "if: success()")), capsys
    )
    assert code == 1
    assert "always()" in out


def test_missing_aggregate_job_fails(tmp_path, capsys):
    code, out = run(workflow(tmp_path, COMPLETE), capsys, job="all-green")
    assert code == 1
    assert "all-green" in out


def test_missing_needs_fails(tmp_path, capsys):
    text = COMPLETE.replace("    needs: [secrets, python-tests, sonos-demo]\n", "")
    code, out = run(workflow(tmp_path, text), capsys)
    assert code == 1
    assert "secrets" in out


def test_missing_file_fails(tmp_path, capsys):
    code, out = run(tmp_path / "missing.yml", capsys)
    assert code == 1
    assert "::error" in out


def test_no_jobs_mapping_fails(tmp_path, capsys):
    code, out = run(workflow(tmp_path, "name: CI\n"), capsys)
    assert code == 1
    assert "::error" in out


def test_repository_workflow_passes(capsys):
    code, out = run(REPO_ROOT / ".github" / "workflows" / "ci.yml", capsys)
    assert code == 0, out
