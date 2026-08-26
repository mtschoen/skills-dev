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
    expected_markdownlint_config,
    is_fixture_path,
    ruff_pin_errors_in_text,
    strip_jsonc_comments,
)

__all__ = [
    "CANONICAL_MODAL_CONFIG",
    "EM_DASH_BYTES",
    "FIXTURE_DIR_SEGMENTS",
    "FLEET_RUFF_PIN",
    "MODAL_CONFIG_EXCEPTIONS",
    "PROJECT_LOCK_CONFIG",
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
    "resolve_skill_directory",
    "ruff_pin_errors_in_text",
    "strip_jsonc_comments",
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


def check_code_without_ci(repo_root: Path, path):
    """Return drift errors for untested/unlinted code in one repo."""
    skill_dir = resolve_skill_directory(repo_root, path)
    root_workflow_path = skill_dir / ".github" / "workflows" / "lint.yml"
    if not root_workflow_path.is_file():
        return []

    files = tracked_files(repo_root, path)
    py_files = [f for f in files if f.endswith(".py") and not is_fixture_path(f)]
    sh_files = [f for f in files if f.endswith(".sh") and not is_fixture_path(f)]
    if not py_files and not sh_files:
        return []

    # Group files by their applicable lint.yml (either a child directory's lint.yml if present, or the root lint.yml).
    groups = {}
    for f in py_files:
        top_segment = f.split("/")[0] if "/" in f else ""
        child_wf = (
            skill_dir / top_segment / ".github" / "workflows" / "lint.yml"
            if top_segment
            else None
        )
        if child_wf and child_wf.is_file():
            key = (child_wf, f"{path}/{top_segment}" if path else top_segment)
        else:
            key = (root_workflow_path, str(path) if path else "")
        groups.setdefault(key, {"py": [], "sh": []})["py"].append(f)

    for f in sh_files:
        top_segment = f.split("/")[0] if "/" in f else ""
        child_wf = (
            skill_dir / top_segment / ".github" / "workflows" / "lint.yml"
            if top_segment
            else None
        )
        if child_wf and child_wf.is_file():
            key = (child_wf, f"{path}/{top_segment}" if path else top_segment)
        else:
            key = (root_workflow_path, str(path) if path else "")
        groups.setdefault(key, {"py": [], "sh": []})["sh"].append(f)

    errors = []
    for (wf_path, label), file_dict in sorted(
        groups.items(), key=lambda item: item[0][1]
    ):
        text = wf_path.read_text(encoding=_DEFAULT_ENCODING)
        scoped_py = file_dict["py"]
        scoped_sh = file_dict["sh"]
        display_label = label if label else str(path)
        if scoped_py and not (_RUFF_STEP.search(text) and _PYTEST_STEP.search(text)):
            errors.append(
                f"{display_label}: {len(scoped_py)} tracked .py file(s) outside fixture dirs "
                f"(e.g. {scoped_py[0]}) but lint.yml has no ruff+pytest step"
            )
        if scoped_sh and not _SHELLCHECK_STEP.search(text):
            errors.append(
                f"{display_label}: {len(scoped_sh)} tracked .sh file(s) outside fixture dirs "
                f"(e.g. {scoped_sh[0]}) but lint.yml has no shellcheck step"
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
