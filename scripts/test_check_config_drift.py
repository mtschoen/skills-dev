#!/usr/bin/env python3
"""Tests for check_config_drift's pure helper functions.

is_fixture_path and ruff_pin_errors_in_text take plain strings, no git or
filesystem access, so they are tested directly. tracked_files (and the
checks built on it) shell out to `git ls-files`, so those get a light
integration test against a real throwaway git repo instead of a mock.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_config_drift as guard

# --- is_fixture_path ---


def test_is_fixture_path_matches_workspace_tree():
    assert guard.is_fixture_path("workspace/mock_repo/src/__init__.py")


def test_is_fixture_path_matches_evals_fixtures():
    assert guard.is_fixture_path("evals/fixtures/python-script/convert.py")


def test_is_fixture_path_matches_tests_fixtures():
    assert guard.is_fixture_path("tests/fixtures/sessions-demo.csv")


def test_is_fixture_path_does_not_match_seed_trees():
    # seed/ scripts run live during an eval, so they are NOT fixtures.
    path = "evals/scenarios/todo-in-committed-code/seed/src/thumbnails.py"
    assert not guard.is_fixture_path(path)


def test_is_fixture_path_does_not_match_harness_files():
    assert not guard.is_fixture_path("evals/grade.py")


def test_is_fixture_path_requires_exact_segment_not_substring():
    # A real directory that merely contains "fixtures" as a substring must
    # not be swept in by a loose match.
    assert not guard.is_fixture_path("my_fixtures_helper/thing.py")
    assert not guard.is_fixture_path("workspaces/thing.py")


# --- ruff_pin_errors_in_text ---


def test_ruff_pin_errors_accepts_the_fleet_pin():
    text = "      - run: pip install ruff==0.15.15 pytest\n"
    assert guard.ruff_pin_errors_in_text("lint.yml", text) == []


def test_ruff_pin_errors_flags_wrong_version():
    text = "      - run: pip install ruff==0.11.0 pytest\n"
    errors = guard.ruff_pin_errors_in_text("lint.yml", text)
    assert len(errors) == 1
    assert "0.11.0" in errors[0]
    assert guard.FLEET_RUFF_PIN in errors[0]


def test_ruff_pin_errors_flags_unpinned_install():
    text = "      - run: pip install ruff pytest\n"
    errors = guard.ruff_pin_errors_in_text("lint.yml", text)
    assert len(errors) == 1
    assert "without a version pin" in errors[0]


def test_ruff_pin_errors_accepts_uvx_form():
    text = "      - run: uvx ruff@0.15.15 check .\n"
    assert guard.ruff_pin_errors_in_text("lint.yml", text) == []


def test_ruff_pin_errors_ignores_usage_lines():
    # "ruff check"/"ruff format" mention ruff but are not installs.
    text = "      - run: ruff check evals/\n      - run: ruff format --check evals/\n"
    assert guard.ruff_pin_errors_in_text("lint.yml", text) == []


def test_ruff_pin_errors_reports_line_number():
    text = "one\ntwo\n      - run: pip install ruff==9.9.9\n"
    errors = guard.ruff_pin_errors_in_text("lint.yml", text)
    assert errors[0].startswith("lint.yml:3:")


# --- tracked_files / check_code_without_ci / check_em_dash (real git repo) ---


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _init_repo(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    _git("init", cwd=root)
    _git("config", "user.email", "test@example.com", cwd=root)
    _git("config", "user.name", "Test", cwd=root)


def test_tracked_files_excludes_untracked_and_ignored(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "tracked.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "untracked.py").write_text("y = 2\n", encoding="utf-8")
    _git("add", "tracked.py", cwd=repo)
    _git("commit", "-m", "init", cwd=repo)

    files = guard.tracked_files(tmp_path, "repo")
    assert files == ["tracked.py"]


def test_check_code_without_ci_flags_missing_python_job(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "evals").mkdir()
    (repo / "evals" / "run.py").write_text("print('hi')\n", encoding="utf-8")
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "lint.yml").write_text(
        "jobs:\n  markdown:\n    steps: []\n", encoding="utf-8"
    )
    _git("add", "-A", cwd=repo)
    _git("commit", "-m", "init", cwd=repo)

    errors = guard.check_code_without_ci(tmp_path, "repo")
    assert len(errors) == 1
    assert "ruff+pytest" in errors[0]


def test_check_code_without_ci_ignores_fixture_only_python(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    fixture_dir = repo / "evals" / "fixtures"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "convert.py").write_text("print('hi')\n", encoding="utf-8")
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "lint.yml").write_text(
        "jobs:\n  markdown:\n    steps: []\n", encoding="utf-8"
    )
    _git("add", "-A", cwd=repo)
    _git("commit", "-m", "init", cwd=repo)

    assert guard.check_code_without_ci(tmp_path, "repo") == []


def test_check_em_dash_flags_tracked_file_with_em_dash(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "notes.md").write_text("a plain sentence\n", encoding="utf-8")
    # Spelled as an escape, not the character itself, so this test file does
    # not trip the very check it exercises.
    (repo / "bad.md").write_bytes("look\u2014here\n".encode())
    _git("add", "-A", cwd=repo)
    _git("commit", "-m", "init", cwd=repo)

    errors = guard.check_em_dash(tmp_path, "repo")
    assert len(errors) == 1
    assert "bad.md" in errors[0]


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
