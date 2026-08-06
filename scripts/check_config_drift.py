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

_PATH_LINE = re.compile(r"^\s*path\s*=\s*(.+?)\s*$", re.MULTILINE)

# Textual invariants for .github/workflows/lint.yml, checked without a yaml
# dependency (the umbrella's own CI is Python-stdlib-only for this script).
_MARKDOWNLINT_STEP = re.compile(r"markdownlint", re.IGNORECASE)
_PUSH_BRANCH_MAIN = re.compile(r"push:\s*\n\s*branches:\s*\[main\]")
_PULL_REQUEST_BRANCH_MAIN = re.compile(r"pull_request:\s*\n\s*branches:\s*\[main\]")
_WORKFLOW_DISPATCH = re.compile(r"^\s*workflow_dispatch\s*:", re.MULTILINE)
_TIMEOUT_MINUTES = re.compile(r"^\s*timeout-minutes\s*:", re.MULTILINE)


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


def check_submodule(repo_root: Path, path: str):
    """Return every drift error string for one submodule."""
    return check_markdownlint_config(repo_root, path) + check_lint_workflow(
        repo_root, path
    )


def evaluate(repo_root: Path):
    """Run the drift check and return (exit_code, output_lines)."""
    paths = submodule_paths(repo_root)
    if not paths:
        return (2, ["no submodules declared in .gitmodules — nothing to check"])

    errors = []
    for path in paths:
        errors.extend(check_submodule(repo_root, path))

    if errors:
        return (
            1,
            [
                f"config drift detected across submodules ({len(errors)} issue(s)):",
                *(f"  - {error}" for error in errors),
            ],
        )
    return (
        0,
        [f"OK: {len(paths)} submodules match their expected markdownlint/CI shape"],
    )


def main():
    repo_root = Path(__file__).resolve().parent.parent
    code, lines = evaluate(repo_root)
    print("\n".join(lines))
    sys.exit(code)


if __name__ == "__main__":
    main()
