"""Release readiness baseline and SemVer validation for the showcase repository."""

from __future__ import annotations

import argparse
import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

REQUIRED_DOCS: tuple[str, ...] = (
    "README.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "docs/verification.md",
    "docs/enterprise-rollout.md",
    "docs/release-checklist.md",
    ".github/workflows/ci.yml",
)

SEMVER_RE = re.compile(
    r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$"
)
SECTION_RE = re.compile(r"^## \[([^\]]+)\](?:\s+-\s+(\d{4}-\d{2}-\d{2}))?\s*$")
USER_PATH_RE = re.compile(r"C:[\\/]Users[\\/]([^\\/\s\"'`]+)", re.IGNORECASE)
CONFLICT_RE = re.compile(r"^(?:<{7}|={7}|>{7})(?:\s|$)")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
BULLET_RE = re.compile(r"^\s*-\s+\S+")

SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv"})
GLOBAL_USER_ALLOWLIST = frozenset(
    token.casefold()
    for token in ("<user>", "x", "example", "username", "you", "runneradmin")
)
TEST_USER_ALLOWLIST = frozenset(
    token.casefold() for token in ("geheim", "geheim-pfad-4711")
)


def _is_test_path(rel_posix: str) -> bool:
    lowered = rel_posix.casefold()
    return "/tests/" in lowered or lowered.startswith("tests/")


def _check_required_docs(repo_root: Path) -> list[str]:
    missing: list[str] = []
    for rel in REQUIRED_DOCS:
        if not (repo_root / rel).is_file():
            missing.append(f"Missing required file: {rel}")
    return missing


def _check_changelog(changelog_path: Path, version: str | None) -> list[str]:
    if not changelog_path.is_file():
        return []
    text = changelog_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    if not any(line.strip() == "## [Unreleased]" for line in lines):
        return ["CHANGELOG.md must contain an '## [Unreleased]' heading."]

    if version is None:
        return []

    if not SEMVER_RE.match(version):
        return [
            f"Invalid SemVer version '{version}'. Expected strict 'vX.Y.Z' (e.g. v0.1.0)."
        ]

    start_idx: int | None = None
    section_date: str | None = None
    for idx, line in enumerate(lines):
        match = SECTION_RE.match(line)
        if match and match.group(1) == version:
            start_idx = idx + 1
            section_date = match.group(2)
            break

    if start_idx is None:
        return [
            f"CHANGELOG.md does not contain a release heading '## [{version}] - YYYY-MM-DD'."
        ]

    if section_date is None:
        return [
            f"CHANGELOG.md heading for '{version}' is missing a valid '- YYYY-MM-DD' date."
        ]

    try:
        datetime.date.fromisoformat(section_date)
    except ValueError:
        return [
            f"CHANGELOG.md heading date '{section_date}' for '{version}' is not a valid ISO date."
        ]

    section_lines: list[str] = []
    for line in lines[start_idx:]:
        if SECTION_RE.match(line):
            break
        section_lines.append(line)

    cleaned = HTML_COMMENT_RE.sub("", "\n".join(section_lines))
    has_bullet = any(BULLET_RE.match(line) for line in cleaned.splitlines())
    if not has_bullet:
        return [
            f"CHANGELOG.md section for '{version}' must contain at least one '- ...' changelog entry."
        ]
    return []


def _collect_tracked_files(repo_root: Path) -> tuple[list[Path], list[str]]:
    if (repo_root / ".git").exists():
        try:
            proc = subprocess.run(
                ["git", "ls-files", "-z"],
                cwd=repo_root,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            return [], [f"Failed to execute 'git ls-files -z': {exc}"]
        if proc.returncode != 0:
            detail = proc.stderr.decode("utf-8", errors="replace").strip()
            suffix = f": {detail}" if detail else ""
            return [], [f"'git ls-files -z' failed with exit {proc.returncode}{suffix}"]
        files: list[Path] = []
        for raw_rel in proc.stdout.split(b"\x00"):
            if not raw_rel:
                continue
            rel = raw_rel.decode("utf-8", errors="replace")
            candidate = repo_root / rel
            if candidate.is_file():
                files.append(candidate)
        return files, []

    walked: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS)
        for filename in sorted(filenames):
            walked.append(Path(dirpath) / filename)
    return walked, []


def _scan_hygiene(repo_root: Path) -> list[str]:
    files, errors = _collect_tracked_files(repo_root)
    if errors:
        return errors

    findings: list[str] = []
    for file_path in files:
        try:
            raw = file_path.read_bytes()
        except OSError as exc:
            findings.append(f"Unreadable file {file_path}: {exc}")
            continue
        if b"\x00" in raw:
            continue

        rel_posix = file_path.relative_to(repo_root).as_posix()
        is_test = _is_test_path(rel_posix)
        text = raw.decode("utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if CONFLICT_RE.match(line):
                findings.append(f"Git conflict marker in {rel_posix}:{line_no}")
            for match in USER_PATH_RE.finditer(line):
                token = match.group(1).casefold()
                if token in GLOBAL_USER_ALLOWLIST:
                    continue
                if is_test and token in TEST_USER_ALLOWLIST:
                    continue
                findings.append(
                    f"Disallowed Windows user path in {rel_posix}:{line_no} ({match.group(1)})"
                )
    return findings


def main(argv: list[str] | None = None) -> int:
    """Validate showcase release readiness baseline and optional SemVer target."""
    parser = argparse.ArgumentParser(
        description="Verify release readiness baseline for the portfolio repository."
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Path to the repository root (default: current directory).",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="Optional SemVer tag (vX.Y.Z) to verify against CHANGELOG.md.",
    )
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    errors = [
        *_check_required_docs(repo_root),
        *_check_changelog(repo_root / "CHANGELOG.md", args.version),
        *_scan_hygiene(repo_root),
    ]
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(
        "Baseline checks passed: required docs, CHANGELOG.md, conflict markers (0), private user paths (0)."
    )
    if args.version is not None:
        print(f"Release version check passed: {args.version}.")
    print(
        "Remaining external/manual release gates (must stay verified outside this script):"
    )
    print("  - green CI on exact commit")
    print("  - cross-model review FREI")
    print("  - explicit owner approval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
