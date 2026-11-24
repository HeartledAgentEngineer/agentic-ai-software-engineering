"""Verify that Dependabot watches every directory that holds a pip or npm dependency manifest.

Usage (from the repository root):

    python .github/scripts/ci_dependabot_coverage.py

Dependabot only opens update pull requests for the directories listed in ``.github/dependabot.yml``. A new
project with its own ``requirements.txt`` or ``package.json`` is silently left out until someone adds it. This
script walks the repository, collects every directory with a manifest, and compares that with the configuration.
It fails with exit code 1 and a GitHub ``::error`` annotation when a manifest directory is not listed, or when the
configuration lists a directory that holds no manifest (a moved or deleted project). Other ecosystems, such as
``github-actions``, are not checked.

Dependabot pip also reads requirement files (``requirements*.txt``, ``requirements*.in``) one folder below a listed
directory, but no other pip manifest there (dependabot-core, ``python/lib/dependabot/python/shared_file_fetcher.rb``,
``req_files_for_dir``). A folder that holds only requirement files is therefore covered by its listed parent, and
listing both is an error, because Dependabot then opens every update twice. A folder with another pip manifest, such
as ``pyproject.toml``, must be listed itself; if it also holds a requirement file below a listed parent, Dependabot
may update that file twice, which the configuration cannot avoid.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
from pathlib import Path

import yaml

# Requirement files: the only pip manifests Dependabot also reads one folder below a listed directory.
REQUIREMENT_FILES = ("requirements*.txt", "requirements*.in")

# File names Dependabot reads for each ecosystem. npm needs a package.json; a lockfile alone is not a project.
MANIFESTS: dict[str, tuple[str, ...]] = {
    "pip": (
        *REQUIREMENT_FILES,
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "Pipfile",
        "Pipfile.lock",
    ),
    "npm": ("package.json",),
}

# Installed or generated trees, never maintained by hand.
SKIPPED_DIRECTORIES = {"node_modules", ".git", ".venv", "venv", "__pycache__"}


def normalise(directory: object) -> str:
    """``/tools/readfree/`` and ``tools/readfree`` both become ``/tools/readfree``; the root stays ``/``."""
    text = str(directory).strip().strip("/")
    return "/" + text if text else "/"


def parent(directory: str) -> str | None:
    """``/tools/foundry-demos/shared_core`` becomes ``/tools/foundry-demos``, ``/tools`` becomes ``/``; ``/`` has none."""
    if directory == "/":
        return None
    return normalise(directory.rsplit("/", 1)[0])


def matches(files: list[str], patterns: tuple[str, ...]) -> bool:
    """True when one of the file names fits one of the patterns. Names compare case-sensitively, as on Linux."""
    return any(
        fnmatch.fnmatchcase(name, pattern) for name in files for pattern in patterns
    )


def watched(config: object) -> tuple[dict[str, set[str]], list[str]]:
    """Directories per checked ecosystem from ``directory`` and ``directories``, plus configuration errors."""
    result: dict[str, set[str]] = {ecosystem: set() for ecosystem in MANIFESTS}
    updates = config.get("updates") if isinstance(config, dict) else None
    if not isinstance(updates, list) or not updates:
        return result, ["the configuration has no updates list"]
    for entry in updates:
        if not isinstance(entry, dict):
            continue
        ecosystem = entry.get("package-ecosystem")
        if ecosystem not in result:
            continue
        listed = entry.get("directories") or []
        if "directory" in entry:
            listed = [entry["directory"], *listed]
        result[ecosystem].update(normalise(directory) for directory in listed)
    return result, []


def scan(root: Path) -> tuple[dict[str, set[str]], set[str]]:
    """Directories per ecosystem that hold at least one manifest, and the pip directories whose only pip manifests
    are requirement files."""
    result: dict[str, set[str]] = {ecosystem: set() for ecosystem in MANIFESTS}
    requirements_only: set[str] = set()
    other_pip = tuple(
        pattern for pattern in MANIFESTS["pip"] if pattern not in REQUIREMENT_FILES
    )
    for current, directories, files in os.walk(root):
        directories[:] = [
            name for name in directories if name not in SKIPPED_DIRECTORIES
        ]
        relative = Path(current).relative_to(root).as_posix()
        directory = normalise("" if relative == "." else relative)
        for ecosystem, patterns in MANIFESTS.items():
            if matches(files, patterns):
                result[ecosystem].add(directory)
        if matches(files, REQUIREMENT_FILES) and not matches(files, other_pip):
            requirements_only.add(directory)
    return result, requirements_only


def found(root: Path) -> dict[str, set[str]]:
    """Directories per ecosystem that hold at least one manifest."""
    return scan(root)[0]


def problems(config: object, root: Path) -> list[str]:
    """Error messages for manifests Dependabot does not watch, for listed directories without a manifest, and for
    requirement folders listed next to their listed parent."""
    listed, errors = watched(config)
    if errors:
        return errors
    present, requirements_only = scan(root)
    below_listed_parent = {
        directory
        for directory in requirements_only
        if parent(directory) in listed["pip"]
    }
    for ecosystem in MANIFESTS:
        covered = listed[ecosystem] | (
            below_listed_parent if ecosystem == "pip" else set()
        )
        errors += [
            f"{ecosystem}: {directory} has a manifest but is not in dependabot.yml"
            for directory in sorted(present[ecosystem] - covered)
        ]
        errors += [
            f"{ecosystem}: {directory} is listed in dependabot.yml but holds no manifest"
            for directory in sorted(listed[ecosystem] - present[ecosystem])
        ]
    errors += [
        f"pip: {directory} is already covered by {parent(directory)} (Dependabot pip reads requirement files one "
        "folder down); listing both opens duplicate pull requests"
        for directory in sorted(below_listed_parent & listed["pip"])
    ]
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check that Dependabot watches every pip and npm manifest directory."
    )
    parser.add_argument("--config", type=Path, default=Path(".github/dependabot.yml"))
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)

    try:
        config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        print(
            f"::error file={args.config.as_posix()}::cannot read Dependabot config: {error}"
        )
        return 1

    errors = problems(config, args.root)
    for message in errors:
        print(f"::error file={args.config.as_posix()}::{message}")
    if errors:
        return 1
    counts = {
        ecosystem: len(directories)
        for ecosystem, directories in found(args.root).items()
    }
    print(
        f"Dependabot watches all {sum(counts.values())} manifest directories "
        f"(pip: {counts['pip']}, npm: {counts['npm']})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
