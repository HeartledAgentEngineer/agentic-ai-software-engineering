"""Verify that every workflow `uses:` reference is pinned to an immutable commit SHA or digest.

Usage (from the repository root):

    python .github/scripts/ci_pinned_actions.py .github/workflows

Parses every ``*.yml`` and ``*.yaml`` file under the given paths with PyYAML (``yaml.compose_all`` / ``SafeLoader``)
and rejects invalid YAML, flow-mapping ``uses:``, empty/aliased/multiline ``uses:`` entries, missing commit SHAs or
digests, and missing ``# v...`` release comments with exit code 1.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from pathlib import Path

import yaml

SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST64_RE = re.compile(r"^docker://[^@\s]+@sha256:[0-9a-f]{64}$")
VERSION_COMMENT_RE = re.compile(r"#\s*v\S+")


def _iter_uses_entries(
    root: yaml.Node,
) -> Iterator[tuple[yaml.MappingNode, yaml.ScalarNode, yaml.Node]]:
    """Iteratively yield ``(mapping, key_node, val_node)`` for all ``uses`` keys without risking recursion limits."""
    stack: list[yaml.Node] = [root]
    seen_containers: set[int] = set()
    while stack:
        node = stack.pop()
        if isinstance(node, yaml.MappingNode):
            node_id = id(node)
            if node_id in seen_containers:
                continue
            seen_containers.add(node_id)
            for key_node, val_node in node.value:
                if (
                    isinstance(key_node, yaml.ScalarNode)
                    and key_node.tag == "tag:yaml.org,2002:str"
                    and key_node.value == "uses"
                ):
                    yield node, key_node, val_node
            for key_node, val_node in reversed(node.value):
                if isinstance(val_node, (yaml.MappingNode, yaml.SequenceNode)):
                    stack.append(val_node)
                if isinstance(key_node, (yaml.MappingNode, yaml.SequenceNode)):
                    stack.append(key_node)
        elif isinstance(node, yaml.SequenceNode):
            node_id = id(node)
            if node_id in seen_containers:
                continue
            seen_containers.add(node_id)
            for item in reversed(node.value):
                if isinstance(item, (yaml.MappingNode, yaml.SequenceNode)):
                    stack.append(item)


def _validate_target(target: str, trailing: str) -> str | None:
    """Return an error reason if ``target``/``trailing`` violates pinning policy, else ``None``."""
    if target.startswith("./"):
        return None
    if target.startswith("docker://"):
        if DIGEST64_RE.fullmatch(target):
            return None
        return f"docker action must pin a 64-char sha256 digest ({target})"
    if "@" not in target:
        return f"missing @<commit-sha> in {target}"
    action, ref = target.split("@", 1)
    if not action or not SHA40_RE.fullmatch(ref):
        return f"must pin a 40-char lowercase commit SHA instead of '{ref}' ({target})"
    if not VERSION_COMMENT_RE.search(trailing):
        return f"missing version comment '# v...' after pinned SHA ({target})"
    return None


def _validate_uses_entry(
    file_ref: str,
    lines: list[str],
    mapping: yaml.MappingNode,
    key_node: yaml.ScalarNode,
    val_node: yaml.Node,
) -> str | None:
    """Return an Actions ``::error`` line for a non-compliant ``uses`` AST entry, or ``None`` if valid."""
    lineno = max(key_node.start_mark.line, val_node.start_mark.line) + 1
    if mapping.flow_style:
        return f"::error file={file_ref},line={lineno}::flow-mapping uses: is not supported; use block mapping"

    if (
        not isinstance(val_node, yaml.ScalarNode)
        or val_node.tag != "tag:yaml.org,2002:str"
        or val_node.style in ("|", ">")
        or key_node.start_mark.line != val_node.start_mark.line
        or key_node.end_mark.line != key_node.start_mark.line
        or val_node.end_mark.line != val_node.start_mark.line
        or val_node.start_mark.column <= key_node.end_mark.column
    ):
        return f"::error file={file_ref},line={lineno}::empty, aliased, or multiline uses: is not supported"

    target = val_node.value
    if not target or any(ch.isspace() for ch in target):
        return f"::error file={file_ref},line={lineno}::invalid whitespace or empty uses: target ({target})"

    line_idx = val_node.start_mark.line
    raw_after = (
        lines[line_idx][val_node.end_mark.column :] if line_idx < len(lines) else ""
    )
    trailing = raw_after.strip()
    if trailing and not trailing.startswith("#"):
        return f"::error file={file_ref},line={lineno}::unexpected trailing content after uses: target"

    reason = _validate_target(target, trailing)
    if reason is not None:
        return f"::error file={file_ref},line={lineno}::{reason}"
    return None


def _collect_yaml_files(paths: list[Path]) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    errors: list[str] = []
    for path in paths:
        if not path.exists():
            errors.append(f"::error::path not found: {path.as_posix()}")
            continue
        if path.is_file():
            files.append(path)
        else:
            found = sorted(
                {
                    p
                    for pattern in ("*.yml", "*.yaml")
                    for p in path.rglob(pattern)
                    if p.is_file()
                },
                key=lambda p: p.as_posix(),
            )
            files.extend(found)
    return files, errors


def check_paths(paths: list[Path]) -> tuple[int, list[str]]:
    """Scan ``paths`` and return ``(uses_count, error_lines)``."""
    files, errors = _collect_yaml_files(paths)
    if errors:
        return 0, errors

    uses_count = 0
    for file in files:
        file_ref = file.as_posix()
        try:
            text = file.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"::error file={file_ref}::could not read file ({exc})")
            continue
        lines = text.splitlines()
        try:
            docs = list(yaml.compose_all(text, Loader=yaml.SafeLoader))
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            line_part = f",line={mark.line + 1}" if mark is not None else ""
            errors.append(f"::error file={file_ref}{line_part}::invalid YAML ({exc})")
            continue
        for doc in docs:
            if doc is None:
                continue
            for mapping, key_node, val_node in _iter_uses_entries(doc):
                uses_count += 1
                err = _validate_uses_entry(file_ref, lines, mapping, key_node, val_node)
                if err is not None:
                    errors.append(err)

    if uses_count == 0 and not errors:
        errors.append("::error::no uses: lines found")
    return uses_count, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ensure workflow uses: lines are pinned to full commit SHAs."
    )
    parser.add_argument("paths", nargs="*", default=[".github/workflows"], type=Path)
    args = parser.parse_args(argv)

    uses_count, errors = check_paths(args.paths)
    if errors:
        for line in errors:
            print(line)
        return 1
    print(f"{uses_count} uses: lines pinned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
