#!/usr/bin/env python3
"""Tests for check_config_drift.

is_fixture_path and ruff_pin_errors_in_text take plain strings, no git or
filesystem access, so they are tested directly. tracked_files (and the
checks built on it) shell out to `git ls-files`, so those get a light
integration test against a real throwaway git repo instead of a mock. The
config/workflow shape checks read files directly, so they run against
tmp_path directory trees.
"""

import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

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


# --- parse_workflow_yaml / tool_run_targets / path_is_covered / shellcheck_targets ---


def test_parse_workflow_yaml_parses_a_mapping():
    workflow = guard.parse_workflow_yaml("jobs:\n  build:\n    steps: []\n")
    assert workflow == {"jobs": {"build": {"steps": []}}}


def test_parse_workflow_yaml_returns_empty_dict_for_non_mapping_document():
    assert guard.parse_workflow_yaml("") == {}
    assert guard.parse_workflow_yaml("- just\n- a\n- list\n") == {}


def test_tool_run_targets_returns_none_when_the_tool_never_appears():
    workflow = guard.parse_workflow_yaml("steps:\n  - run: echo hi\n")
    assert guard.tool_run_targets(workflow, guard._PYTEST_STEP) is None


def test_tool_run_targets_falls_back_to_working_directory_with_no_args():
    workflow = guard.parse_workflow_yaml(
        "steps:\n  - working-directory: evals\n    run: pytest\n"
    )
    assert guard.tool_run_targets(workflow, guard._PYTEST_STEP) == [("dir", "evals")]


def test_tool_run_targets_classifies_directory_and_file_arguments():
    workflow = guard.parse_workflow_yaml(
        "steps:\n  - run: ruff check evals tests deploy.py\n"
    )
    targets = guard.tool_run_targets(
        workflow, guard._RUFF_STEP, skip_tokens=guard.RUFF_SUBCOMMAND_TOKENS
    )
    assert set(targets) == {("dir", "evals"), ("dir", "tests"), ("glob", "deploy.py")}


def test_tool_run_targets_skips_subcommand_and_flag_tokens():
    workflow = guard.parse_workflow_yaml(
        "steps:\n  - run: ruff format --check scripts/\n"
    )
    targets = guard.tool_run_targets(
        workflow, guard._RUFF_STEP, skip_tokens=guard.RUFF_SUBCOMMAND_TOKENS
    )
    assert targets == [("dir", "scripts")]


def test_tool_run_targets_ignores_tool_names_inside_a_pip_install_line():
    """A shared `pip install ruff==... pytest ...` line must not be read as
    an invocation of either tool - both names appear only as install
    arguments, not as the command being run. Before anchoring the match to
    the start of a command segment, this produced junk targets like
    `('glob', '==0.15.15')` for ruff and a bare working-directory target for
    pytest, which happened to be harmless only because it was permissive.
    """
    workflow = guard.parse_workflow_yaml(
        "steps:\n  - run: pip install ruff==0.15.15 pytest pytest-cov\n"
    )
    assert guard.tool_run_targets(workflow, guard._RUFF_STEP) is None
    assert guard.tool_run_targets(workflow, guard._PYTEST_STEP) is None


def test_tool_run_targets_recognizes_python_dash_m_invocation():
    workflow = guard.parse_workflow_yaml(
        "steps:\n  - working-directory: agent-remote\n    run: python -m pytest tests -q\n"
    )
    assert guard.tool_run_targets(workflow, guard._PYTEST_STEP) == [
        ("dir", "agent-remote/tests")
    ]


def test_tool_run_targets_only_matches_a_tool_leading_its_own_command_segment():
    """`ruff`/`pytest` appearing after a `&&`/`;` still counts - only a tool
    name buried mid-argument-list (the pip install shape) is excluded.
    """
    workflow = guard.parse_workflow_yaml(
        "steps:\n  - run: echo start && ruff check evals\n"
    )
    targets = guard.tool_run_targets(
        workflow, guard._RUFF_STEP, skip_tokens=guard.RUFF_SUBCOMMAND_TOKENS
    )
    assert targets == [("dir", "evals")]


def test_path_is_covered_dir_target_matches_by_prefix():
    targets = [("dir", "hooks")]
    assert guard.path_is_covered(targets, "hooks/deploy.sh")
    assert not guard.path_is_covered(targets, "research-first/hooks/deploy.sh")


def test_path_is_covered_empty_dir_target_covers_everything():
    assert guard.path_is_covered([("dir", "")], "anything/at/all.py")


def test_path_is_covered_glob_target_matches_by_fnmatch():
    targets = [("glob", "scripts/*.sh")]
    assert guard.path_is_covered(targets, "scripts/deploy.sh")
    assert not guard.path_is_covered(targets, "install-skills.sh")


def test_shellcheck_targets_reads_scandir_from_an_action_step():
    workflow = guard.parse_workflow_yaml(
        "jobs:\n"
        "  shell:\n"
        "    steps:\n"
        "      - uses: ludeeus/action-shellcheck@2.0.0\n"
        "        with:\n"
        "          scandir: '.'\n"
    )
    assert guard.shellcheck_targets(workflow) == [("dir", "")]


def test_shellcheck_targets_returns_none_without_a_shellcheck_step():
    workflow = guard.parse_workflow_yaml("steps:\n  - run: ruff check .\n")
    assert guard.shellcheck_targets(workflow) is None


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
    assert "no pytest step" in errors[0]


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


def test_check_em_dash_skips_tracked_file_that_disappears(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "tracked_files", lambda _root, _path: ["gone.md"])

    assert guard.check_em_dash(tmp_path, "") == []


# --- strip_jsonc_comments ---


def test_strip_jsonc_comments_removes_line_comments():
    text = '{\n  // a comment\n  "a": 1\n}\n'
    assert json.loads(guard.strip_jsonc_comments(text)) == {"a": 1}


def test_strip_jsonc_comments_keeps_double_slash_inside_strings():
    text = '{"url": "http://example.com//x"}'
    assert guard.strip_jsonc_comments(text) == text


def test_strip_jsonc_comments_handles_escaped_quotes_in_strings():
    text = '{"a": "she said \\"hi\\" // not a comment"}'
    assert guard.strip_jsonc_comments(text) == text


def test_strip_jsonc_comments_handles_comment_at_eof_without_newline():
    assert guard.strip_jsonc_comments("{} // trailing") == "{} "


# --- expected_markdownlint_config ---


def test_expected_config_project_lock_gets_its_own_shape():
    assert guard.expected_markdownlint_config("project-lock") == (
        guard.PROJECT_LOCK_CONFIG
    )


def test_expected_config_exception_repos_get_their_override():
    assert (
        guard.expected_markdownlint_config("docs-update")
        == (guard.MODAL_CONFIG_EXCEPTIONS["docs-update"])
    )


def test_expected_config_unknown_repo_gets_the_canonical_shape():
    assert guard.expected_markdownlint_config("some-new-skill") == (
        guard.CANONICAL_MODAL_CONFIG
    )


# --- check_markdownlint_config ---


def test_check_markdownlint_config_flags_missing_file(tmp_path):
    errors = guard.check_markdownlint_config(tmp_path, "alpha")
    assert errors == ["alpha: missing .markdownlint-cli2.jsonc"]


def test_check_markdownlint_config_flags_unparseable_jsonc(tmp_path):
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpha" / ".markdownlint-cli2.jsonc").write_text(
        "{not json\n", encoding="utf-8"
    )
    errors = guard.check_markdownlint_config(tmp_path, "alpha")
    assert len(errors) == 1
    assert "did not parse as JSON" in errors[0]


def test_check_markdownlint_config_flags_shape_mismatch(tmp_path):
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpha" / ".markdownlint-cli2.jsonc").write_text(
        '{"config": {"default": true}}\n', encoding="utf-8"
    )
    errors = guard.check_markdownlint_config(tmp_path, "alpha")
    assert len(errors) == 1
    assert "does not match its expected shape" in errors[0]


def test_check_markdownlint_config_accepts_canonical_shape_with_comments(tmp_path):
    (tmp_path / "alpha").mkdir()
    canonical = json.dumps(guard.CANONICAL_MODAL_CONFIG, indent=2)
    (tmp_path / "alpha" / ".markdownlint-cli2.jsonc").write_text(
        "// canonical modal config\n" + canonical + "\n", encoding="utf-8"
    )
    assert guard.check_markdownlint_config(tmp_path, "alpha") == []


# --- check_lint_workflow ---

_GOOD_LINT_YML = """name: lint
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:
jobs:
  markdown:
    timeout-minutes: 5
    steps:
      - uses: DavidAnson/markdownlint-cli2-action@v23
"""


def _write_lint_yml(repo: Path, text: str):
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    (workflows / "lint.yml").write_text(text, encoding="utf-8")


def test_check_lint_workflow_flags_missing_file(tmp_path):
    errors = guard.check_lint_workflow(tmp_path, "alpha")
    assert errors == ["alpha: missing .github/workflows/lint.yml"]


def test_check_lint_workflow_flags_every_missing_invariant(tmp_path):
    (tmp_path / "alpha").mkdir()
    _write_lint_yml(tmp_path / "alpha", "jobs:\n  build:\n    steps: []\n")
    errors = guard.check_lint_workflow(tmp_path, "alpha")
    assert len(errors) == 5


def test_check_lint_workflow_accepts_the_canonical_shape(tmp_path):
    (tmp_path / "alpha").mkdir()
    _write_lint_yml(tmp_path / "alpha", _GOOD_LINT_YML)
    assert guard.check_lint_workflow(tmp_path, "alpha") == []


# --- check_ruff_pin ---


def test_check_ruff_pin_passes_when_no_workflows_dir(tmp_path):
    assert guard.check_ruff_pin(tmp_path, "alpha") == []


def test_check_ruff_pin_scopes_submodule_and_umbrella_labels(tmp_path):
    _write_lint_yml(tmp_path / "alpha", "- run: pip install ruff==0.11.0\n")
    _write_lint_yml(tmp_path, "- run: pip install ruff\n")
    sub_errors = guard.check_ruff_pin(tmp_path, "alpha")
    umbrella_errors = guard.check_ruff_pin(tmp_path, "")
    assert len(sub_errors) == 1 and sub_errors[0].startswith("alpha/lint.yml:")
    assert len(umbrella_errors) == 1
    assert umbrella_errors[0].startswith("lint.yml:")


# --- check_code_without_ci (shell side) ---


def test_check_code_without_ci_flags_missing_shellcheck_step(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "deploy.sh").write_text("#!/bin/sh\ntrue\n", encoding="utf-8")
    _write_lint_yml(repo, "steps:\n  - run: ruff check .\n  - run: pytest\n")
    _git("add", "-A", cwd=repo)
    _git("commit", "-m", "init", cwd=repo)

    errors = guard.check_code_without_ci(tmp_path, "repo")
    assert len(errors) == 1
    assert "shellcheck" in errors[0]


def test_check_code_without_ci_passes_with_all_steps_present(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "run.py").write_text("print('hi')\n", encoding="utf-8")
    (repo / "deploy.sh").write_text("#!/bin/sh\ntrue\n", encoding="utf-8")
    _write_lint_yml(
        repo,
        "steps:\n  - run: ruff check .\n  - run: pytest\n  - run: shellcheck deploy.sh\n",
    )
    _git("add", "-A", cwd=repo)
    _git("commit", "-m", "init", cwd=repo)

    assert guard.check_code_without_ci(tmp_path, "repo") == []


def test_check_code_without_ci_flags_shellcheck_scandir_that_misses_the_file(tmp_path):
    """Regression test for schoen-lab skills-dev#36.

    Before the fix, the guard decided a repo had shellcheck coverage by
    regex-matching the word "shellcheck" anywhere in lint.yml, never
    checking that the configured scandir actually reached a tracked .sh
    file. `skills-working-method` hit exactly this: `scandir: './hooks'`
    scanned an empty directory for weeks because the real hooks/ lived one
    level deeper, under research-first/hooks/, while the guard reported the
    submodule compliant. Confirmed against the pre-fix implementation
    (git stash) that this scenario returned [] there; it must not here.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    nested_hooks = repo / "research-first" / "hooks"
    nested_hooks.mkdir(parents=True)
    (nested_hooks / "prompt-reminder.sh").write_text(
        "#!/bin/sh\ntrue\n", encoding="utf-8"
    )
    _write_lint_yml(
        repo,
        "jobs:\n"
        "  shell:\n"
        "    steps:\n"
        "      - uses: ludeeus/action-shellcheck@2.0.0\n"
        "        with:\n"
        "          scandir: './hooks'\n",
    )
    _git("add", "-A", cwd=repo)
    _git("commit", "-m", "init", cwd=repo)

    errors = guard.check_code_without_ci(tmp_path, "repo")
    assert len(errors) == 1
    assert "research-first/hooks/prompt-reminder.sh" in errors[0]
    assert "not covered by any configured shellcheck" in errors[0]


def test_check_code_without_ci_flags_ruff_step_scoped_to_the_wrong_skill(tmp_path):
    """Regression test for the same vacuous-pass shape applied to ruff.

    Before the fix, `_RUFF_STEP.search(text)` matched anywhere in the whole
    lint.yml, so deleting one skill's entire ruff step out of a shared file
    with multiple skills' python blocks still passed as long as some other
    skill's block still mentioned "ruff". Confirmed against the pre-fix
    implementation (git stash) that this scenario returned [] there; it
    must not here.
    """
    repo = tmp_path / "family"
    _init_repo(repo)
    (repo / "alpha").mkdir()
    (repo / "alpha" / "tool.py").write_text("print('a')\n", encoding="utf-8")
    (repo / "beta").mkdir()
    (repo / "beta" / "tool.py").write_text("print('b')\n", encoding="utf-8")
    _write_lint_yml(
        repo,
        "jobs:\n"
        "  python:\n"
        "    steps:\n"
        "      - name: alpha\n"
        "        working-directory: alpha\n"
        "        run: |\n"
        "          ruff check .\n"
        "          pytest\n"
        # beta's own ruff step is gone; only its pytest step remains.
        "      - name: beta\n"
        "        working-directory: beta\n"
        "        run: |\n"
        "          pytest\n",
    )
    _git("add", "-A", cwd=repo)
    _git("commit", "-m", "init", cwd=repo)

    errors = guard.check_code_without_ci(tmp_path, "family")
    assert len(errors) == 1
    assert "beta/tool.py" in errors[0]
    assert "not scanned by any configured ruff step" in errors[0]


def test_check_code_without_ci_skips_when_lint_yml_missing(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "run.py").write_text("print('hi')\n", encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-m", "init", cwd=repo)

    # The missing lint.yml is check_lint_workflow's finding, not this check's.
    assert guard.check_code_without_ci(tmp_path, "repo") == []


def test_check_code_without_ci_ignores_a_stale_nested_workflow_when_root_covers_the_file(
    tmp_path,
):
    """A dead nested lint.yml must not cause a false positive.

    Forges only execute .github/workflows/lint.yml at the repository root,
    so coverage is judged against the root workflow only. Before the
    root-only routing fix, a nested lint.yml one level below a submodule
    root was consulted instead of the root whenever one existed - here that
    nested file is stale/incomplete, which would have made a file the root
    workflow genuinely covers look uncovered.
    """
    repo = tmp_path / "family"
    _init_repo(repo)
    child = repo / "child"
    child.mkdir(parents=True)
    (child / "run.py").write_text("print('hi')\n", encoding="utf-8")
    (child / "deploy.sh").write_text("#!/bin/sh\ntrue\n", encoding="utf-8")
    _write_lint_yml(
        repo,
        "steps:\n  - run: ruff check .\n  - run: pytest\n  - run: shellcheck child/deploy.sh\n",
    )
    # Stale nested workflow: looks like real CI, covers nothing, never runs.
    _write_lint_yml(child, "jobs:\n  markdown:\n    steps: []\n")
    _git("add", "-A", cwd=repo)
    _git("commit", "-m", "init", cwd=repo)

    assert guard.check_code_without_ci(tmp_path, "family") == []


def test_check_code_without_ci_does_not_let_a_nested_workflow_mask_a_root_gap(tmp_path):
    """A nested lint.yml that looks complete must not mask a real root gap.

    The nested workflow here has full ruff+pytest coverage for child/'s
    files, but it never runs - only the root lint.yml does, and the root
    lint.yml has no python coverage at all. The finding must still fire.
    """
    repo = tmp_path / "family"
    _init_repo(repo)
    child = repo / "child"
    child.mkdir(parents=True)
    (child / "run.py").write_text("print('hi')\n", encoding="utf-8")
    _write_lint_yml(repo, "jobs:\n  markdown:\n    steps: []\n")
    # This nested workflow looks fully complete - it must not be trusted.
    _write_lint_yml(child, "steps:\n  - run: ruff check .\n  - run: pytest\n")
    _git("add", "-A", cwd=repo)
    _git("commit", "-m", "init", cwd=repo)

    errors = guard.check_code_without_ci(tmp_path, "family")
    assert len(errors) == 1
    assert "family/child:" in errors[0]
    assert "no pytest step" in errors[0]


def test_check_ruff_pin_checks_nested_child_workflows(tmp_path):
    repo = tmp_path / "family"
    _init_repo(repo)
    child = repo / "child"
    _write_lint_yml(repo, "- run: pip install ruff==0.15.15\n")
    _write_lint_yml(child, "- run: pip install ruff==0.11.0\n")
    errors = guard.check_ruff_pin(tmp_path, "family")
    assert len(errors) == 1
    assert errors[0].startswith("family/child/lint.yml:")
    assert "0.11.0" in errors[0]


# --- check_nested_workflows ---


def test_check_nested_workflows_flags_a_dead_nested_lint_yml(tmp_path):
    repo = tmp_path / "family"
    child = repo / "child"
    _write_lint_yml(child, "jobs:\n  markdown:\n    steps: []\n")

    errors = guard.check_nested_workflows(tmp_path, "family")
    assert len(errors) == 1
    assert "family/child:" in errors[0]
    assert "child/.github/workflows/lint.yml" in errors[0]
    assert "never runs" in errors[0]


def test_check_nested_workflows_passes_with_no_nested_workflow(tmp_path):
    repo = tmp_path / "family"
    child = repo / "child"
    child.mkdir(parents=True)
    (child / "SKILL.md").write_text("# child\n", encoding="utf-8")

    assert guard.check_nested_workflows(tmp_path, "family") == []


def test_check_nested_workflows_ignores_dot_directories(tmp_path):
    repo = tmp_path / "family"
    dot_dir = repo / ".github"
    _write_lint_yml(dot_dir, "jobs:\n  markdown:\n    steps: []\n")

    assert guard.check_nested_workflows(tmp_path, "family") == []


def test_check_nested_workflows_finds_every_nested_skill(tmp_path):
    repo = tmp_path / "family"
    _write_lint_yml(repo / "alpha", "jobs:\n  markdown:\n    steps: []\n")
    _write_lint_yml(repo / "beta", "jobs:\n  markdown:\n    steps: []\n")

    errors = guard.check_nested_workflows(tmp_path, "family")
    assert len(errors) == 2
    assert any("family/alpha:" in error for error in errors)
    assert any("family/beta:" in error for error in errors)


def test_check_submodule_includes_nested_workflow_findings(tmp_path):
    repo = tmp_path / "alpha"
    _init_repo(repo)
    config = json.dumps(guard.CANONICAL_MODAL_CONFIG, indent=2)
    (repo / ".markdownlint-cli2.jsonc").write_text(config, encoding="utf-8")
    _write_lint_yml(repo, _GOOD_LINT_YML)
    _write_lint_yml(repo / "child", "jobs:\n  markdown:\n    steps: []\n")
    _git("add", "-A", cwd=repo)
    _git("commit", "-m", "init", cwd=repo)

    errors = guard.check_submodule(tmp_path, "alpha")
    assert any("never runs" in error for error in errors)


# --- evaluate / main ---


def _make_umbrella_repo(tmp_path, *, canonical_config=True):
    """Build an umbrella-shaped repo with one clean alpha submodule."""
    root = tmp_path / "umbrella"
    alpha = root / "alpha"
    _init_repo(alpha)
    if canonical_config:
        config = json.dumps(guard.CANONICAL_MODAL_CONFIG, indent=2)
        (alpha / ".markdownlint-cli2.jsonc").write_text(config, encoding="utf-8")
    _write_lint_yml(alpha, _GOOD_LINT_YML)
    _git("add", "-A", cwd=alpha)
    _git("commit", "-m", "init", cwd=alpha)
    _init_repo(root)
    (root / ".gitmodules").write_text(
        '[submodule "alpha"]\n\tpath = alpha\n\turl = ../skills-alpha.git\n',
        encoding="utf-8",
    )
    _git("add", ".gitmodules", cwd=root)
    return root


def test_evaluate_empty_gitmodules_exits_two(tmp_path):
    root = tmp_path / "umbrella"
    _init_repo(root)
    (root / ".gitmodules").write_text("", encoding="utf-8")
    code, lines = guard.evaluate(root)
    assert code == 2
    assert any("nothing to check" in line for line in lines)


def test_evaluate_clean_repo_exits_zero(tmp_path):
    code, lines = guard.evaluate(_make_umbrella_repo(tmp_path))
    assert code == 0
    assert any(line.startswith("OK:") for line in lines)


def test_evaluate_drifted_repo_exits_one(tmp_path):
    code, lines = guard.evaluate(_make_umbrella_repo(tmp_path, canonical_config=False))
    assert code == 1
    assert any("violations detected" in line for line in lines)


def test_evaluate_discovers_nested_gitmodule_skills(tmp_path):
    root = tmp_path / "umbrella"
    parent = root / "family"
    parent.mkdir(parents=True, exist_ok=True)
    _init_repo(parent)
    canonical = json.dumps(guard.CANONICAL_MODAL_CONFIG, indent=2)
    (parent / ".markdownlint-cli2.jsonc").write_text(canonical, encoding="utf-8")
    _write_lint_yml(parent, _GOOD_LINT_YML)
    _git("add", "-A", cwd=parent)
    _git("commit", "-m", "init", cwd=parent)

    # create the nested skill
    reader = parent / "reader"
    reader.mkdir()
    (reader / "SKILL.md").write_text("# reader\n")
    _git("add", "-A", cwd=parent)
    _git("commit", "-m", "add reader", cwd=parent)

    _init_repo(root)
    (root / ".gitmodules").write_text(
        '[submodule "family"]\n\tpath = family\n\turl = ../skills-family.git\n',
        encoding="utf-8",
    )
    code, lines = guard.evaluate(root)
    assert code == 0
    assert any("OK:" in line for line in lines)


def test_evaluate_includes_extra_root_skills(tmp_path):
    root = tmp_path / "umbrella"
    _init_repo(root)
    (root / ".gitmodules").write_text("", encoding="utf-8")
    extra = tmp_path / "mono"
    skill = extra / "satellites" / "project" / "skills" / "migrated"
    _init_repo(skill)
    canonical = json.dumps(guard.CANONICAL_MODAL_CONFIG, indent=2)
    (skill / ".markdownlint-cli2.jsonc").write_text(canonical, encoding="utf-8")
    _write_lint_yml(skill, _GOOD_LINT_YML)
    _git("add", "-A", cwd=skill)
    _git("commit", "-m", "init", cwd=skill)

    code, lines = guard.evaluate(root, extra_skill_roots=[str(extra)])
    assert code == 0
    assert any("submodules match" in line for line in lines)


def test_main_prints_lines_and_exits_with_evaluate_code(monkeypatch, capsys):
    monkeypatch.setattr(
        guard,
        "evaluate",
        lambda _root, extra_skill_roots=None: (0, ["OK: fine"]),
    )
    with pytest.raises(SystemExit) as excinfo:
        guard.main()
    assert excinfo.value.code == 0
    assert "OK: fine" in capsys.readouterr().out


def test_script_entry_point_runs_the_fleet_guard():
    with pytest.raises(SystemExit) as exit_information:
        runpy.run_path(str(Path(guard.__file__)), run_name="__main__")

    assert exit_information.value.code == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
