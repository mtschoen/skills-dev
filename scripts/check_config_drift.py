#!/usr/bin/env python3
"""Guard against per-repo markdownlint/CI config drifting apart across submodules.

Every top-level submodule in this repo is meant to share the same
`.markdownlint-cli2.jsonc` shape and the same CI trigger/timeout shape in
`.github/workflows/lint.yml`, with a small, explicit set of exceptions (real
local noise directories, real rule violations proven by an empirical
`markdownlint-cli2` run). This script encodes that canonical shape plus the
exception table, so an accidental copy-paste drift (or a stray suppression
nobody re-justified) fails CI instead of silently spreading.

This is a drift *guard*, not a linter: it does not run markdownlint or judge
whether a config is a good idea, only whether each repo matches its declared
expected shape (canonical or exception).

Exit codes: 0 = no drift, 1 = drift detected, 2 = nothing to check.

Run from anywhere:  python scripts/check_config_drift.py
"""

import json
import re
import subprocess
import sys
from pathlib import Path

# The shape every modal skill repo's .markdownlint-cli2.jsonc should have
# unless listed in MODAL_CONFIG_EXCEPTIONS below. MD013 (line length) and
# MD060 (table pipe style) are disabled everywhere by choice, uniformly.
CANONICAL_MODAL_CONFIG = {
    "config": {"default": True, "MD013": False, "MD060": False},
    "globs": ["**/*.md"],
    "ignores": ["node_modules"],
}

# Deviations from CANONICAL_MODAL_CONFIG, each proven necessary by a real
# `markdownlint-cli2` failure when the override was removed:
#   - MD041 (first-line-heading): eval scenario briefs open with prose, not a
#     heading, so escalate-over-shortcut, review-in-parallel-pipelines,
#     docs-update, and project-maintenance keep it disabled.
#   - using-a-debugger's ignores list carries ".superpowers", a real local
#     scratch directory that exists in that repo (not gitignored elsewhere).
#
# find-task, fleet-orchestration, and running-spikes used to keep MD033
# (no-inline-html) disabled for bare angle-bracket placeholders like <task>,
# <repo path>, and <component> in their SKILL.md prose. Those placeholders
# were backticked instead of suppressing the rule, so all three are back on
# CANONICAL_MODAL_CONFIG.
MODAL_CONFIG_EXCEPTIONS = {
    "escalate-over-shortcut": {
        "config": {"default": True, "MD013": False, "MD041": False, "MD060": False},
        "globs": ["**/*.md"],
        "ignores": ["node_modules"],
    },
    "review-in-parallel-pipelines": {
        "config": {"default": True, "MD013": False, "MD041": False, "MD060": False},
        "globs": ["**/*.md"],
        "ignores": ["node_modules"],
    },
    "docs-update": {
        "config": {"default": True, "MD013": False, "MD041": False, "MD060": False},
        "globs": ["**/*.md"],
        "ignores": ["node_modules"],
    },
    "project-maintenance": {
        "config": {"default": True, "MD013": False, "MD041": False, "MD060": False},
        "globs": ["**/*.md"],
        "ignores": ["node_modules"],
    },
    "using-a-debugger": {
        "config": {"default": True, "MD013": False, "MD060": False},
        "globs": ["**/*.md"],
        "ignores": ["node_modules", ".superpowers"],
    },
}

# project-lock is not a modal skill repo: it predates the shared config shape
# (no "default": true, its own workspace/.pi-subagents excludes) and keeps
# MD013 + MD041 disabled deliberately (MD041 covers its CLAUDE.md/GEMINI.md
# @AGENTS.md stub files, which never open with a heading).
PROJECT_LOCK_CONFIG = {
    "config": {"MD013": False, "MD041": False},
    "globs": ["**/*.md", "!workspace/**", "!.pi-subagents/**"],
    "ignores": ["node_modules", ".superpowers"],
}

# Directory segments whose tracked files are inert demo/prop content: sample
# projects copied into a scenario's workspace, or fixtures a debugger backend
# points at. They are never executed or linted by the umbrella's own CI, so
# code-without-CI (below) skips them. This is a deliberate contrast with eval
# scenario `seed/` trees: `seed/` code IS executed live during an eval run (an
# agent edits it, a probe script runs against it), so it counts as real code
# and still needs CI coverage - only `workspace/`, `mock_repo/`, and
# `fixtures/` are exempted here, confirmed against the corpus on 2026-08-06
# (smoke-test's evals/fixtures/, using-a-debugger's evals/fixtures/mock_repo/,
# cost-estimator's tests/fixtures/, fast-tests's and pushback's
# workspace/mock_repo/).
FIXTURE_DIR_SEGMENTS = frozenset({"workspace", "mock_repo", "fixtures"})

# The one ruff version every workflow reference across the fleet (umbrella +
# every submodule) must pin, so aislop's format pass, the dedicated ruff job,
# and every submodule's own CI all lint/format identically.
FLEET_RUFF_PIN = "0.15.15"

# The literal UTF-8 bytes for U+2014 EM DASH. Spelled as an escape, not the
# character itself, so this file does not trip its own check. No corpus file
# should contain one (see ~/.claude/notes/feedback_no_em_dashes.md) - swept
# clean 2026-08-05.
EM_DASH_BYTES = "\u2014".encode()

_PATH_LINE = re.compile(r"^\s*path\s*=\s*(.+?)\s*$", re.MULTILINE)

# Textual invariants for .github/workflows/lint.yml, checked without a yaml
# dependency (the umbrella's own CI is Python-stdlib-only for this script).
_MARKDOWNLINT_STEP = re.compile(r"markdownlint", re.IGNORECASE)
_PUSH_BRANCH_MAIN = re.compile(r"push:\s*\n\s*branches:\s*\[main\]")
_PULL_REQUEST_BRANCH_MAIN = re.compile(r"pull_request:\s*\n\s*branches:\s*\[main\]")
_WORKFLOW_DISPATCH = re.compile(r"^\s*workflow_dispatch\s*:", re.MULTILINE)
_TIMEOUT_MINUTES = re.compile(r"^\s*timeout-minutes\s*:", re.MULTILINE)

# code-without-CI: presence checks for a ruff step, a pytest step, and a
# shellcheck step anywhere in a lint.yml (any job, any step - the corpus
# names its python job "python", "test", or "validate" depending on the
# repo, so this checks for the tool invocation, not a fixed job name).
_RUFF_STEP = re.compile(r"\bruff\b")
_PYTEST_STEP = re.compile(r"\bpytest\b")
_SHELLCHECK_STEP = re.compile(r"shellcheck", re.IGNORECASE)

# linter pin: a line only counts as a ruff *install* (and therefore needs the
# fleet pin) if it looks like one - `ruff check`/`ruff format` usage lines
# mention "ruff" too but are not installs and must not be flagged.
_RUFF_INSTALL_LINE = re.compile(r"(pip|pipx)\s+install\b.*\bruff\b|uvx\s+ruff@")
_RUFF_VERSION_REF = re.compile(r"ruff(?:==|@)([^\s'\"]+)")


def strip_jsonc_comments(text):
    """Remove `//` line comments from JSONC text, respecting string literals."""
    result = []
    in_string = False
    escape_next = False
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if in_string:
            result.append(character)
            if escape_next:
                escape_next = False
            elif character == "\\":
                escape_next = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            result.append(character)
            index += 1
            continue
        if character == "/" and index + 1 < length and text[index + 1] == "/":
            while index < length and text[index] != "\n":
                index += 1
            continue
        result.append(character)
        index += 1
    return "".join(result)


def submodule_paths(repo_root: Path):
    """Return the ordered list of submodule paths declared in .gitmodules."""
    gitmodules = repo_root / ".gitmodules"
    return _PATH_LINE.findall(gitmodules.read_text(encoding="utf-8"))


def expected_markdownlint_config(path: str):
    """Return the expected .markdownlint-cli2.jsonc content for *path*."""
    if path == "project-lock":
        return PROJECT_LOCK_CONFIG
    return MODAL_CONFIG_EXCEPTIONS.get(path, CANONICAL_MODAL_CONFIG)


def check_markdownlint_config(repo_root: Path, path: str):
    """Return drift error strings for one submodule's markdownlint config."""
    config_path = repo_root / path / ".markdownlint-cli2.jsonc"
    if not config_path.is_file():
        return [f"{path}: missing .markdownlint-cli2.jsonc"]

    raw = config_path.read_text(encoding="utf-8")
    try:
        actual = json.loads(strip_jsonc_comments(raw))
    except json.JSONDecodeError as error:
        return [
            f"{path}: .markdownlint-cli2.jsonc did not parse as JSON "
            f"after stripping // comments: {error}"
        ]

    expected = expected_markdownlint_config(path)
    if actual != expected:
        return [
            f"{path}: .markdownlint-cli2.jsonc does not match its expected shape\n"
            f"    expected: {json.dumps(expected, sort_keys=True)}\n"
            f"    actual:   {json.dumps(actual, sort_keys=True)}"
        ]
    return []


def check_lint_workflow(repo_root: Path, path: str):
    """Return drift error strings for one submodule's lint.yml CI invariants."""
    workflow_path = repo_root / path / ".github" / "workflows" / "lint.yml"
    if not workflow_path.is_file():
        return [f"{path}: missing .github/workflows/lint.yml"]

    text = workflow_path.read_text(encoding="utf-8")
    errors = []
    if not _MARKDOWNLINT_STEP.search(text):
        errors.append(f"{path}: lint.yml has no markdownlint step")
    if not _PUSH_BRANCH_MAIN.search(text):
        errors.append(f"{path}: lint.yml push trigger is not branch-filtered to main")
    if not _PULL_REQUEST_BRANCH_MAIN.search(text):
        errors.append(
            f"{path}: lint.yml pull_request trigger is not branch-filtered to main"
        )
    if not _WORKFLOW_DISPATCH.search(text):
        errors.append(f"{path}: lint.yml is missing a workflow_dispatch trigger")
    if not _TIMEOUT_MINUTES.search(text):
        errors.append(f"{path}: lint.yml has no timeout-minutes on any job")
    return errors


def is_fixture_path(tracked_path: str) -> bool:
    """Return True if *tracked_path* sits under a FIXTURE_DIR_SEGMENTS directory.

    Only directory segments count, not the filename itself, and the check is
    exact-segment (not substring), so a real directory like `workspaces/` or
    `my_fixtures_helper/` does not accidentally match.
    """
    directories = tracked_path.split("/")[:-1]
    return any(segment in FIXTURE_DIR_SEGMENTS for segment in directories)


def tracked_files(repo_root: Path, path: str):
    """Return the tracked file paths (relative, forward-slash) for one repo.

    *path* is a submodule path, or "" for the umbrella itself. Uses
    `git -C <dir> ls-files` rather than a filesystem walk so gitignored junk
    (__pycache__, node_modules) never counts as "tracked code without CI".
    """
    repo_dir = repo_root / path if path else repo_root
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.splitlines()


def check_code_without_ci(repo_root: Path, path: str):
    """Return drift errors for a submodule's untested/unlinted code.

    Skips repos whose lint.yml is already reported missing by
    check_lint_workflow, to avoid duplicate "missing lint.yml" noise.
    """
    workflow_path = repo_root / path / ".github" / "workflows" / "lint.yml"
    if not workflow_path.is_file():
        return []

    files = tracked_files(repo_root, path)
    py_files = [f for f in files if f.endswith(".py") and not is_fixture_path(f)]
    sh_files = [f for f in files if f.endswith(".sh") and not is_fixture_path(f)]
    if not py_files and not sh_files:
        return []

    text = workflow_path.read_text(encoding="utf-8")
    errors = []
    if py_files and not (_RUFF_STEP.search(text) and _PYTEST_STEP.search(text)):
        errors.append(
            f"{path}: {len(py_files)} tracked .py file(s) outside fixture dirs "
            f"(e.g. {py_files[0]}) but lint.yml has no ruff+pytest step"
        )
    if sh_files and not _SHELLCHECK_STEP.search(text):
        errors.append(
            f"{path}: {len(sh_files)} tracked .sh file(s) outside fixture dirs "
            f"(e.g. {sh_files[0]}) but lint.yml has no shellcheck step"
        )
    return errors


def ruff_pin_errors_in_text(label: str, text: str):
    """Return pin-drift errors for ruff install lines found in *text*.

    Pure text function (no filesystem access) so it is unit-testable without
    a real workflow file. `label` is only used to build the error message.
    """
    errors = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not _RUFF_INSTALL_LINE.search(line):
            continue
        match = _RUFF_VERSION_REF.search(line)
        if match is None:
            errors.append(
                f"{label}:{lineno}: installs ruff without a version pin "
                f"(expected =={FLEET_RUFF_PIN})"
            )
        elif match.group(1) != FLEET_RUFF_PIN:
            errors.append(
                f"{label}:{lineno}: pins ruff to {match.group(1)}, "
                f"fleet pin is {FLEET_RUFF_PIN}"
            )
    return errors


def check_ruff_pin(repo_root: Path, path: str):
    """Return pin-drift errors across every workflow file for one repo."""
    workflows_dir = (
        repo_root / path / ".github" / "workflows"
        if path
        else (repo_root / ".github" / "workflows")
    )
    if not workflows_dir.is_dir():
        return []

    errors = []
    workflow_files = sorted(workflows_dir.glob("*.yml")) + sorted(
        workflows_dir.glob("*.yaml")
    )
    for workflow_file in workflow_files:
        label = f"{path}/{workflow_file.name}" if path else workflow_file.name
        text = workflow_file.read_text(encoding="utf-8")
        errors.extend(ruff_pin_errors_in_text(label, text))
    return errors


def check_em_dash(repo_root: Path, path: str):
    """Return one error per tracked file containing a U+2014 em-dash byte."""
    repo_dir = repo_root / path if path else repo_root
    errors = []
    for relative in tracked_files(repo_root, path):
        file_path = repo_dir / relative
        try:
            data = file_path.read_bytes()
        except OSError:
            continue
        if EM_DASH_BYTES in data:
            label = f"{path}/{relative}" if path else relative
            errors.append(f"{label}: contains an em-dash (U+2014)")
    return errors


def check_submodule(repo_root: Path, path: str):
    """Return every drift error string for one submodule."""
    return (
        check_markdownlint_config(repo_root, path)
        + check_lint_workflow(repo_root, path)
        + check_code_without_ci(repo_root, path)
    )


def evaluate(repo_root: Path):
    """Run the drift check and return (exit_code, output_lines)."""
    paths = submodule_paths(repo_root)
    if not paths:
        return (2, ["no submodules declared in .gitmodules - nothing to check"])

    errors = []
    for path in paths:
        errors.extend(check_submodule(repo_root, path))

    # Pin and em-dash checks span the umbrella too ("" is the umbrella itself).
    for path in [*paths, ""]:
        errors.extend(check_ruff_pin(repo_root, path))
        errors.extend(check_em_dash(repo_root, path))

    if errors:
        return (
            1,
            [
                f"fleet guard violations detected ({len(errors)} issue(s)):",
                *(f"  - {error}" for error in errors),
            ],
        )
    return (
        0,
        [
            f"OK: {len(paths)} submodules match their expected markdownlint/CI shape",
            f"OK: ruff pin ({FLEET_RUFF_PIN}) consistent across {len(paths)} "
            "submodules + umbrella",
            f"OK: no em-dash bytes found across {len(paths)} submodules + umbrella",
        ],
    )


def main():
    repo_root = Path(__file__).resolve().parent.parent
    code, lines = evaluate(repo_root)
    print("\n".join(lines))
    sys.exit(code)


if __name__ == "__main__":
    main()
