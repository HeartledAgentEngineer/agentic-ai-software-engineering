"""Tests for ci_release_readiness.py. Run from repository root: python -m pytest -q .github/scripts"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ci_release_readiness as readiness  # noqa: E402

REQUIRED_DOCS = (
    "README.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "docs/verification.md",
    "docs/enterprise-rollout.md",
    "docs/release-checklist.md",
    ".github/workflows/ci.yml",
)


def _make_minimal_repo(root: Path, changelog: str | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel in REQUIRED_DOCS:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if rel == "CHANGELOG.md":
            text = (
                changelog
                if changelog is not None
                else "# Changelog\n\n## [Unreleased]\n"
            )
        else:
            text = f"# {rel}\n"
        target.write_text(text, encoding="utf-8", newline="\n")
    return root


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def test_baseline_passes_and_lists_manual_gates(tmp_path: Path, capsys) -> None:
    repo = _make_minimal_repo(tmp_path / "repo")
    code = readiness.main(["--repo-root", str(repo)])
    out = capsys.readouterr().out
    assert code == 0
    assert "green CI on exact commit" in out
    assert "cross-model review FREI" in out
    assert "explicit owner approval" in out


@pytest.mark.parametrize("missing_rel", REQUIRED_DOCS)
def test_missing_required_file_fails(tmp_path: Path, capsys, missing_rel: str) -> None:
    repo = _make_minimal_repo(tmp_path / "repo")
    (repo / missing_rel).unlink()
    code = readiness.main(["--repo-root", str(repo)])
    out = capsys.readouterr().out
    assert code == 1
    assert missing_rel in out


def test_missing_unreleased_heading_fails(tmp_path: Path, capsys) -> None:
    repo = _make_minimal_repo(
        tmp_path / "repo", changelog="# Changelog\n\nNothing yet.\n"
    )
    code = readiness.main(["--repo-root", str(repo)])
    out = capsys.readouterr().out
    assert code == 1
    assert "[Unreleased]" in out


@pytest.mark.parametrize("bad_version", ["1.0.0", "v01.0.0", "v1.2", "v1.0.0+build"])
def test_invalid_semver_fails(tmp_path: Path, capsys, bad_version: str) -> None:
    repo = _make_minimal_repo(tmp_path / "repo")
    code = readiness.main(["--repo-root", str(repo), "--version", bad_version])
    out = capsys.readouterr().out
    assert code == 1
    assert "SemVer" in out


def test_version_requires_populated_non_comment_section(tmp_path: Path, capsys) -> None:
    repo = _make_minimal_repo(
        tmp_path / "repo",
        changelog=(
            "# Changelog\n\n## [Unreleased]\n\n"
            "## [v0.1.0] - 2026-11-21\n\n"
            "<!-- placeholder only -->\n\n"
            "## [v0.0.9] - 2026-11-20\n\n- Old\n"
        ),
    )
    assert readiness.main(["--repo-root", str(repo), "--version", "v0.1.0"]) == 1
    capsys.readouterr()

    assert readiness.main(["--repo-root", str(repo), "--version", "v0.2.0"]) == 1
    capsys.readouterr()

    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [v0.1.0] - 2026-11-21\n\n- First release notes.\n",
        encoding="utf-8",
        newline="\n",
    )
    assert readiness.main(["--repo-root", str(repo), "--version", "v0.1.0"]) == 0


def test_private_user_path_fails_outside_and_inside_tests(
    tmp_path: Path, capsys
) -> None:
    real_path_prefix = "C:/Users/" + "alice"
    for rel in ("scripts/helper.py", "projects/demo/tests/test_x.py"):
        repo = _make_minimal_repo(tmp_path / rel.replace("/", "_"))
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f'path = "{real_path_prefix}/secret.txt"\n', encoding="utf-8")
        code = readiness.main(["--repo-root", str(repo)])
        out = capsys.readouterr().out
        assert code == 1
        assert rel in out


@pytest.mark.parametrize(
    ("rel", "token", "expected"),
    [
        ("scripts/demo.ps1", "<user>", 0),
        ("projects/demo/tests/test_paths.py", "<user>", 0),
        ("projects/demo/tests/test_paths.py", "x", 0),
        ("projects/demo/tests/test_paths.py", "geheim", 0),
        ("projects/demo/tests/test_paths.py", "GEHEIM-PFAD-4711", 0),
        ("scripts/demo.ps1", "geheim", 1),
        ("scripts/demo.ps1", "GEHEIM-PFAD-4711", 1),
    ],
)
def test_user_path_allowlist_scope_and_case_folding(
    tmp_path: Path, rel: str, token: str, expected: int
) -> None:
    repo = _make_minimal_repo(tmp_path / "repo")
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    fixture = "C:" + "\\" + "Users" + "\\" + token + "\\" + "file.txt"
    target.write_text(f'sample = "{fixture}"\n', encoding="utf-8")
    assert readiness.main(["--repo-root", str(repo)]) == expected


def test_user_path_in_markdown_backticks(tmp_path: Path) -> None:
    repo = _make_minimal_repo(tmp_path / "repo")
    allowed = "C:" + "\\" + "Users" + "\\" + "<user>"
    (repo / "docs/release-checklist.md").write_text(
        f"# Release Checklist\n\nCheck `{allowed}` paths.\n",
        encoding="utf-8",
        newline="\n",
    )
    assert readiness.main(["--repo-root", str(repo)]) == 0

    blocked = "C:" + "\\" + "Users" + "\\" + "alice"
    (repo / "docs/release-checklist.md").write_text(
        f"# Release Checklist\n\nCheck `{blocked}` paths.\n",
        encoding="utf-8",
        newline="\n",
    )
    assert readiness.main(["--repo-root", str(repo)]) == 1


def test_conflict_marker_fails(tmp_path: Path, capsys) -> None:
    repo = _make_minimal_repo(tmp_path / "repo")
    marker = "<" * 7 + " HEAD"
    (repo / "README.md").write_text(f"# README\n{marker}\n", encoding="utf-8")
    code = readiness.main(["--repo-root", str(repo)])
    out = capsys.readouterr().out
    assert code == 1
    assert "README.md" in out


def test_git_ls_files_ignores_untracked_and_catches_tracked(tmp_path: Path) -> None:
    repo = _make_minimal_repo(tmp_path / "gitrepo")
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")

    leak = "C:/Users/" + "alice" + "/private.txt"
    untracked = repo / "scratch_local.txt"
    untracked.write_text(leak + "\n", encoding="utf-8")
    assert readiness.main(["--repo-root", str(repo)]) == 0

    tracked = repo / "notes.md"
    tracked.write_text(leak + "\n", encoding="utf-8")
    _git(repo, "add", "notes.md")
    assert readiness.main(["--repo-root", str(repo)]) == 1
