"""Tests for ci_test_report.py. Run from the repository root: python -m pytest -q .github/scripts"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ci_test_report as test_report  # noqa: E402

JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="4" time="3.5">
  <testcase classname="tests.test_a" name="test_saves_the_song" file="tests\\test_a.py" time="0.1"/>
  <testcase classname="tests.test_a" name="test_adds[case-1]" file="tests\\test_a.py" time="0.1">
    <failure message="assert 1 == 2&#10;second line">Traceback</failure>
  </testcase>
  <testcase classname="tests.sub.test_b" name="test_needs_data" time="0.0">
    <skipped type="pytest.skip" message="concert_data.json missing"/>
  </testcase>
  <testcase classname="tests.sub.test_b" name="test_broken" time="0.0"><error message="fixture missing"/></testcase>
</testsuite></testsuites>
"""

COVERAGE = """<?xml version="1.0" ?>
<coverage><packages><package name="."><classes>
  <class filename="app.py"><lines><line number="1" hits="1"/><line number="2" hits="0"/></lines></class>
  <class filename="services/x.py"><lines><line number="1" hits="3"/></lines></class>
  <class filename="tests/test_a.py"><lines><line number="1" hits="1"/></lines></class>
  <class filename="test_manual.py"><lines><line number="1" hits="0"/></lines></class>
</classes></package></packages></coverage>
"""


def _write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_test_name_reads_as_a_sentence():
    assert test_report.as_sentence("test_saves_the_song") == "saves the song"
    assert test_report.as_sentence("test_adds[case-1]") == "adds [case-1]"


def test_report_counts_every_status_and_lists_failures_with_message(tmp_path):
    report = test_report.build_report("Demo", _write(tmp_path, "j.xml", JUNIT), None)

    assert "**4 tests:** 1 passed · 1 skipped · 1 failed · 1 errors · 3.5 s" in report
    lit = test_report.literal
    assert (
        f"- <code>{lit('tests/test_a.py')}</code> · {lit('adds [case-1]')}: assert 1 == 2"
        in report
    )
    assert "second line" not in report
    assert (
        f"- <code>{lit('tests/sub/test_b.py')}</code> · needs data: {lit('concert_data.json')} missing"
        in report
    )
    assert (
        f"- <code>{lit('tests/sub/test_b.py')}</code> · broken: fixture missing"
        in report
    )
    assert "All 4 tests by file (2 files)" in report


def test_coverage_excludes_test_code(tmp_path):
    report = test_report.build_report(
        "Demo", _write(tmp_path, "j.xml", JUNIT), _write(tmp_path, "c.xml", COVERAGE)
    )

    assert "### Coverage: 67 % of lines (2 of 3, test code excluded)" in report
    assert "| <code>app.py</code> | 2 | 1 | 50 % |" in report
    assert "| <code>services</code> | 1 | 1 | 100 % |" in report
    assert "tests" not in report.split("### Coverage")[1]


def test_messages_and_names_stay_literal_not_html_or_markdown(tmp_path):
    junit = """<testsuites><testsuite time="1">
      <testcase name="test_link_[a](b)" file="tests/x|y.py"><skipped message="&lt;h1&gt;Success&lt;/h1&gt; *bold*"/></testcase>
    </testsuite></testsuites>"""
    report = test_report.build_report("Demo", _write(tmp_path, "j.xml", junit), None)

    assert "<h1>" not in report
    assert "&lt;h1&gt;Success&lt;/h1&gt; &#42;bold&#42;" in report
    assert "link &#91;a&#93;(b)" in report
    assert "x&#124;y.py" in report


def test_missing_junit_report_is_reported_instead_of_crashing(tmp_path):
    report = test_report.build_report("Demo", tmp_path / "missing.xml", None)
    assert "pytest did not run to the end" in report


def test_main_appends_to_the_job_summary(tmp_path, monkeypatch):
    summary = _write(tmp_path, "summary.md", "before\n")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    assert (
        test_report.main(
            ["--title", "Demo", "--junit", str(_write(tmp_path, "j.xml", JUNIT))]
        )
        == 0
    )
    content = summary.read_text(encoding="utf-8")
    assert content.startswith("before\n## Demo: test report")


def test_unreadable_reports_are_reported_and_exit_stays_0(tmp_path, monkeypatch):
    summary = _write(tmp_path, "summary.md", "")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    broken = _write(tmp_path, "broken.xml", "<testsuites><testsuite")

    assert test_report.main(["--title", "Demo", "--junit", str(broken)]) == 0
    assert "JUnit report could not be read" in summary.read_text(encoding="utf-8")

    folder = (
        tmp_path / "folder.xml"
    )  # exists, but is not a file (OSError instead of ParseError)
    folder.mkdir()
    summary.write_text("", encoding="utf-8")
    assert test_report.main(["--title", "Demo", "--junit", str(folder)]) == 0
    assert "JUnit report could not be read" in summary.read_text(encoding="utf-8")

    summary.write_text("", encoding="utf-8")
    junit = _write(tmp_path, "j.xml", JUNIT)
    assert (
        test_report.main(
            ["--title", "Demo", "--junit", str(junit), "--coverage", str(broken)]
        )
        == 0
    )
    content = summary.read_text(encoding="utf-8")
    assert "**4 tests:**" in content
    assert "Coverage report could not be read" in content


def _denied(*_args, **_kwargs):
    raise PermissionError(13, "Access denied")


def test_no_access_is_reported_even_when_the_existence_check_fails(
    tmp_path, monkeypatch
):
    """Path.exists() raises PermissionError on Python 3.12 (for example a parent folder without access)."""
    summary = _write(tmp_path, "summary.md", "")
    junit = _write(tmp_path, "j.xml", JUNIT)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr(test_report.Path, "exists", _denied)
    monkeypatch.setattr(test_report.ET, "parse", _denied)

    assert (
        test_report.main(
            ["--title", "Demo", "--junit", str(junit), "--coverage", str(junit)]
        )
        == 0
    )
    assert "JUnit report could not be read" in summary.read_text(encoding="utf-8")


def test_no_access_to_the_coverage_report_is_reported(tmp_path, monkeypatch):
    """As above, for the coverage report only: the JUnit report is readable, coverage is not."""
    real_exists = test_report.Path.exists
    summary = _write(tmp_path, "summary.md", "")
    junit = _write(tmp_path, "j.xml", JUNIT)
    coverage = _write(tmp_path, "c.xml", COVERAGE)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr(
        test_report.Path,
        "exists",
        lambda path, *a, **k: _denied()
        if path.name == "c.xml"
        else real_exists(path, *a, **k),
    )
    monkeypatch.setattr(test_report, "read_coverage", _denied)

    assert (
        test_report.main(
            ["--title", "Demo", "--junit", str(junit), "--coverage", str(coverage)]
        )
        == 0
    )
    content = summary.read_text(encoding="utf-8")
    assert "**4 tests:**" in content
    assert "Coverage report could not be read" in content


def test_summary_that_cannot_be_written_falls_back_to_stdout_and_exit_stays_0(
    tmp_path, monkeypatch, capsys
):
    folder = (
        tmp_path / "summary-is-a-folder"
    )  # opening it for appending raises an OSError
    folder.mkdir()
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(folder))

    assert (
        test_report.main(
            ["--title", "Demo", "--junit", str(_write(tmp_path, "j.xml", JUNIT))]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "::warning::Job summary could not be written" in out
    assert "## Demo: test report" in out
