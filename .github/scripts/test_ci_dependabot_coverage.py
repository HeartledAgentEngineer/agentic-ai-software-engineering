"""Tests for ci_dependabot_coverage.py. Run from the repository root: python -m pytest -q .github/scripts"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ci_dependabot_coverage as coverage  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

COMPLETE = """\
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: monthly
  - package-ecosystem: pip
    directories:
      - /app
      - /tools/cli
    schedule:
      interval: monthly
  - package-ecosystem: npm
    directories:
      - /web
    schedule:
      interval: monthly
"""


def repo(tmp_path: Path, files: list[str], config: str = COMPLETE) -> Path:
    """A small repository: the given files (empty) and .github/dependabot.yml."""
    for name in files:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    (tmp_path / ".github").mkdir(exist_ok=True)
    (tmp_path / ".github" / "dependabot.yml").write_text(config, encoding="utf-8")
    return tmp_path


FILES = ["app/requirements.txt", "tools/cli/pyproject.toml", "web/package.json"]


def run(root: Path, capsys) -> tuple[int, str]:
    code = coverage.main(
        ["--config", str(root / ".github" / "dependabot.yml"), "--root", str(root)]
    )
    return code, capsys.readouterr().out


def test_complete_config_passes(tmp_path, capsys):
    code, out = run(repo(tmp_path, FILES), capsys)
    assert code == 0, out
    assert "Dependabot watches all 3 manifest directories (pip: 2, npm: 1)." in out


def test_unwatched_pip_directory_fails_and_is_named(tmp_path, capsys):
    code, out = run(repo(tmp_path, FILES + ["tools/readfree/requirements.txt"]), capsys)
    assert code == 1
    assert "::error" in out
    assert "pip: /tools/readfree has a manifest but is not in dependabot.yml" in out


def test_unwatched_npm_directory_fails(tmp_path, capsys):
    code, out = run(repo(tmp_path, FILES + ["docs/site/package.json"]), capsys)
    assert code == 1
    assert "npm: /docs/site has a manifest but is not in dependabot.yml" in out


def test_listed_directory_without_manifest_fails(tmp_path, capsys):
    code, out = run(
        repo(tmp_path, ["app/requirements.txt", "web/package.json"]), capsys
    )
    assert code == 1
    assert "pip: /tools/cli is listed in dependabot.yml but holds no manifest" in out


def test_node_modules_and_virtualenvs_are_ignored(tmp_path, capsys):
    extra = [
        "web/node_modules/left-pad/package.json",
        "app/.venv/lib/site-packages/pkg/pyproject.toml",
        "app/venv/requirements.txt",
        ".git/hooks/package.json",
    ]
    code, out = run(repo(tmp_path, FILES + extra), capsys)
    assert code == 0, out


def test_singular_directory_key_is_understood(tmp_path, capsys):
    config = COMPLETE.replace(
        "    directories:\n      - /web\n", "    directory: /web\n"
    )
    code, out = run(repo(tmp_path, FILES, config), capsys)
    assert code == 0, out


def test_pyproject_and_dev_requirements_count_as_pip(tmp_path):
    root = repo(
        tmp_path,
        ["a/pyproject.toml", "b/requirements-dev.txt", "c/requirements_azure.txt"],
    )
    assert coverage.found(root)["pip"] == {"/a", "/b", "/c"}


def test_setup_py_pipfile_and_setup_cfg_count_as_pip(tmp_path):
    root = repo(
        tmp_path, ["a/setup.py", "b/Pipfile", "c/setup.cfg", "d/requirements.in"]
    )
    assert coverage.found(root)["pip"] == {"/a", "/b", "/c", "/d"}


def test_file_names_are_case_sensitive_like_the_linux_runner(tmp_path):
    root = repo(tmp_path, ["a/Requirements.TXT", "b/Package.json"])
    found = coverage.found(root)
    assert found["pip"] == set()
    assert found["npm"] == set()


def test_trailing_slash_is_the_same_directory(tmp_path, capsys):
    config = COMPLETE.replace("      - /tools/cli\n", "      - /tools/cli/\n")
    code, out = run(repo(tmp_path, FILES, config), capsys)
    assert code == 0, out


def test_root_directory_is_normalised(tmp_path, capsys):
    config = COMPLETE.replace("      - /app\n", "      - /\n")
    files = ["requirements.txt", "tools/cli/pyproject.toml", "web/package.json"]
    code, out = run(repo(tmp_path, files, config), capsys)
    assert code == 0, out


def test_config_without_updates_fails(tmp_path, capsys):
    code, out = run(repo(tmp_path, FILES, "version: 2\n"), capsys)
    assert code == 1
    assert "updates" in out


def test_missing_config_fails(tmp_path, capsys):
    code = coverage.main(
        ["--config", str(tmp_path / "missing.yml"), "--root", str(tmp_path)]
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "::error" in out
    assert "cannot read Dependabot config" in out


def test_repository_config_passes(capsys):
    code = coverage.main(
        [
            "--config",
            str(REPO_ROOT / ".github" / "dependabot.yml"),
            "--root",
            str(REPO_ROOT),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0, out


# Dependabot pip also reads requirement files one folder below a listed directory (dependabot-core,
# python/lib/dependabot/python/shared_file_fetcher.rb, req_files_for_dir). Other pip manifests are not read there.
PARENT_ONLY = COMPLETE.replace("      - /tools/cli\n", "")


def test_requirements_one_folder_down_are_covered_by_the_parent(tmp_path, capsys):
    files = [
        "app/requirements.txt",
        "app/shared/requirements_azure.txt",
        "web/package.json",
    ]
    code, out = run(repo(tmp_path, files, PARENT_ONLY), capsys)
    assert code == 0, out
    assert "(pip: 2, npm: 1)" in out


def test_listing_parent_and_requirements_child_fails_as_duplicate(tmp_path, capsys):
    config = COMPLETE.replace("      - /tools/cli\n", "      - /app/shared\n")
    files = [
        "app/requirements.txt",
        "app/shared/requirements_azure.txt",
        "web/package.json",
    ]
    code, out = run(repo(tmp_path, files, config), capsys)
    assert code == 1
    assert (
        "pip: /app/shared is already covered by /app (Dependabot pip reads requirement files one folder down); "
        "listing both opens duplicate pull requests"
    ) in out


def test_pyproject_one_folder_down_is_not_covered_by_the_parent(tmp_path, capsys):
    files = ["app/requirements.txt", "app/lib/pyproject.toml", "web/package.json"]
    code, out = run(repo(tmp_path, files, PARENT_ONLY), capsys)
    assert code == 1
    assert "pip: /app/lib has a manifest but is not in dependabot.yml" in out


def test_requirements_two_folders_down_are_not_covered(tmp_path, capsys):
    files = [
        "app/requirements.txt",
        "app/sub/deep/requirements.txt",
        "web/package.json",
    ]
    code, out = run(repo(tmp_path, files, PARENT_ONLY), capsys)
    assert code == 1
    assert "pip: /app/sub/deep has a manifest but is not in dependabot.yml" in out


def test_root_covers_requirements_in_top_level_folders(tmp_path, capsys):
    config = PARENT_ONLY.replace("      - /app\n", "      - /\n")
    files = ["requirements.txt", "tools/requirements-dev.txt", "web/package.json"]
    code, out = run(repo(tmp_path, files, config), capsys)
    assert code == 0, out


def test_mixed_folder_below_a_listed_parent_must_be_listed_itself(tmp_path, capsys):
    files = [
        "app/requirements.txt",
        "app/lib/pyproject.toml",
        "app/lib/requirements.txt",
        "web/package.json",
    ]
    listed = COMPLETE.replace("      - /tools/cli\n", "      - /app/lib\n")
    code, out = run(repo(tmp_path, files, listed), capsys)
    assert code == 0, out

    code, out = run(repo(tmp_path, files, PARENT_ONLY), capsys)
    assert code == 1
    assert "pip: /app/lib has a manifest but is not in dependabot.yml" in out
