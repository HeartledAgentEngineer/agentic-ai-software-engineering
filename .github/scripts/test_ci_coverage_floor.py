"""Tests for ci_coverage_floor.py. Run from the repository root: python -m pytest -q .github/scripts"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ci_coverage_floor as coverage_floor  # noqa: E402

# app.py: 3 of 4 lines covered = 75 %. The test file is fully covered but must not count.
COVERAGE = """<?xml version="1.0" ?>
<coverage><packages><package name="."><classes>
  <class filename="app.py"><lines>
    <line number="1" hits="1"/><line number="2" hits="2"/><line number="3" hits="1"/><line number="4" hits="0"/>
  </lines></class>
  <class filename="tests/test_app.py"><lines>
    <line number="1" hits="1"/><line number="2" hits="1"/><line number="3" hits="1"/><line number="4" hits="1"/>
  </lines></class>
</classes></package></packages></coverage>
"""

ONLY_TEST_CODE = """<?xml version="1.0" ?>
<coverage><packages><package name="."><classes>
  <class filename="tests/test_app.py"><lines><line number="1" hits="1"/></lines></class>
  <class filename="conftest.py"><lines><line number="1" hits="1"/></lines></class>
</classes></package></packages></coverage>
"""


def _report(tmp_path, content=COVERAGE):
    path = tmp_path / "coverage.xml"
    path.write_text(content, encoding="utf-8")
    return path


def _run(path, floor):
    return coverage_floor.main(
        ["--suite", "demo", "--floor", str(floor), "--coverage", str(path)]
    )


def test_above_the_floor_passes_and_prints_value_and_floor(tmp_path, capsys):
    assert _run(_report(tmp_path), 70) == 0
    out = capsys.readouterr().out
    assert (
        "Coverage demo: 75.00 % (3 of 4 lines, test code excluded), floor 70 %" in out
    )
    assert "::error" not in out


def test_exactly_on_the_floor_passes(tmp_path, capsys):
    assert _run(_report(tmp_path), 75) == 0
    assert "::error" not in capsys.readouterr().out


def test_below_the_floor_fails_with_an_annotation(tmp_path, capsys):
    assert _run(_report(tmp_path), 75.5) == 1
    out = capsys.readouterr().out
    assert (
        "Coverage demo: 75.00 % (3 of 4 lines, test code excluded), floor 75.5 %" in out
    )
    assert "::error" in out
    assert "below" in out


def test_test_code_does_not_lift_the_value(tmp_path, capsys):
    # With the fully covered test file counted, the share would be 7 of 8 = 87.5 % and pass.
    assert _run(_report(tmp_path), 80) == 1
    assert "75.00 %" in capsys.readouterr().out


def test_missing_report_fails(tmp_path, capsys):
    assert _run(tmp_path / "missing.xml", 0) == 1
    out = capsys.readouterr().out
    assert "::error" in out
    assert "missing.xml" in out


def test_unreadable_report_fails(tmp_path, capsys):
    assert _run(_report(tmp_path, "<coverage><broken"), 0) == 1
    assert "::error" in capsys.readouterr().out


def test_report_without_measured_lines_fails(tmp_path, capsys):
    assert _run(_report(tmp_path, ONLY_TEST_CODE), 0) == 1
    out = capsys.readouterr().out
    assert "::error" in out
    assert "no lines" in out


@pytest.mark.parametrize("floor", ["", "abc", "-1", "100.1", "nan"])
def test_floor_must_be_a_number_from_0_to_100(tmp_path, floor):
    with pytest.raises(SystemExit) as stop:
        _run(_report(tmp_path), floor)
    assert stop.value.code == 2


@pytest.mark.parametrize("floor", ["0", "100", "42.5"])
def test_floor_accepts_the_edges_and_decimals(floor):
    assert coverage_floor.parse_floor(floor) == float(floor)
