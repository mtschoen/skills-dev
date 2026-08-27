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
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.check_config_drift_checks import (
    check_code_without_ci,
    check_em_dash,
    check_lint_workflow,
    check_markdownlint_config,
    check_nested_workflows,
    check_ruff_pin,
    check_submodule,
    resolve_skill_directory,
    tracked_files,
)
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
    "check_nested_workflows",
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
