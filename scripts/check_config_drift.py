#!/usr/bin/env python3
"""Guard against per-repo markdownlint/CI config drifting apart across submodules.

Every top-level submodule in this repo is meant to share the same
`.markdownlint-cli2.jsonc` shape and the same CI trigger/timeout shape in
`.github/workflows/lint.yml`, with a small, explicit set of exceptions.
This script encodes that canonical shape plus the exception table, so an
accidental copy-paste drift (or a stray suppression nobody re-justified) fails CI
instead of silently spreading.

This script discovers:

  - `.gitmodules`-backed skills, including submodules that hold skill directories
    one level below the declared path;
  - optional extra roots passed by argument, scanning
    `packages/*/skills/*` and `satellites/*/skills/*` under each root.

It does not run markdownlint or judge rule quality, only whether each repo matches
its expected shape.

Exit codes: 0 = no drift, 1 = drift detected, 2 = nothing to check.

Run from anywhere:  python scripts/check_config_drift.py
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.check_config_drift_rules import (
    _DEFAULT_ENCODING,
    _EXTRA_SKILL_ROOT_GLOBS,
    _MARKDOWNLINT_STEP,
    _PATH_LINE,
    _PULL_REQUEST_BRANCH_MAIN,
    _PUSH_BRANCH_MAIN,
    _PYTEST_STEP,
    _RUFF_INSTALL_LINE,
    _RUFF_STEP,
    _RUFF_VERSION_REF,
    _SCAN_SKIP_DIRECTORIES,
    _SHELLCHECK_STEP,
    _TIMEOUT_MINUTES,
    _WORKFLOW_DISPATCH,
    CANONICAL_MODAL_CONFIG,
    EM_DASH_BYTES,
    FIXTURE_DIR_SEGMENTS,
    FLEET_RUFF_PIN,
    MODAL_CONFIG_EXCEPTIONS,
    PROJECT_LOCK_CONFIG,
    RUFF_SUBCOMMAND_TOKENS,
    expected_markdownlint_config,
    is_fixture_path,
    parse_workflow_yaml,
    path_is_covered,
    ruff_pin_errors_in_text,
    shellcheck_targets,
    strip_jsonc_comments,
    tool_run_targets,
)

__all__ = [
    "CANONICAL_MODAL_CONFIG",
    "EM_DASH_BYTES",
    "FIXTURE_DIR_SEGMENTS",
    "FLEET_RUFF_PIN",
    "MODAL_CONFIG_EXCEPTIONS",
    "PROJECT_LOCK_CONFIG",
    "RUFF_SUBCOMMAND_TOKENS",
    "_DEFAULT_ENCODING",
    "_EXTRA_SKILL_ROOT_GLOBS",
    "_MARKDOWNLINT_STEP",
    "_PATH_LINE",
    "_PULL_REQUEST_BRANCH_MAIN",
    "_PUSH_BRANCH_MAIN",
    "_PYTEST_STEP",
    "_RUFF_INSTALL_LINE",
    "_RUFF_STEP",
    "_RUFF_VERSION_REF",
    "_SCAN_SKIP_DIRECTORIES",
    "_SHELLCHECK_STEP",
    "_TIMEOUT_MINUTES",
    "_WORKFLOW_DISPATCH",
    "check_code_without_ci",
    "check_em_dash",
    "check_lint_workflow",
    "check_markdownlint_config",
    "check_ruff_pin",
    "check_submodule",
    "discover_extra_skill_directories",
    "evaluate",
    "expected_markdownlint_config",
    "is_fixture_path",
    "main",
    "parse_submodule_paths",
    "parse_workflow_yaml",
    "path_is_covered",
    "resolve_skill_directory",
    "ruff_pin_errors_in_text",
    "shellcheck_targets",
    "strip_jsonc_comments",
    "tool_run_targets",
    "tracked_files",
]


def resolve_skill_directory(repo_root: Path, path):
    """Return an absolute directory path from either relative or absolute input."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return repo_root / candidate


def parse_submodule_paths(gitmodules_text: str):
    """Return the ordered list of submodule paths declared in a .gitmodules file."""
    return _PATH_LINE.findall(gitmodules_text)


def discover_extra_skill_directories(root: Path):
    """Yield `(label, directory)` for extra-root skill directories."""
    for pattern in _EXTRA_SKILL_ROOT_GLOBS:
        for candidate in sorted(root.glob(pattern)):
            if not candidate.is_dir() or candidate.name == ".git":
                continue
            try:
                label = candidate.relative_to(root).as_posix()
            except ValueError:
                label = candidate.as_posix()
            yield label, candidate


def tracked_files(repo_root: Path, path):
    """Return tracked file paths for one repository or skill directory."""
    repo_dir = resolve_skill_directory(repo_root, path)
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "ls-files"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.splitlines()
    return [
        str(candidate.relative_to(repo_dir))
        for candidate in sorted(repo_dir.rglob("*"))
        if candidate.is_file()
        and not _SCAN_SKIP_DIRECTORIES.intersection(
            candidate.relative_to(repo_dir).parts
        )
    ]


def check_markdownlint_config(repo_root: Path, path):
    """Return drift error strings for one repo's markdownlint config."""
    skill_dir = resolve_skill_directory(repo_root, path)
    config_path = skill_dir / ".markdownlint-cli2.jsonc"
    label = str(path)
    if not config_path.is_file():
        return [f"{label}: missing .markdownlint-cli2.jsonc"]

    raw = config_path.read_text(encoding=_DEFAULT_ENCODING)
    try:
        actual = json.loads(strip_jsonc_comments(raw))
    except json.JSONDecodeError as error:
        return [
            f"{label}: .markdownlint-cli2.jsonc did not parse as JSON "
            f"after stripping // comments: {error}"
        ]

    expected = expected_markdownlint_config(label)
    if actual != expected:
        return [
            f"{label}: .markdownlint-cli2.jsonc does not match its expected shape\n"
            f"    expected: {json.dumps(expected, sort_keys=True)}\n"
            f"    actual:   {json.dumps(actual, sort_keys=True)}"
        ]
    return []


def check_lint_workflow(repo_root: Path, path):
    """Return drift error strings for one repo's lint.yml CI invariants."""
    skill_dir = resolve_skill_directory(repo_root, path)
    workflow_path = skill_dir / ".github" / "workflows" / "lint.yml"
    label = str(path)
    if not workflow_path.is_file():
        return [f"{label}: missing .github/workflows/lint.yml"]

    text = workflow_path.read_text(encoding=_DEFAULT_ENCODING)
    errors = []
    if not _MARKDOWNLINT_STEP.search(text):
        errors.append(f"{label}: lint.yml has no markdownlint step")
    if not _PUSH_BRANCH_MAIN.search(text):
        errors.append(f"{label}: lint.yml push trigger is not branch-filtered to main")
    if not _PULL_REQUEST_BRANCH_MAIN.search(text):
        errors.append(
            f"{label}: lint.yml pull_request trigger is not branch-filtered to main"
        )
    if not _WORKFLOW_DISPATCH.search(text):
        errors.append(f"{label}: lint.yml is missing a workflow_dispatch trigger")
    if not _TIMEOUT_MINUTES.search(text):
        errors.append(f"{label}: lint.yml has no timeout-minutes on any job")
    return errors


def _route_to_workflow(skill_dir: Path, path, tracked_path: str):
    """Return (workflow_path, group_label, relative_path) for one tracked file.

    `tracked_path` is resolved against the tracked path's own top-level
    directory's lint.yml when one exists one level down (a nested skill with
    its own CI), else against the skill's own root lint.yml.
    `relative_path` is the file's path relative to whichever workflow's
    checkout root applies (with the nested skill's own directory prefix
    stripped off in the nested case, since that workflow checks out that
    directory as its own root).
    """
    top_segment = tracked_path.split("/", 1)[0] if "/" in tracked_path else ""
    child_workflow = (
        skill_dir / top_segment / ".github" / "workflows" / "lint.yml"
        if top_segment
        else None
    )
    if child_workflow and child_workflow.is_file():
        group_label = f"{path}/{top_segment}" if path else top_segment
        relative_path = tracked_path.split("/", 1)[1]
        return child_workflow, group_label, relative_path

    root_workflow = skill_dir / ".github" / "workflows" / "lint.yml"
    group_label = str(path) if path else ""
    return root_workflow, group_label, tracked_path


def check_code_without_ci(repo_root: Path, path):
    """Return drift errors for untested/unlinted code in one repo.

    Beyond checking that a ruff/pytest/shellcheck step merely appears
    somewhere in the applicable lint.yml, this resolves each step's actual
    scope (scandir/path/explicit arguments, resolved against each step's own
    working-directory) against the tracked files it is meant to cover, so a
    step scoped to the wrong directory - the shape of schoen-lab
    skills-dev#36, where `scandir: './hooks'` scanned an empty directory
    while a real `hooks/` lived one level deeper - is caught instead of
    silently passing because the tool's name appears in the file somewhere.

    ruff and shellcheck get this exact-path treatment: both are static
    scanners that only act on files they are literally pointed at, so
    "does a configured target actually reach this file" is a sound check.
    pytest does not get it: a test file commonly targets code that lives
    outside the directory named on the pytest command line (`pytest tests/`
    routinely exercises code under a sibling `src/` or `evals/` via imports),
    so requiring the pytest command to name every covered file's own
    directory would flag that completely idiomatic layout as drift. pytest
    keeps the coarser "does some pytest step exist in the applicable
    lint.yml" bar - which, combined with ruff's precise check, still catches
    the case this guard exists to catch: deleting one skill's entire CI
    block out of a shared lint.yml still leaves that skill's files unscanned
    by ruff, even though other skills' "ruff"/"pytest" text remains in the
    file.
    """
    skill_dir = resolve_skill_directory(repo_root, path)
    root_workflow_path = skill_dir / ".github" / "workflows" / "lint.yml"
    if not root_workflow_path.is_file():
        return []

    files = tracked_files(repo_root, path)
    py_files = [f for f in files if f.endswith(".py") and not is_fixture_path(f)]
    sh_files = [f for f in files if f.endswith(".sh") and not is_fixture_path(f)]
    if not py_files and not sh_files:
        return []

    workflow_cache = {}

    def load_workflow(workflow_path: Path) -> dict:
        if workflow_path not in workflow_cache:
            text = workflow_path.read_text(encoding=_DEFAULT_ENCODING)
            workflow_cache[workflow_path] = parse_workflow_yaml(text)
        return workflow_cache[workflow_path]

    def group(tracked_paths):
        grouped = {}
        for tracked_path in tracked_paths:
            workflow_path, group_label, relative_path = _route_to_workflow(
                skill_dir, path, tracked_path
            )
            grouped.setdefault((workflow_path, group_label), []).append(
                (tracked_path, relative_path)
            )
        return grouped

    errors = []

    for (workflow_path, group_label), scoped_py in sorted(
        group(py_files).items(), key=lambda item: item[0][1]
    ):
        workflow = load_workflow(workflow_path)
        display_label = group_label if group_label else str(path)
        if tool_run_targets(workflow, _PYTEST_STEP) is None:
            errors.append(
                f"{display_label}: {len(scoped_py)} tracked .py file(s) outside fixture dirs "
                f"(e.g. {scoped_py[0][0]}) but lint.yml has no pytest step"
            )
            continue
        ruff_targets = tool_run_targets(
            workflow, _RUFF_STEP, skip_tokens=RUFF_SUBCOMMAND_TOKENS
        )
        if ruff_targets is None:
            errors.append(
                f"{display_label}: {len(scoped_py)} tracked .py file(s) outside fixture dirs "
                f"(e.g. {scoped_py[0][0]}) but lint.yml has no ruff step"
            )
            continue
        uncovered = [
            tracked_path
            for tracked_path, relative_path in scoped_py
            if not path_is_covered(ruff_targets, relative_path)
        ]
        if uncovered:
            errors.append(
                f"{display_label}: {len(uncovered)} tracked .py file(s) outside fixture dirs "
                f"(e.g. {uncovered[0]}) not scanned by any configured ruff step "
                "(lint.yml has a ruff step, but it does not check this path)"
            )

    for (workflow_path, group_label), scoped_sh in sorted(
        group(sh_files).items(), key=lambda item: item[0][1]
    ):
        workflow = load_workflow(workflow_path)
        display_label = group_label if group_label else str(path)
        targets = shellcheck_targets(workflow)
        if targets is None:
            errors.append(
                f"{display_label}: {len(scoped_sh)} tracked .sh file(s) outside fixture dirs "
                f"(e.g. {scoped_sh[0][0]}) but lint.yml has no shellcheck step"
            )
            continue
        uncovered = [
            tracked_path
            for tracked_path, relative_path in scoped_sh
            if not path_is_covered(targets, relative_path)
        ]
        if uncovered:
            errors.append(
                f"{display_label}: {len(uncovered)} tracked .sh file(s) outside fixture dirs "
                f"(e.g. {uncovered[0]}) not covered by any configured shellcheck "
                "scandir/path (lint.yml has a shellcheck step, but it does not scan this file)"
            )
    return errors


def check_ruff_pin(repo_root: Path, path):
    """Return pin-drift errors across all workflow files for one repo."""
    skill_dir = resolve_skill_directory(repo_root, path)
    workflows_dir = (
        skill_dir / ".github" / "workflows"
        if path
        else (repo_root / ".github" / "workflows")
    )

    errors = []
    if workflows_dir.is_dir():
        for workflow_file in sorted(workflows_dir.glob("*.yml")) + sorted(
            workflows_dir.glob("*.yaml")
        ):
            label = f"{path}/{workflow_file.name}" if path else workflow_file.name
            text = workflow_file.read_text(encoding=_DEFAULT_ENCODING)
            errors.extend(ruff_pin_errors_in_text(label, text))

    if path and skill_dir.is_dir():
        for child in sorted(skill_dir.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                child_wf_dir = child / ".github" / "workflows"
                if child_wf_dir.is_dir():
                    for workflow_file in sorted(child_wf_dir.glob("*.yml")) + sorted(
                        child_wf_dir.glob("*.yaml")
                    ):
                        label = f"{path}/{child.name}/{workflow_file.name}"
                        text = workflow_file.read_text(encoding=_DEFAULT_ENCODING)
                        errors.extend(ruff_pin_errors_in_text(label, text))
    return errors


def check_em_dash(repo_root: Path, path):
    """Return one error per tracked file containing a U+2014 em-dash byte."""
    skill_dir = resolve_skill_directory(repo_root, path)
    label_prefix = "" if not path else f"{path}/"
    errors = []
    for relative in tracked_files(repo_root, path):
        file_path = skill_dir / relative
        try:
            data = file_path.read_bytes()
        except OSError:
            continue
        if EM_DASH_BYTES in data:
            errors.append(f"{label_prefix}{relative}: contains an em-dash (U+2014)")
    return errors


def check_submodule(repo_root: Path, path):
    """Return every drift error string for one skill directory."""
    return (
        check_markdownlint_config(repo_root, path)
        + check_lint_workflow(repo_root, path)
        + check_code_without_ci(repo_root, path)
    )


def evaluate(repo_root: Path, extra_skill_roots=None):
    """Run the drift check and return (exit_code, output_lines)."""
    gitmodules = repo_root / ".gitmodules"
    submodules = (
        parse_submodule_paths(gitmodules.read_text(encoding=_DEFAULT_ENCODING))
        if gitmodules.is_file()
        else []
    )

    if not submodules and not extra_skill_roots:
        return (2, ["no submodules declared in .gitmodules - nothing to check"])

    extra_skills = []
    seen = {str((repo_root / p).resolve()) for p in submodules}
    for extra_root in extra_skill_roots or []:
        root_path = Path(extra_root)
        for label, candidate in discover_extra_skill_directories(root_path):
            resolved = str(candidate.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            extra_skills.append((label, candidate))

    errors = []
    # Repo-level configs apply only to submodules
    for path in submodules:
        errors.extend(check_submodule(repo_root, path))

    # File-level checks apply to submodules, umbrella (""), and extra skills
    for path in [*submodules, ""]:
        errors.extend(check_ruff_pin(repo_root, path))
        errors.extend(check_em_dash(repo_root, path))

    for _label, candidate in extra_skills:
        # For extra skills, candidate is an absolute path. We pass candidate.parent as repo_root and candidate.name as path.
        errors.extend(check_ruff_pin(candidate.parent, candidate.name))
        errors.extend(check_em_dash(candidate.parent, candidate.name))

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
            f"OK: {len(submodules)} submodules match their expected markdownlint/CI shape",
            f"OK: ruff pin ({FLEET_RUFF_PIN}) consistent across {len(submodules)} "
            f"submodules + umbrella + {len(extra_skills)} extra roots",
            f"OK: no em-dash bytes found across {len(submodules)} submodules + umbrella + {len(extra_skills)} extra roots",
        ],
    )


def main():
    parser = argparse.ArgumentParser(
        description="Validate skill repository drift expectations."
    )
    parser.add_argument(
        "--extra-skill-root",
        action="append",
        default=[],
        help=(
            "scan an additional repo root for relocated skills under "
            "`packages/*/skills/*` and `satellites/*/skills/*`"
        ),
    )
    args, _ = parser.parse_known_args()
    repo_root = Path(__file__).resolve().parent.parent
    code, lines = evaluate(repo_root, extra_skill_roots=args.extra_skill_root)
    print("\n".join(lines))
    sys.exit(code)


if __name__ == "__main__":
    main()
