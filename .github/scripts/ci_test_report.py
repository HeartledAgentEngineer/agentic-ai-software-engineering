"""Test report for the GitHub job summary: which tests ran, which did not pass, how much code they cover.

Usage (in the project's working directory, after pytest):

    python ci_test_report.py --title concertify --junit junit.xml [--coverage coverage.xml]

- ``--junit``: JUnit report from pytest (``--junitxml``, best with ``-o junit_family=xunit1`` so every test
  carries its file).
- ``--coverage``: Cobertura report from pytest-cov (``--cov-report=xml:...``). Optional.

Appends Markdown to ``$GITHUB_STEP_SUMMARY`` or, without that variable (or if it cannot be written), writes it
to standard output.
The exit code is always 0: whether the tests are green is decided by the pytest step, not by the report.
If the JUnit report is missing (pytest did not finish) or a report cannot be read (broken XML, no access),
the report says so and gives the reason.
"""

from __future__ import annotations

import argparse
import html
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ICON = {"passed": "✅", "skipped": "⏭️", "failed": "❌", "error": "💥"}
# Characters Markdown uses for formatting or links; as HTML entities they stay literal.
_MARKDOWN = str.maketrans({char: f"&#{ord(char)};" for char in "\\`*_[]|~"})


def literal(text: str) -> str:
    """Print test names, files and messages so that they turn into neither HTML nor Markdown."""
    return html.escape(text, quote=False).translate(_MARKDOWN)


def as_sentence(name: str) -> str:
    """``test_add_song_persists_score[x]`` -> ``add song persists score [x]``."""
    base, bracket, rest = name.partition("[")
    if base.startswith("test_"):
        base = base[len("test_"):]
    sentence = base.replace("_", " ").strip()
    return f"{sentence} [{rest}" if bracket else sentence


def suite_time(path: Path) -> float:
    """Run time from <testsuite time=…> (includes collection and fixtures, unlike the sum of the test cases)."""
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    return sum(float(s.get("time") or 0) for s in suites)


def read_junit(path: Path) -> list[dict]:
    root = ET.parse(path).getroot()
    cases = []
    for case in root.iter("testcase"):
        status, message = "passed", ""
        for tag, name in (("failure", "failed"), ("error", "error"), ("skipped", "skipped")):
            node = case.find(tag)
            if node is not None:
                status, message = name, (node.get("message") or "").strip()
                break
        file = (case.get("file") or case.get("classname", "").replace(".", "/") + ".py").replace("\\", "/")
        cases.append({"file": file, "name": case.get("name", ""), "status": status, "message": message,
                      "time": float(case.get("time") or 0)})
    return cases


def is_test_code(filename: str) -> bool:
    parts = filename.replace("\\", "/").split("/")
    return "tests" in parts[:-1] or parts[-1].startswith("test_") or parts[-1] == "conftest.py"


def read_coverage(path: Path) -> tuple[dict[str, list[int]], list[int]]:
    """Lines per module (first folder, or file at the top level): {module: [lines, covered]}."""
    modules: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    total = [0, 0]
    for klass in ET.parse(path).getroot().iter("class"):
        filename = klass.get("filename", "").replace("\\", "/")
        if not filename or is_test_code(filename):
            continue
        module = filename.split("/")[0] if "/" in filename else filename
        for line in klass.iter("line"):
            covered = int(line.get("hits", "0")) > 0
            for target in (modules[module], total):
                target[0] += 1
                target[1] += covered
    return dict(modules), total


def share(lines: int, covered: int) -> str:
    return f"{100 * covered / lines:.0f} %" if lines else "–"


def unreadable(what: str, path: Path, error: Exception) -> str:
    return f"{what} could not be read: <code>{literal(str(path))}</code> ({literal(str(error))})."


def coverage_section(coverage: Path) -> list[str]:
    # No Path.exists() first: it raises PermissionError itself when a parent folder is not accessible.
    try:
        modules, total = read_coverage(coverage)
    except FileNotFoundError:
        return [f"No coverage report at <code>{literal(str(coverage))}</code>.", ""]
    except (ET.ParseError, OSError) as error:
        return [unreadable("Coverage report", coverage, error), ""]
    lines = [f"### Coverage: {share(*total)} of lines ({total[1]} of {total[0]}, test code excluded)", "",
             "| Module | Lines | Covered | Share |", "|---|---:|---:|---:|"]
    for module in sorted(modules):
        count, covered = modules[module]
        lines.append(f"| <code>{literal(module)}</code> | {count} | {covered} | {share(count, covered)} |")
    return lines + [""]


def build_report(title: str, junit: Path, coverage: Path | None) -> str:
    lines = [f"## {title}: test report", ""]
    try:
        cases = read_junit(junit)
        duration = suite_time(junit) or sum(c["time"] for c in cases)
    except FileNotFoundError:
        return "\n".join(lines + [f"No JUnit report at <code>{literal(str(junit))}</code>: "
                                  "pytest did not run to the end.", ""])
    except (ET.ParseError, OSError) as error:
        return "\n".join(lines + [unreadable("JUnit report", junit, error), ""])
    counts: dict[str, int] = defaultdict(int)
    for case in cases:
        counts[case["status"]] += 1
    lines.append(f"**{len(cases)} tests:** {counts['passed']} passed · {counts['skipped']} skipped · "
                 f"{counts['failed']} failed · {counts['error']} errors · {duration:.1f} s")
    lines.append("")

    for status, heading in (("failed", "Failed"), ("error", "Errors while running"), ("skipped", "Skipped")):
        selection = [c for c in cases if c["status"] == status]
        if not selection:
            continue
        lines.append(f"### {heading} ({len(selection)})")
        for case in selection:
            reason = f": {literal(case['message'].splitlines()[0][:200])}" if case["message"] else ""
            lines.append(f"- <code>{literal(case['file'])}</code> · {literal(as_sentence(case['name']))}{reason}")
        lines.append("")

    per_file: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        per_file[case["file"]].append(case)
    lines.append(f"<details><summary>All {len(cases)} tests by file ({len(per_file)} files)</summary>")
    lines.append("")
    for file in sorted(per_file):
        lines.append(f"**{literal(file)}**")
        lines.append("")
        for case in per_file[file]:
            lines.append(f"- {ICON[case['status']]} {literal(as_sentence(case['name']))}")
        lines.append("")
    lines.append("</details>")
    lines.append("")

    if coverage is not None:
        lines += coverage_section(coverage)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test report for the GitHub job summary")
    parser.add_argument("--title", required=True)
    parser.add_argument("--junit", required=True, type=Path)
    parser.add_argument("--coverage", type=Path)
    args = parser.parse_args(argv)

    report = build_report(args.title, args.junit, args.coverage)
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        try:
            with open(target, "a", encoding="utf-8") as file:
                file.write(report + "\n")
            return 0
        except OSError as error:
            # The report must never fail the job: fall back to the log, with a warning on the run page.
            report = f"::warning::Job summary could not be written ({error}); the report follows in the log.\n{report}"
    sys.stdout.buffer.write((report + "\n").encode("utf-8"))  # Windows console: not cp1252
    return 0


if __name__ == "__main__":
    sys.exit(main())
