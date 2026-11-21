"""Tests for ci_pinned_actions.py. Run from the repository root: python -m pytest -q .github/scripts"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ci_pinned_actions as pinned  # noqa: E402

SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
DIGEST = "a" * 64


def workflows(tmp_path: Path, text: str, name: str = "ci.yml") -> Path:
    folder = tmp_path / "workflows"
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")
    return folder


def run(folder: Path, capsys) -> tuple[int, str]:
    code = pinned.main([str(folder)])
    return code, capsys.readouterr().out


def test_pinned_with_version_comment_passes(tmp_path, capsys):
    folder = workflows(tmp_path, f"steps:\n  - uses: actions/checkout@{SHA} # v7.0.1\n")
    code, out = run(folder, capsys)
    assert code == 0
    assert "1 uses: lines pinned" in out


@pytest.mark.parametrize("ref", ["v7", "main", SHA[:12], SHA + "0", SHA.upper()])
def test_tag_branch_short_long_or_uppercase_ref_fails(tmp_path, capsys, ref):
    folder = workflows(tmp_path, f"steps:\n  - uses: actions/checkout@{ref} # v7.0.1\n")
    code, out = run(folder, capsys)
    assert code == 1
    assert "::error file=" in out


def test_missing_version_comment_fails(tmp_path, capsys):
    folder = workflows(tmp_path, f"steps:\n  - uses: actions/checkout@{SHA}\n")
    code, out = run(folder, capsys)
    assert code == 1
    assert "version comment" in out


def test_missing_ref_fails(tmp_path, capsys):
    folder = workflows(tmp_path, "steps:\n  - uses: actions/checkout\n")
    assert run(folder, capsys)[0] == 1


@pytest.mark.parametrize("line", [
    f"  - uses: 'actions/checkout@{SHA}' # v7.0.1",
    f'  - uses: "actions/checkout@{SHA}"   # v7.0.1',
    f"  -   uses:   actions/checkout@{SHA}  #   v7.0.1",
    f"    uses: actions/upload-artifact@{SHA} # v7.0.2",
    f"  uses: octo/repo/.github/workflows/build.yml@{SHA} # v1.2.3",
])
def test_accepted_spellings(tmp_path, capsys, line):
    folder = workflows(tmp_path, f"jobs:\n{line}\n")
    assert run(folder, capsys)[0] == 0


@pytest.mark.parametrize("line", [
    "  - uses: 'actions/checkout@v7'",
    '  - uses: "actions/checkout@v7" # v7.0.1',
    "  uses: octo/repo/.github/workflows/build.yml@main # v1.2.3",
])
def test_rejected_spellings(tmp_path, capsys, line):
    folder = workflows(tmp_path, f"jobs:\n{line}\n")
    assert run(folder, capsys)[0] == 1


def test_local_action_is_allowed(tmp_path, capsys):
    folder = workflows(tmp_path, "steps:\n  - uses: ./.github/actions/setup\n")
    assert run(folder, capsys)[0] == 0


def test_docker_needs_a_digest(tmp_path, capsys):
    ok = workflows(tmp_path, f"steps:\n  - uses: docker://alpine@sha256:{DIGEST}\n", "a.yml")
    assert run(ok, capsys)[0] == 0
    (ok / "a.yml").write_text("steps:\n  - uses: docker://alpine:3.20\n", encoding="utf-8")
    assert run(ok, capsys)[0] == 1


def test_finding_names_file_and_line(tmp_path, capsys):
    folder = workflows(tmp_path, f"jobs:\n  a:\n    steps:\n      - uses: actions/checkout@{SHA} # v7.0.1\n"
                                 "      - uses: actions/setup-python@v7\n")
    code, out = run(folder, capsys)
    assert code == 1
    assert "ci.yml,line=5::" in out
    assert "actions/setup-python@v7" in out
    assert "ci.yml,line=4" not in out


def test_yaml_extension_and_subfolders_are_scanned(tmp_path, capsys):
    folder = workflows(tmp_path, f"steps:\n  - uses: actions/checkout@{SHA} # v7.0.1\n")
    (folder / "other.yaml").write_text("steps:\n  - uses: actions/checkout@v7\n", encoding="utf-8")
    code, out = run(folder, capsys)
    assert code == 1
    assert "other.yaml" in out


def test_comment_lines_and_text_mentions_are_ignored(tmp_path, capsys):
    folder = workflows(tmp_path, f"# old: uses: actions/checkout@v4\nsteps:\n"
                                 f"  - run: echo 'uses: actions/checkout@v4'\n"
                                 f"  - run: echo '[{{uses: actions/checkout@v4}}]'\n"
                                 f"  - uses: actions/checkout@{SHA} # v7.0.1\n")
    code, out = run(folder, capsys)
    assert code == 0
    assert "1 uses: lines pinned" in out


def test_no_uses_line_at_all_fails(tmp_path, capsys):
    folder = workflows(tmp_path, "steps:\n  - run: echo hi\n")
    code, out = run(folder, capsys)
    assert code == 1
    assert "no uses:" in out


def test_missing_folder_fails(tmp_path, capsys):
    code, out = run(tmp_path / "missing", capsys)
    assert code == 1
    assert "::error::" in out


@pytest.mark.parametrize("uses_rhs", [">-", ">", "|", "|-", "|+", ">2-", "", "   # only comment"])
def test_multiline_or_empty_uses_fails(tmp_path, capsys, uses_rhs):
    folder = workflows(tmp_path, f"steps:\n  - uses: {uses_rhs}\n    actions/checkout@v7\n")
    code, out = run(folder, capsys)
    assert code == 1
    assert "::error file=" in out
    assert "line=2::" in out


def test_mixed_valid_pinned_and_multiline_uses_fails(tmp_path, capsys):
    content = (
        f"steps:\n"
        f"  - uses: actions/checkout@{SHA} # v7.0.1\n"
        f"  - uses: >-\n"
        f"      actions/setup-python@v7\n"
    )
    folder = workflows(tmp_path, content)
    code, out = run(folder, capsys)
    assert code == 1
    assert "ci.yml,line=3::" in out
    assert "ci.yml,line=2" not in out


@pytest.mark.parametrize("line", [
    "  - {uses: actions/checkout@v7}",
    "  - { name: step, uses: actions/checkout@v7 }",
    '  - {name: "#", uses: actions/checkout@v7}',
    "  - {name: '# foo', uses: actions/checkout@v7}",
    '  - {"uses": "actions/checkout@v7"}',
    "  run: {uses: octo/repo/.github/workflows/build.yml@main}",
    "  steps: [{uses: actions/checkout@v7}]",
    f"  - {{uses: actions/checkout@{SHA}}} # v7.0.1",
])
def test_flow_mapping_uses_fails(tmp_path, capsys, line):
    folder = workflows(tmp_path, f"jobs:\n{line}\n")
    code, out = run(folder, capsys)
    assert code == 1
    assert "::error file=" in out
    assert "line=2::" in out


@pytest.mark.parametrize("bad_line", [
    "  - {uses: actions/checkout@v7}",
    '  - {name: "#", uses: actions/checkout@v7}',
    "  run: {uses: octo/repo/.github/workflows/build.yml@main}",
])
def test_mixed_valid_pinned_and_flow_mapping_uses_fails(tmp_path, capsys, bad_line):
    content = (
        f"jobs:\n"
        f"  - uses: actions/checkout@{SHA} # v7.0.1\n"
        f"{bad_line}\n"
    )
    folder = workflows(tmp_path, content)
    code, out = run(folder, capsys)
    assert code == 1
    assert "ci.yml,line=3::" in out
    assert "ci.yml,line=2" not in out


@pytest.mark.parametrize("block", [
    "  - {\n    name: Checkout,\n    uses: actions/checkout@v7\n  }",
    "  - {\n    name: Checkout,\n    uses\n    : actions/checkout@v7\n  }",
    f"  - {{\n    name: Checkout,\n    uses: actions/checkout@{SHA}\n  }} # v7.0.1",
])
def test_multiline_flow_mapping_uses_fails(tmp_path, capsys, block):
    folder = workflows(tmp_path, f"jobs:\n{block}\n")
    code, out = run(folder, capsys)
    assert code == 1
    assert "::error file=" in out
    assert "line=4::" in out


@pytest.mark.parametrize("block", [
    "  - {\n    name: Checkout,\n    uses: actions/checkout@v7\n  }",
    "  - {\n    name: Checkout,\n    uses\n    : actions/checkout@v7\n  }",
])
def test_mixed_valid_pinned_and_multiline_flow_mapping_uses_fails(tmp_path, capsys, block):
    content = (
        f"jobs:\n"
        f"  - uses: actions/checkout@{SHA} # v7.0.1\n"
        f"{block}\n"
    )
    folder = workflows(tmp_path, content)
    code, out = run(folder, capsys)
    assert code == 1
    assert "ci.yml,line=5::" in out
    assert "ci.yml,line=2" not in out


@pytest.mark.parametrize("block", [
    "  ? uses: actions/checkout@v7",
    "  - ? uses: actions/checkout@v7",
    "  ?\n    uses\n  : actions/checkout@v7",
    "  - - uses: actions/checkout@v7",
])
def test_explicit_or_nested_uses_fails(tmp_path, capsys, block):
    folder = workflows(tmp_path, f"jobs:\n{block}\n")
    code, out = run(folder, capsys)
    assert code == 1
    assert "::error file=" in out


def test_multiline_run_block_scalar_with_braces_and_uses_text_passes(tmp_path, capsys):
    content = (
        "jobs:\n"
        f"  - uses: actions/checkout@{SHA} # v7.0.1\n"
        "  - name: Check shell snippet\n"
        "    run: |\n"
        "      if true; then {\n"
        '        echo "uses: actions/checkout@v4"\n'
        "      }; fi\n"
    )
    folder = workflows(tmp_path, content)
    code, out = run(folder, capsys)
    assert code == 0
    assert "1 uses: lines pinned" in out


@pytest.mark.parametrize("line", [
    r'  - "us\u0065s": actions/checkout@v7',
    r'  - "\x75ses": actions/checkout@v7',
    r'  - {"us\u0065s": actions/checkout@v7}',
    r'  ? "us\u0065s": actions/checkout@v7',
])
def test_escaped_double_quoted_uses_key_fails(tmp_path, capsys, line):
    content = (
        "jobs:\n"
        f"  - uses: actions/checkout@{SHA} # v7.0.1\n"
        f"{line}\n"
    )
    folder = workflows(tmp_path, content)
    code, out = run(folder, capsys)
    assert code == 1
    assert "ci.yml,line=3::" in out
    assert "ci.yml,line=2" not in out


@pytest.mark.parametrize("shell_line", [
    "  - run: echo {",
    "  - run: if [ -f foo; then {",
    "  - run: echo [ uses:example ]",
    "  - run: echo { uses:example }",
])
def test_plain_scalar_with_brace_or_bracket_before_pinned_uses_passes(tmp_path, capsys, shell_line):
    content = (
        "jobs:\n"
        f"{shell_line}\n"
        f"  - uses: actions/checkout@{SHA} # v7.0.1\n"
    )
    folder = workflows(tmp_path, content)
    code, out = run(folder, capsys)
    assert code == 0
    assert "1 uses: lines pinned" in out


@pytest.mark.parametrize("line", [
    "  - &checkout {uses: actions/checkout@v7}",
    "  - !custom {uses: actions/checkout@v7}",
    "  build: &checkout {uses: actions/checkout@v7}",
    "  - &checkout uses: actions/checkout@v7",
    "  - !!map {uses: actions/checkout@v7}",
    "  - !<tag:yaml.org,2002:map> {uses: actions/checkout@v7}",
])
def test_anchored_or_tagged_uses_fails(tmp_path, capsys, line):
    content = (
        "jobs:\n"
        f"  - uses: actions/checkout@{SHA} # v7.0.1\n"
        f"{line}\n"
    )
    folder = workflows(tmp_path, content)
    code, out = run(folder, capsys)
    assert code == 1
    assert "ci.yml,line=3::" in out
    assert "ci.yml,line=2" not in out


def test_doc_start_flow_uses_fails(tmp_path, capsys):
    folder = workflows(tmp_path, "--- {uses: actions/checkout@v7}\n")
    code, out = run(folder, capsys)
    assert code == 1
    assert "ci.yml,line=1::" in out


def test_anchored_multiline_flow_mapping_uses_fails(tmp_path, capsys):
    content = (
        "jobs:\n"
        f"  - uses: actions/checkout@{SHA} # v7.0.1\n"
        "  - &checkout {\n"
        "    name: Checkout,\n"
        "    uses\n"
        "    : actions/checkout@v7\n"
        "  }\n"
    )
    folder = workflows(tmp_path, content)
    code, out = run(folder, capsys)
    assert code == 1
    assert "ci.yml,line=5::" in out
    assert "ci.yml,line=2" not in out


@pytest.mark.parametrize("bad_uses", [
    f"  - uses: 'actions/checkout@{SHA}''@v7' # v7.0.1",
    f'  - uses: "actions/checkout@{SHA}" @v7 # v7.0.1',
    f"  - uses: actions/checkout@v7@{SHA} # v7.0.1",
    "  - uses: ./local\n      extra",
    '  ? "us\\\n    es"\n  : actions/checkout@v7',
])
def test_hardened_target_and_multiline_key_edge_cases_fail(tmp_path, capsys, bad_uses):
    content = (
        "jobs:\n"
        f"  - uses: actions/checkout@{SHA} # v7.0.1\n"
        f"{bad_uses}\n"
    )
    folder = workflows(tmp_path, content)
    code, out = run(folder, capsys)
    assert code == 1
    assert "ci.yml,line=2" not in out


@pytest.mark.parametrize("snippet", [
    '  - run: "echo\n      uses: actions/checkout@v4"',
    "  - run: echo\n      {",
    "  env: {\n    MODE: uses\n  }",
    "  - name: Don't skip checkout",
    "  - name: 'Don''t skip checkout'",
    '  - with: {a: "x", "b":\'y\'}',
])
def test_hardened_valid_multiline_context_before_pinned_uses_passes(tmp_path, capsys, snippet):
    content = (
        "jobs:\n"
        f"{snippet}\n"
        f"  - uses: actions/checkout@{SHA} # v7.0.1\n"
    )
    folder = workflows(tmp_path, content)
    code, out = run(folder, capsys)
    assert code == 0
    assert "1 uses: lines pinned" in out


@pytest.mark.parametrize("snippet", [
    "  - name: Don't skip checkout\n    uses: actions/checkout@v7",
    "  - name: step 'unclosed\n    uses: actions/checkout@v7",
    "  - run: echo 'hello\n    uses: actions/checkout@v7",
    "  - { name: Don't, uses: actions/checkout@v7 }",
    "  - { name: foo\n      'bar, uses: actions/checkout@v7 }",
    "  - {name: foo:'bar, uses: actions/checkout@v7, with: {fetch-depth: '0'}}",
    "  - {name: foo:\n      'bar, uses: actions/checkout@v7, with: {fetch-depth: '0'}}",
    "  - {name:http:'bar, uses: actions/checkout@v7, env: {X: '1'}}",
    "  - {name: foo?'bar, uses: actions/checkout@v7, with: {fetch-depth: '0'}}",
    "  - {name: foo?\n      'bar, uses: actions/checkout@v7, with: {fetch-depth: '0'}}",
    "  - {name: foo ? 'bar, uses: actions/checkout@v7, with: {fetch-depth: '0'}}",
    "  - {? 'uses': actions/checkout@v7}",
    "  - {name: 'unclosed?\n    uses: actions/checkout@v7}",
    "  - foo:'bar\n  - uses: actions/checkout@v7\n  - name: '0'",
    "  - name: foo\n      ? 'bar\n  - uses: actions/checkout@v7\n  - name: '0'",
    "  - {name:\n      foo:'bar, uses: actions/checkout@v7, with: {fetch-depth: '0'}}",
    "  - name: 'unclosed quote at eof",
])
def test_apostrophe_or_unclosed_quote_never_hides_unpinned_uses(tmp_path, capsys, snippet):
    content = (
        "steps:\n"
        f"  - uses: actions/checkout@{SHA} # v7.0.1\n"
        f"{snippet}\n"
    )
    folder = workflows(tmp_path, content)
    code, out = run(folder, capsys)
    assert code == 1
    assert "::error file=" in out
    assert "ci.yml,line=2" not in out





