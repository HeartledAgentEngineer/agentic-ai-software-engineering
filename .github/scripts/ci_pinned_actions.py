"""Verify that every workflow `uses:` reference is pinned to an immutable commit SHA or digest.

Usage (from the repository root):

    python .github/scripts/ci_pinned_actions.py .github/workflows

Scans every ``*.yml`` and ``*.yaml`` file under the given paths using standard library only (no PyYAML dependency)
and rejects empty, multiline block-scalar (``|``, ``>``), single-line or multiline flow-mapping (``{uses: ...}``),
and explicit ``? uses`` entries with exit code 1 so unpinned actions cannot slip past silently.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

USES_CLEANED_RE = re.compile(r"^\s*(?:-\s+)*uses\s*:")
FLOW_OPEN_PREFIX_RE = re.compile(r"^\s*(?:-\s+)*(?:\?\s*)?(?:[^:\[\]{},?#\s][^:\[\]{}]*:\s*)?(?:\[\s*)*$")
FLOW_USES_KEY_RE = re.compile(r"(?:^|[,{\[\s])uses(?:\s*:|\s*$)")
FLOW_SEQ_USES_RE = re.compile(r"\[[^\]]*(?:^|[,\[\s])uses\s*:")
EXPLICIT_INLINE_USES_RE = re.compile(r"^\s*(?:-\s+)*\?\s*uses(?:\s*:|\s*$)")
EXPLICIT_ONLY_QMARK_RE = re.compile(r"^(?:-\s+)*\?$")
EXPLICIT_NEXT_USES_RE = re.compile(r"^\s*uses(?:\s*:|\s*$)")
BLOCK_SCALAR_START_RE = re.compile(r":\s*[|>](?:[+-]?\d+|\d+[+-]?|[+-])?\s*$")
BLOCK_SCALAR_RE = re.compile(r"^[|>](?:[+-]?\d+|\d+[+-]?|[+-])?(?:\s+#.*|\s*)$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST64_RE = re.compile(r"^docker://.+@sha256:[0-9a-f]{64}$")
VERSION_COMMENT_RE = re.compile(r"#\s*v\S+")

_YAML_ESCAPES = {
    "0": "\x00",
    "a": "\a",
    "b": "\b",
    "t": "\t",
    "\t": "\t",
    "n": "\n",
    "v": "\v",
    "f": "\f",
    "r": "\r",
    "e": "\x1b",
    " ": " ",
    '"': '"',
    "/": "/",
    "\\": "\\",
    "N": "\x85",
    "_": "\xa0",
    "L": "\u2028",
    "P": "\u2029",
}
_HEX_WIDTHS = {"x": 2, "u": 4, "U": 8}


def _decode_yaml_escape(line: str, idx: int) -> tuple[str, int]:
    """Decode one YAML double-quoted escape starting after ``\\`` at ``idx``."""
    if idx >= len(line):
        return "", idx
    esc = line[idx]
    width = _HEX_WIDTHS.get(esc)
    if width is not None:
        hex_part = line[idx + 1 : idx + 1 + width]
        if len(hex_part) == width and all(c in "0123456789abcdefABCDEF" for c in hex_part):
            return chr(int(hex_part, 16)), idx + 1 + width
    if esc in _YAML_ESCAPES:
        return _YAML_ESCAPES[esc], idx + 1
    return esc, idx + 1


def _scan_yaml_line(line: str, flow_depth: int = 0, seq_depth: int = 0) -> tuple[str, int, int, bool]:
    """Strip comments/``${{ ... }}``, normalize quoted strings (decoding YAML escapes), and track flow depth."""
    out: list[str] = []
    depth = flow_depth
    seq = seq_depth
    had_flow = depth > 0 or seq > 0
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == "#" and (i == 0 or line[i - 1].isspace()):
            break
        if line.startswith("${{", i):
            j = i + 3
            expr_quote = False
            while j < n:
                if expr_quote:
                    if line[j] == "'":
                        if j + 1 < n and line[j + 1] == "'":
                            j += 2
                            continue
                        expr_quote = False
                elif line[j] == "'":
                    expr_quote = True
                elif line.startswith("}}", j):
                    j += 2
                    break
                j += 1
            out.append('""')
            i = j
            continue
        if ch == "'":
            j = i + 1
            chars: list[str] = []
            while j < n:
                if line[j] == "'":
                    if j + 1 < n and line[j + 1] == "'":
                        chars.append("'")
                        j += 2
                        continue
                    j += 1
                    break
                chars.append(line[j])
                j += 1
            out.append("uses" if "".join(chars) == "uses" else '""')
            i = j
            continue
        if ch == '"':
            j = i + 1
            chars = []
            while j < n:
                if line[j] == "\\":
                    decoded, j = _decode_yaml_escape(line, j + 1)
                    chars.append(decoded)
                    continue
                if line[j] == '"':
                    j += 1
                    break
                chars.append(line[j])
                j += 1
            out.append("uses" if "".join(chars) == "uses" else '""')
            i = j
            continue
        if ch == "{":
            if depth > 0 or seq > 0 or FLOW_OPEN_PREFIX_RE.match("".join(out)):
                depth += 1
                had_flow = True
        elif ch == "}":
            if depth > 0:
                depth -= 1
                had_flow = True
        elif ch == "[":
            if depth > 0 or seq > 0 or FLOW_OPEN_PREFIX_RE.match("".join(out)):
                seq += 1
                had_flow = True
        elif ch == "]" and seq > 0:
            seq -= 1
            had_flow = True
        out.append(ch)
        i += 1
    return "".join(out), depth, seq, had_flow


def _extract_mapping_rhs(line: str) -> str | None:
    """Return the raw substring after the first YAML mapping key ``:`` on ``line``."""
    i = 0
    n = len(line)
    while i < n:
        while i < n and line[i].isspace():
            i += 1
        if i < n and line[i] == "-" and (i + 1 == n or line[i + 1].isspace()):
            i += 1
            continue
        break
    if i >= n:
        return None
    if line[i] == "'":
        i += 1
        while i < n:
            if line[i] == "'":
                if i + 1 < n and line[i + 1] == "'":
                    i += 2
                    continue
                i += 1
                break
            i += 1
    elif line[i] == '"':
        i += 1
        while i < n:
            if line[i] == "\\":
                i += 2
                continue
            if line[i] == '"':
                i += 1
                break
            i += 1
    else:
        while i < n and line[i] != ":":
            i += 1
    while i < n and line[i].isspace():
        i += 1
    if i < n and line[i] == ":":
        return line[i + 1 :]
    return None


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
        flow_depth = 0
        seq_depth = 0
        block_indent: int | None = None
        pending_explicit_key = False
        for lineno, line in enumerate(lines, start=1):
            if block_indent is not None:
                if not line.strip():
                    continue
                if len(line) - len(line.lstrip(" ")) > block_indent:
                    continue
                block_indent = None

            cleaned, flow_depth, seq_depth, in_flow = _scan_yaml_line(line, flow_depth, seq_depth)
            stripped = cleaned.strip()

            if not in_flow and pending_explicit_key:
                if not stripped:
                    continue
                pending_explicit_key = False
                if EXPLICIT_NEXT_USES_RE.match(cleaned):
                    uses_count += 1
                    errors.append(f"::error file={file_ref},line={lineno}::explicit '? uses' key is not supported")
                    continue

            if (in_flow and FLOW_USES_KEY_RE.search(cleaned)) or FLOW_SEQ_USES_RE.search(cleaned):
                uses_count += 1
                errors.append(
                    f"::error file={file_ref},line={lineno}::flow-mapping uses: is not supported; use block mapping"
                )
                continue

            if not in_flow and EXPLICIT_INLINE_USES_RE.match(cleaned):
                uses_count += 1
                errors.append(f"::error file={file_ref},line={lineno}::explicit '? uses' key is not supported")
                continue

            if not in_flow and EXPLICIT_ONLY_QMARK_RE.match(stripped):
                pending_explicit_key = True
                continue

            if USES_CLEANED_RE.match(cleaned):
                uses_count += 1
                raw_rhs = _extract_mapping_rhs(line)
                parsed = None if raw_rhs is None else _split_target_and_comment(raw_rhs)
                if parsed is None:
                    errors.append(f"::error file={file_ref},line={lineno}::empty or multiline uses: is not supported")
                    continue
                reason = _validate_target(*parsed)
                if reason is not None:
                    errors.append(f"::error file={file_ref},line={lineno}::{reason}")
                continue

            if flow_depth == 0 and seq_depth == 0 and BLOCK_SCALAR_START_RE.search(cleaned):
                prefix_match = re.match(r"^(\s*(?:-\s+)*)", cleaned)
                block_indent = len(prefix_match.group(1)) if prefix_match else 0

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
