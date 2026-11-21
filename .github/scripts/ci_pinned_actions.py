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

_NODE_PROP = r"(?:(?:!<[^>]+>|[&!][^\s\[\]{},]+)\s+)*"
USES_CLEANED_RE = re.compile(rf"^\s*(?:---\s+)?(?:-\s+)*{_NODE_PROP}uses\s*:")
FLOW_OPEN_PREFIX_RE = re.compile(
    rf"^\s*(?:---\s+)?(?:-\s+)*(?:\?\s*)?{_NODE_PROP}"
    rf"(?:[^:\[\]{{}},?#\s][^:\[\]{{}}]*:\s*)?(?:(?:\[\s*)|{_NODE_PROP})*$"
)
FLOW_USES_KEY_RE = re.compile(rf"(?:^\s*|[,{{\[]\s*){_NODE_PROP}(?:\?\s*{_NODE_PROP})?uses(?:\s*:|\s*$)")
FLOW_ONLY_WS_AND_PROP_RE = re.compile(rf"^\s*{_NODE_PROP}$")
FLOW_QUOTE_AFTER_DELIM_RE = re.compile(rf"[,{{\[\?]\s*{_NODE_PROP}$")
FLOW_COLON_WS_QUOTE_RE = re.compile(
    rf"(?:^|[,{{\[\?])\s*{_NODE_PROP}(?:[^:\[\]{{}},]|:(?!\s))+:\s+{_NODE_PROP}$"
)
FLOW_QUOTED_KEY_COLON_RE = re.compile(rf"(?:^|[,{{\[\?])\s*{_NODE_PROP}(?:\"\"|uses)\s*:\s*{_NODE_PROP}$")
FLOW_NEXT_NODE_END_RE = re.compile(
    rf"(?:[,{{\[\?]\s*{_NODE_PROP}$|(?:^|[,{{\[\?])\s*{_NODE_PROP}(?:[^:\[\]{{}},]|:(?!\s))+:\s*{_NODE_PROP}$)"
)
EXPLICIT_INLINE_USES_RE = re.compile(rf"^\s*(?:---\s+)?(?:-\s+)*{_NODE_PROP}\?\s*{_NODE_PROP}uses(?:\s*:|\s*$)")
EXPLICIT_ONLY_QMARK_RE = re.compile(rf"^(?:---\s+)?(?:-\s+)*{_NODE_PROP}\?$")
EXPLICIT_NEXT_USES_RE = re.compile(rf"^\s*{_NODE_PROP}uses(?:\s*:|\s*$)")
BLOCK_SCALAR_START_RE = re.compile(r":\s*[|>](?:[+-]?\d+|\d+[+-]?|[+-])?\s*$")
BLOCK_SCALAR_RE = re.compile(r"^[|>](?:[+-]?\d+|\d+[+-]?|[+-])?(?:\s+#.*|\s*)$")
PLAIN_SCALAR_MAPPING_RE = re.compile(
    rf"^\s*(?:---\s+)?(?:-\s+)*{_NODE_PROP}[^:\[\]{{}},?#\s][^:\[\]{{}}]*:\s*{_NODE_PROP}\S"
)
NODE_PROP_PREFIX_RE = re.compile(r"^(?:(?:!<[^>]+>|[&!][^\s#]+)\s+)+")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST64_RE = re.compile(r"^docker://[^@\s]+@sha256:[0-9a-f]{64}$")
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


def _consume_single_quoted(line: str, j: int, chars: list[str]) -> tuple[int, bool]:
    n = len(line)
    while j < n:
        if line[j] == "'":
            if j + 1 < n and line[j + 1] == "'":
                chars.append("'")
                j += 2
                continue
            return j + 1, True
        chars.append(line[j])
        j += 1
    return j, False


def _consume_double_quoted(line: str, j: int, chars: list[str]) -> tuple[int, bool, bool]:
    n = len(line)
    while j < n:
        if line[j] == "\\":
            if j + 1 == n:
                return j + 1, False, True
            decoded, j = _decode_yaml_escape(line, j + 1)
            chars.append(decoded)
            continue
        if line[j] == '"':
            return j + 1, True, False
        chars.append(line[j])
        j += 1
    return j, False, False


def _can_start_quote(prefix: str, depth: int, seq: int, allow_ws_open: bool) -> bool:
    """Return True only when ``prefix`` ends at a YAML node start position."""
    if depth == 0 and seq == 0:
        return bool((prefix.strip() or allow_ws_open) and FLOW_OPEN_PREFIX_RE.match(prefix))
    if FLOW_ONLY_WS_AND_PROP_RE.match(prefix):
        return allow_ws_open
    return bool(
        FLOW_QUOTE_AFTER_DELIM_RE.search(prefix)
        or FLOW_COLON_WS_QUOTE_RE.search(prefix)
        or FLOW_QUOTED_KEY_COLON_RE.search(prefix)
    )


def _scan_yaml_line(
    line: str,
    flow_depth: int = 0,
    seq_depth: int = 0,
    open_quote: str | None = None,
    quote_chars: list[str] | None = None,
    quote_escaped_nl: bool = False,
    allow_whitespace_flow_open: bool = True,
) -> tuple[str, int, int, bool, str | None, list[str], bool]:
    """Strip comments/``${{ ... }}``, track multiline quotes, normalize ``'uses'``/``\"uses\"``, and track flow."""
    out: list[str] = []
    depth = flow_depth
    seq = seq_depth
    had_flow = depth > 0 or seq > 0
    i = 0
    n = len(line)

    if open_quote is not None:
        chars = list(quote_chars or ())
        while i < n and line[i].isspace():
            i += 1
        if open_quote == "'":
            if i < n and chars:
                chars.append(" ")
            j, closed = _consume_single_quoted(line, i, chars)
            if not closed:
                return "", depth, seq, had_flow, "'", chars, False
        else:
            if not quote_escaped_nl and i < n and chars:
                chars.append(" ")
            j, closed, escaped_nl = _consume_double_quoted(line, i, chars)
            if not closed:
                return "", depth, seq, had_flow, '"', chars, escaped_nl
        out.append("uses" if "".join(chars) == "uses" else '""')
        i = j

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
        if ch in ("'", '"') and _can_start_quote("".join(out), depth, seq, allow_whitespace_flow_open):
            chars = []
            if ch == "'":
                j, closed = _consume_single_quoted(line, i + 1, chars)
                if not closed:
                    return "".join(out), depth, seq, had_flow, "'", chars, False
            else:
                j, closed, escaped_nl = _consume_double_quoted(line, i + 1, chars)
                if not closed:
                    return "".join(out), depth, seq, had_flow, '"', chars, escaped_nl
            out.append("uses" if "".join(chars) == "uses" else '""')
            i = j
            continue
        if ch == "{":
            prefix = "".join(out)
            if depth > 0 or seq > 0 or ((prefix.strip() or allow_whitespace_flow_open) and FLOW_OPEN_PREFIX_RE.match(prefix)):
                depth += 1
                had_flow = True
        elif ch == "}":
            if depth > 0:
                depth -= 1
                had_flow = True
        elif ch == "[":
            prefix = "".join(out)
            if depth > 0 or seq > 0 or ((prefix.strip() or allow_whitespace_flow_open) and FLOW_OPEN_PREFIX_RE.match(prefix)):
                seq += 1
                had_flow = True
        elif ch == "]" and seq > 0:
            seq -= 1
            had_flow = True
        out.append(ch)
        i += 1
    return "".join(out), depth, seq, had_flow, None, [], False


def _extract_mapping_rhs(line: str) -> str | None:
    """Return the raw substring after the first YAML mapping key ``:`` on ``line``."""
    i = 0
    n = len(line)
    while i < n and line[i].isspace():
        i += 1
    if line.startswith("---", i) and (i + 3 == n or line[i + 3].isspace()):
        i += 3
    while i < n:
        while i < n and line[i].isspace():
            i += 1
        if i < n and line[i] == "-" and (i + 1 == n or line[i + 1].isspace()):
            i += 1
            continue
        if line.startswith("!<", i):
            gt = line.find(">", i + 2)
            if gt != -1:
                i = gt + 1
                continue
        if i < n and line[i] in ("&", "!"):
            while i < n and not line[i].isspace():
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
    rest = NODE_PROP_PREFIX_RE.sub("", raw_rhs.strip())
    if not rest or rest.startswith(("#", "&", "!", "*")) or BLOCK_SCALAR_RE.match(rest):
        return None
    if rest[0] in ("'", '"'):
        chars: list[str] = []
        if rest[0] == "'":
            end, closed = _consume_single_quoted(rest, 1, chars)
            if not closed:
                return None
        else:
            end, closed, escaped_nl = _consume_double_quoted(rest, 1, chars)
            if not closed or escaped_nl:
                return None
        after = rest[end:]
        trailing = after.strip()
        if trailing and not (after[0].isspace() and trailing.startswith("#")):
            return None
        target = "".join(chars).strip()
        if not target or any(ch.isspace() for ch in target):
            return None
        return target, trailing
    comment_idx = next((idx for idx, ch in enumerate(rest) if ch == "#" and idx > 0 and rest[idx - 1].isspace()), -1)
    if comment_idx == -1:
        target, trailing = rest, ""
    else:
        target, trailing = rest[:comment_idx].strip(), rest[comment_idx:].strip()
    if not target or any(ch.isspace() for ch in target):
        return None
    return target, trailing


def _validate_target(target: str, trailing: str) -> str | None:
    """Return an error reason if ``target``/``trailing`` violates pinning policy, else ``None``."""
    if any(ch.isspace() for ch in target):
        return f"invalid whitespace in uses: target ({target})"
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
        last_uses_indent: int | None = None
        plain_scalar_indent: int | None = None
        open_quote: str | None = None
        open_quote_lineno = 0
        flow_node_ready = True
        quote_chars: list[str] = []
        quote_escaped_nl = False
        pending_explicit_key = False
        for lineno, line in enumerate(lines, start=1):
            if block_indent is not None:
                if not line.strip():
                    continue
                if len(line) - len(line.lstrip(" ")) > block_indent:
                    continue
                block_indent = None

            raw_stripped = line.strip()
            indent = len(line) - len(line.lstrip(" \t"))
            if open_quote is None:
                if last_uses_indent is not None:
                    if not raw_stripped:
                        continue
                    if raw_stripped.startswith("#"):
                        last_uses_indent = None
                        continue
                    if indent > last_uses_indent:
                        errors.append(f"::error file={file_ref},line={lineno}::empty or multiline uses: is not supported")
                        last_uses_indent = None
                        continue
                    last_uses_indent = None
                if plain_scalar_indent is not None:
                    if not raw_stripped:
                        continue
                    if raw_stripped.startswith("#") or indent <= plain_scalar_indent:
                        plain_scalar_indent = None

            prev_open_quote = open_quote
            if flow_depth > 0 or seq_depth > 0:
                allow_ws_flow = flow_node_ready
            else:
                allow_ws_flow = not (plain_scalar_indent is not None and indent > plain_scalar_indent)
            cleaned, flow_depth, seq_depth, in_flow, open_quote, quote_chars, quote_escaped_nl = _scan_yaml_line(
                line,
                flow_depth,
                seq_depth,
                open_quote,
                quote_chars,
                quote_escaped_nl,
                allow_ws_flow,
            )
            stripped = cleaned.strip()
            if prev_open_quote is None and open_quote is not None:
                open_quote_lineno = lineno
            if flow_depth == 0 and seq_depth == 0:
                flow_node_ready = True
            elif open_quote is None and stripped:
                flow_node_ready = bool(FLOW_NEXT_NODE_END_RE.search(cleaned))

            if not in_flow and pending_explicit_key:
                if not stripped:
                    continue
                pending_explicit_key = False
                if EXPLICIT_NEXT_USES_RE.match(cleaned):
                    uses_count += 1
                    errors.append(f"::error file={file_ref},line={lineno}::explicit '? uses' key is not supported")
                    continue

            if in_flow and FLOW_USES_KEY_RE.search(cleaned):
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
                elif not parsed[1]:
                    prefix_match = re.match(r"^(\s*(?:---\s+)?(?:-\s+)*)", cleaned)
                    last_uses_indent = len(prefix_match.group(1)) if prefix_match else 0
                continue

            if flow_depth == 0 and seq_depth == 0 and BLOCK_SCALAR_START_RE.search(cleaned):
                prefix_match = re.match(r"^(\s*(?:-\s+)*)", cleaned)
                block_indent = len(prefix_match.group(1)) if prefix_match else 0
            elif (
                flow_depth == 0
                and seq_depth == 0
                and not in_flow
                and open_quote is None
                and plain_scalar_indent is None
                and PLAIN_SCALAR_MAPPING_RE.match(cleaned)
            ):
                prefix_match = re.match(r"^(\s*(?:---\s+)?(?:-\s+)*)", cleaned)
                plain_scalar_indent = len(prefix_match.group(1)) if prefix_match else 0

        if open_quote is not None:
            errors.append(f"::error file={file_ref},line={open_quote_lineno}::unclosed YAML {open_quote} quote")

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
