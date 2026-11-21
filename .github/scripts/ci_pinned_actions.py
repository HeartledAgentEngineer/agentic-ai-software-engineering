"""Verify that every workflow `uses:` reference is pinned to an immutable commit SHA or digest.

Usage (from the repository root):

    python .github/scripts/ci_pinned_actions.py .github/workflows

Line-based by design (standard library only, no PyYAML dependency): inspects every ``*.yml`` and ``*.yaml`` file
under the given paths and rejects empty, multiline block-scalar (``|``, ``>``, etc.) or flow-mapping
(``{uses: ...}``) ``uses:`` entries with exit code 1 so unpinned actions cannot slip past silently.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

USES_LINE_RE = re.compile(r"""^\s*(?:-\s+)?(?:uses|['"]uses['"])\s*:(.*)$""")
FLOW_START_RE = re.compile(r"""^\s*(?:-\s*)?(?:[\[{]|(?:[A-Za-z0-9_.-]+|['"][^'"]+['"])\s*:\s*[\[{])""")
FLOW_USES_KEY_RE = re.compile(r"""(?:^|[,{\[\s])(?:uses|['"]uses['"])\s*:""")
BLOCK_SCALAR_RE = re.compile(r"^[|>](?:[+-]?\d+|\d+[+-]?|[+-])?(?:\s+#.*|\s*)$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST64_RE = re.compile(r"^docker://.+@sha256:[0-9a-f]{64}$")
VERSION_COMMENT_RE = re.compile(r"#\s*v\S+")


def _strip_yaml_comment(line: str) -> str:
    """Return ``line`` up to any unquoted YAML ``#`` comment."""
    in_quote: str | None = None
    i = 0
    while i < len(line):
        ch = line[i]
        if in_quote == "'":
            if ch == "'":
                if i + 1 < len(line) and line[i + 1] == "'":
                    i += 2
                    continue
                in_quote = None
        elif in_quote == '"':
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_quote = None
        else:
            if ch in ("'", '"'):
                in_quote = ch
            elif ch == "#" and (i == 0 or line[i - 1].isspace()):
                return line[:i]
        i += 1
    return line


def _flow_mapping_has_uses(line: str) -> bool:
    if not FLOW_START_RE.match(line):
        return False
    return bool(FLOW_USES_KEY_RE.search(_strip_yaml_comment(line)))


def _split_target_and_comment(raw_rhs: str) -> tuple[str, str] | None:
    """Return ``(target, trailing_text)`` for a single-line ``uses:`` value, or ``None`` if invalid/multiline."""
    rest = raw_rhs.strip()
    if not rest or rest.startswith("#") or BLOCK_SCALAR_RE.match(rest):
        return None
    if rest[0] in ("'", '"'):
        quote = rest[0]
        end = rest.find(quote, 1)
        if end == -1:
            return None
        target = rest[1:end].strip()
        trailing = rest[end + 1 :].strip()
        return (target, trailing) if target else None
    parts = rest.split(None, 1)
    return parts[0], (parts[1].strip() if len(parts) > 1 else "")


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
    action, ref = target.rsplit("@", 1)
    if not action or not SHA40_RE.fullmatch(ref):
        return f"must pin a 40-char lowercase commit SHA instead of '{ref}' ({target})"
    if not VERSION_COMMENT_RE.search(trailing):
        return f"missing version comment '# v...' after pinned SHA ({target})"
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
                {p for pattern in ("*.yml", "*.yaml") for p in path.rglob(pattern) if p.is_file()},
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
            lines = file.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            errors.append(f"::error file={file_ref}::could not read file ({exc})")
            continue
        for lineno, line in enumerate(lines, start=1):
            if _flow_mapping_has_uses(line):
                uses_count += 1
                errors.append(
                    f"::error file={file_ref},line={lineno}::flow-mapping uses: is not supported; use block mapping"
                )
                continue
            match = USES_LINE_RE.match(line)
            if not match:
                continue
            uses_count += 1
            parsed = _split_target_and_comment(match.group(1))
            if parsed is None:
                errors.append(f"::error file={file_ref},line={lineno}::empty or multiline uses: is not supported")
                continue
            reason = _validate_target(*parsed)
            if reason is not None:
                errors.append(f"::error file={file_ref},line={lineno}::{reason}")

    if uses_count == 0:
        errors.append("::error::no uses: lines found")
    return uses_count, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ensure workflow uses: lines are pinned to full commit SHAs.")
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
