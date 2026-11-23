"""Verify that Dependabot watches every directory that holds a pip or npm dependency manifest.

Usage (from the repository root):

    python .github/scripts/ci_dependabot_coverage.py

Dependabot only opens update pull requests for the directories listed in ``.github/dependabot.yml``. A new
project with its own ``requirements.txt`` or ``package.json`` is silently left out until someone adds it. This
script walks the repository, collects every directory with a manifest, and compares that with the configuration.
It fails with exit code 1 and a GitHub ``::error`` annotation when a manifest directory is not listed, or when the
configuration lists a directory that holds no manifest (a moved or deleted project). Other ecosystems, such as
``github-actions``, are not checked.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
from pathlib import Path

import yaml

# File names Dependabot reads for each ecosystem. npm needs a package.json; a lockfile alone is not a project.
MANIFESTS: dict[str, tuple[str, ...]] = {
    "pip": (
        "requirements*.txt",
        "requirements*.in",
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


def found(root: Path) -> dict[str, set[str]]:
    """Directories per ecosystem that hold at least one manifest. Names compare case-sensitively, as on Linux."""
    result: dict[str, set[str]] = {ecosystem: set() for ecosystem in MANIFESTS}
    for current, directories, files in os.walk(root):
        directories[:] = [
            name for name in directories if name not in SKIPPED_DIRECTORIES
        ]
        relative = Path(current).relative_to(root).as_posix()
        for ecosystem, patterns in MANIFESTS.items():
            if any(
                fnmatch.fnmatchcase(name, pattern)
                for name in files
                for pattern in patterns
            ):
                result[ecosystem].add(normalise("" if relative == "." else relative))
    return result


def problems(config: object, root: Path) -> list[str]:
    """Error messages for manifests Dependabot does not watch and for listed directories without a manifest."""
    listed, errors = watched(config)
    if errors:
        return errors
    present = found(root)
    for ecosystem in MANIFESTS:
        errors += [
            f"{ecosystem}: {directory} has a manifest but is not in dependabot.yml"
            for directory in sorted(present[ecosystem] - listed[ecosystem])
        ]
        errors += [
            f"{ecosystem}: {directory} is listed in dependabot.yml but holds no manifest"
            for directory in sorted(listed[ecosystem] - present[ecosystem])
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
