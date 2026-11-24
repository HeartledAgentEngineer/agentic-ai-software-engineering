"""Coverage floor for one pytest suite: fails the job when line coverage drops below the recorded floor.

Usage (after pytest has written a Cobertura report with ``--cov-report=xml:...``):

    python ci_coverage_floor.py --suite concertify --floor 19 --coverage coverage.xml

The share is computed by ``ci_test_report.read_coverage``, the same function and the same test-code rule as the
job summary, so the number the gate checks is the number the summary shows. pytest-cov's ``--cov-fail-under``
would count the test files as well and give a different number.

Always prints one line with value and floor. Exit 1 with a GitHub ``::error`` annotation when the value is below
the floor, when the report is missing or unreadable, or when it holds no measured lines. An invalid floor (not a
number from 0 to 100, for example an empty matrix value) stops with argparse's exit code 2.
"""

from __future__ import annotations

import argparse
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci_test_report import read_coverage  # noqa: E402


def parse_floor(text: str) -> float:
    try:
        floor = float(text)
    except ValueError:
        floor = math.nan
    if not 0 <= floor <= 100:
        raise argparse.ArgumentTypeError(
            f"must be a number from 0 to 100, got {text!r}"
        )
    return floor


def check(suite: str, floor: float, coverage: Path) -> int:
    # No Path.exists() first: it raises PermissionError itself when a parent folder is not accessible.
    try:
        _, (lines, covered) = read_coverage(coverage)
    except FileNotFoundError:
        print(
            f"::error title=Coverage floor::No coverage report for {suite} at {coverage}."
        )
        return 1
    except (ET.ParseError, OSError) as error:
        print(
            f"::error title=Coverage floor::Coverage report for {suite} could not be read: {coverage} ({error})."
        )
        return 1
    if not lines:
        print(
            f"::error title=Coverage floor::The coverage report for {suite} has no lines outside test code."
        )
        return 1
    value = 100 * covered / lines
    print(
        f"Coverage {suite}: {value:.2f} % ({covered} of {lines} lines, test code excluded), floor {floor:g} %"
    )
    if value < floor:
        print(
            f"::error title=Coverage floor::Coverage {suite} is {value:.2f} %, below its floor of {floor:g} % "
            "(set per suite in .github/workflows/ci.yml)."
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail when line coverage of a pytest suite is below its floor."
    )
    parser.add_argument("--suite", required=True)
    parser.add_argument(
        "--floor",
        required=True,
        type=parse_floor,
        help="lowest allowed line coverage in percent",
    )
    parser.add_argument(
        "--coverage", required=True, type=Path, help="Cobertura report from pytest-cov"
    )
    args = parser.parse_args(argv)
    return check(args.suite, args.floor, args.coverage)


if __name__ == "__main__":
    sys.exit(main())
