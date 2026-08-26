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

import fnmatch
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
# character itself, so this file does not trip its own check. House style bans
# em-dashes in repo content (AI tell, and cp1252 tooling breakage on Windows);
# the corpus was swept clean 2026-08-05.
EM_DASH_BYTES = "\u2014".encode()

_PATH_LINE = re.compile(r"^\s*path\s*=\s*(.+?)\s*$", re.MULTILINE)

# linter pin: a line only counts as a ruff *install* (and therefore needs the
# fleet pin) if it looks like one - `ruff check`/`ruff format` usage lines
# mention "ruff" too but are not installs and must not be flagged.
_RUFF_INSTALL_LINE = re.compile(r"(pip|pipx)\s+install\b.*\bruff\b|uvx\s+ruff@")
_RUFF_VERSION_REF = re.compile(r"ruff(?:==|@)([^\s'\"]+)")


def strip_jsonc_comments(text: str) -> str:
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


def strip_yaml_comment(line: str) -> str:
    """Strip trailing comment from a YAML line while respecting quoted strings."""
    active_quote = None
    characters = []
    for character_index, character in enumerate(line):
        if active_quote is not None:
            characters.append(character)
            if character == active_quote:
                if character_index > 0 and line[character_index - 1] == "\\":
                    pass
                else:
                    active_quote = None
        else:
            if character in ('"', "'"):
                active_quote = character
                characters.append(character)
            elif character == "#":
                break
            else:
                characters.append(character)
    return "".join(characters).rstrip()


def parse_flow_sequence(text: str):
    """Parse inline flow sequence syntax like `[main]` or `['a', 'b']`."""
    stripped_text = text.strip()
    if stripped_text.startswith("[") and stripped_text.endswith("]"):
        inner_content = stripped_text[1:-1].strip()
        if not inner_content:
            return []
        items = []
        current_item = []
        active_quote = None
        for character_index, character in enumerate(inner_content):
            if active_quote is not None:
                current_item.append(character)
                if character == active_quote and (
                    character_index == 0 or inner_content[character_index - 1] != "\\"
                ):
                    active_quote = None
            elif character in ('"', "'"):
                active_quote = character
                current_item.append(character)
            elif character == ",":
                items.append("".join(current_item).strip())
                current_item = []
            else:
                current_item.append(character)
        if current_item:
            items.append("".join(current_item).strip())
        return [parse_scalar_value(item) for item in items]
    return text


def parse_scalar_value(value: str | None):
    """Parse scalar YAML value into string, integer, float, boolean, or None."""
    if value is None:
        return ""
    stripped_value = value.strip()
    if not stripped_value:
        return ""
    if len(stripped_value) >= 2 and (
        (stripped_value.startswith('"') and stripped_value.endswith('"'))
        or (stripped_value.startswith("'") and stripped_value.endswith("'"))
    ):
        return stripped_value[1:-1]
    if stripped_value.startswith("[") and stripped_value.endswith("]"):
        return parse_flow_sequence(stripped_value)
    lowercased = stripped_value.lower()
    if lowercased == "true":
        return True
    if lowercased == "false":
        return False
    if lowercased in ("null", "~"):
        return None
    try:
        return int(stripped_value)
    except ValueError:
        pass
    try:
        return float(stripped_value)
    except ValueError:
        pass
    return stripped_value


def parse_yaml_document(text: str):
    """Parse a subset of YAML suitable for GitHub Actions workflows into Python dicts."""
    lines = text.splitlines()
    raw_tokens = []
    for line_number, line in enumerate(lines, start=1):
        stripped = strip_yaml_comment(line)
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        raw_tokens.append((indent, stripped.strip(), line_number))

    token_index = 0
    tokens = []
    while token_index < len(raw_tokens):
        indent, content, line_number = raw_tokens[token_index]
        match_block = re.search(r":\s*([|>][+-]?)\s*$", content)
        if match_block:
            block_type = match_block.group(1)
            prefix = content[: match_block.start() + 1]
            scalar_lines = []
            following_index = token_index + 1
            scalar_base_indent = None
            while following_index < len(raw_tokens):
                original_line = lines[raw_tokens[following_index][2] - 1]
                original_indent = len(original_line) - len(original_line.lstrip(" "))
                if original_indent <= indent:
                    break
                if scalar_base_indent is None:
                    scalar_base_indent = original_indent
                stripped_line = (
                    original_line[scalar_base_indent:]
                    if len(original_line) >= scalar_base_indent
                    else original_line.lstrip()
                )
                scalar_lines.append(stripped_line)
                following_index += 1
            if block_type.startswith(">"):
                scalar_value = " ".join(item.strip() for item in scalar_lines)
            else:
                scalar_value = "\n".join(scalar_lines)
            tokens.append((indent, prefix, scalar_value))
            token_index = following_index
        else:
            tokens.append((indent, content, None))
            token_index += 1

    def parse_block(index: int, base_indent: int):
        if index >= len(tokens):
            return None, index

        indent, content, _block_scalar = tokens[index]
        if indent < base_indent:
            return None, index

        if content.startswith("- ") or content == "-":
            result_list = []
            while index < len(tokens):
                indent, content, block_scalar = tokens[index]
                if indent < base_indent:
                    break
                if indent > base_indent and not (
                    content.startswith("- ") or content == "-"
                ):
                    break
                if not (content.startswith("- ") or content == "-"):
                    break

                item_content = "" if content == "-" else content[2:].strip()
                index += 1

                if block_scalar is not None:
                    if ":" in item_content:
                        key, _ = item_content.split(":", 1)
                        sub_dict = {key.strip(): block_scalar}
                        while (
                            index < len(tokens)
                            and tokens[index][0] > indent
                            and not (
                                tokens[index][1].startswith("- ")
                                or tokens[index][1] == "-"
                            )
                        ):
                            sibling_indent, sibling_content, sibling_block = tokens[
                                index
                            ]
                            if ":" in sibling_content:
                                (
                                    sibling_key,
                                    sibling_val,
                                ) = sibling_content.split(":", 1)
                                if sibling_block is not None:
                                    sub_dict[sibling_key.strip()] = sibling_block
                                    index += 1
                                elif not sibling_val.strip():
                                    val, index = parse_block(
                                        index + 1, sibling_indent + 1
                                    )
                                    sub_dict[sibling_key.strip()] = val
                                else:
                                    sub_dict[sibling_key.strip()] = parse_scalar_value(
                                        sibling_val
                                    )
                                    index += 1
                            else:
                                index += 1
                        result_list.append(sub_dict)
                    else:
                        result_list.append(block_scalar)
                elif ":" in item_content:
                    key, value = item_content.split(":", 1)
                    sub_dict = {}
                    if not value.strip():
                        if index < len(tokens) and tokens[index][0] > indent:
                            val, index = parse_block(index, tokens[index][0])
                            sub_dict[key.strip()] = val
                        else:
                            sub_dict[key.strip()] = None
                    else:
                        sub_dict[key.strip()] = parse_scalar_value(value)

                    while (
                        index < len(tokens)
                        and tokens[index][0] > indent
                        and not (
                            tokens[index][1].startswith("- ") or tokens[index][1] == "-"
                        )
                    ):
                        sibling_indent, sibling_content, sibling_block = tokens[index]
                        if ":" in sibling_content:
                            sibling_key, sibling_val = sibling_content.split(":", 1)
                            if sibling_block is not None:
                                sub_dict[sibling_key.strip()] = sibling_block
                                index += 1
                            elif not sibling_val.strip():
                                if (
                                    index + 1 < len(tokens)
                                    and tokens[index + 1][0] > sibling_indent
                                ):
                                    val, index = parse_block(
                                        index + 1, tokens[index + 1][0]
                                    )
                                    sub_dict[sibling_key.strip()] = val
                                else:
                                    sub_dict[sibling_key.strip()] = None
                                    index += 1
                            else:
                                sub_dict[sibling_key.strip()] = parse_scalar_value(
                                    sibling_val
                                )
                                index += 1
                        else:
                            index += 1
                    result_list.append(sub_dict)
                elif not item_content:
                    if index < len(tokens) and tokens[index][0] > indent:
                        val, index = parse_block(index, tokens[index][0])
                        result_list.append(val)
                    else:
                        result_list.append(None)
                else:
                    result_list.append(parse_scalar_value(item_content))
            return result_list, index

        result_dict = {}
        while index < len(tokens):
            indent, content, block_scalar = tokens[index]
            if indent < base_indent:
                break
            if ":" not in content:
                index += 1
                continue
            key, value = content.split(":", 1)
            key = key.strip()
            value = value.strip()
            index += 1
            if block_scalar is not None:
                result_dict[key] = block_scalar
            elif not value:
                if index < len(tokens) and tokens[index][0] > indent:
                    val, index = parse_block(index, tokens[index][0])
                    result_dict[key] = val
                else:
                    result_dict[key] = None
            else:
                result_dict[key] = parse_scalar_value(value)
        return result_dict, index

    document, _ = parse_block(0, 0)
    return document


def normalize_relative_path(path_string: str) -> str:
    """Normalize a relative path string using forward slashes with no leading/trailing dot-slashes."""
    normalized = path_string.replace("\\", "/").strip()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized.endswith("/"):
        normalized = normalized[:-1]
    return normalized


def path_covers_file(target_path: str, candidate_file: str) -> bool:
    """Return True if target_path covers candidate_file."""
    normalized_target = normalize_relative_path(target_path)
    normalized_candidate = normalize_relative_path(candidate_file)

    if not normalized_target or normalized_target == ".":
        return True

    if normalized_candidate == normalized_target or normalized_candidate.startswith(
        normalized_target + "/"
    ):
        return True

    return bool(
        ("*" in normalized_target or "?" in normalized_target)
        and fnmatch.fnmatch(normalized_candidate, normalized_target)
    )


def extract_step_working_directory(
    job_configuration: dict,
    step_configuration: dict,
) -> str:
    """Extract configured working-directory from step or job defaults."""
    if isinstance(step_configuration, dict) and step_configuration.get(
        "working-directory"
    ):
        return str(step_configuration["working-directory"])
    defaults = job_configuration.get("defaults", {})
    if isinstance(defaults, dict):
        run_defaults = defaults.get("run", {})
        if isinstance(run_defaults, dict) and run_defaults.get("working-directory"):
            return str(run_defaults["working-directory"])
    return ""


def step_covers_shellcheck(
    step_configuration: dict,
    working_directory: str,
    shell_files: list[str],
) -> bool:
    """Return True if step invokes shellcheck covering at least one tracked shell file."""
    if not isinstance(step_configuration, dict):
        return False

    uses = str(step_configuration.get("uses") or "")
    if "action-shellcheck" in uses:
        with_block = step_configuration.get("with") or {}
        scandir = (
            str(with_block.get("scandir") or ".")
            if isinstance(with_block, dict)
            else "."
        )
        combined_directory = (
            f"{working_directory}/{scandir}"
            if working_directory and scandir != "."
            else (working_directory if scandir == "." else scandir)
        )
        combined_directory = normalize_relative_path(combined_directory)
        for shell_file in shell_files:
            if path_covers_file(combined_directory, shell_file):
                return True
        return False

    run_command = step_configuration.get("run")
    if run_command and "shellcheck" in str(run_command):
        for line in str(run_command).splitlines():
            stripped_line = line.strip()
            if not stripped_line or stripped_line.startswith("#"):
                continue
            if "shellcheck" in stripped_line:
                tokens = stripped_line.split()
                try:
                    command_index = next(
                        index
                        for index, token in enumerate(tokens)
                        if "shellcheck" in token
                    )
                    arguments = [
                        token
                        for token in tokens[command_index + 1 :]
                        if not token.startswith("-")
                    ]
                    if not arguments:
                        combined_directory = normalize_relative_path(working_directory)
                        for shell_file in shell_files:
                            if path_covers_file(combined_directory, shell_file):
                                return True
                    for argument in arguments:
                        combined_path = (
                            f"{working_directory}/{argument}"
                            if working_directory
                            else argument
                        )
                        combined_path = normalize_relative_path(combined_path)
                        for shell_file in shell_files:
                            if path_covers_file(combined_path, shell_file):
                                return True
                except StopIteration:
                    pass
    return False


def step_covers_ruff(
    step_configuration: dict,
    working_directory: str,
    python_files: list[str],
) -> bool:
    """Return True if step invokes ruff covering at least one tracked python file."""
    if not isinstance(step_configuration, dict):
        return False
    run_command = step_configuration.get("run")
    if not run_command or "ruff" not in str(run_command):
        return False

    for line in str(run_command).splitlines():
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue
        if re.search(r"\bruff\s+(check|format)\b", stripped_line):
            tokens = stripped_line.split()
            try:
                command_index = next(
                    index
                    for index, token in enumerate(tokens)
                    if token in ("check", "format")
                )
                arguments = [
                    token
                    for token in tokens[command_index + 1 :]
                    if not token.startswith("-")
                ]
                if not arguments:
                    combined_directory = normalize_relative_path(working_directory)
                    for python_file in python_files:
                        if path_covers_file(combined_directory, python_file):
                            return True
                for argument in arguments:
                    combined_path = (
                        f"{working_directory}/{argument}"
                        if working_directory
                        else argument
                    )
                    combined_path = normalize_relative_path(combined_path)
                    for python_file in python_files:
                        if path_covers_file(combined_path, python_file):
                            return True
            except StopIteration:
                pass
    return False


def step_covers_pytest(
    step_configuration: dict,
    working_directory: str,
    python_files: list[str],
) -> bool:
    """Return True if step invokes pytest covering at least one tracked python file."""
    if not isinstance(step_configuration, dict):
        return False
    run_command = step_configuration.get("run")
    if not run_command or "pytest" not in str(run_command):
        return False

    for line in str(run_command).splitlines():
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue
        if re.search(r"\bpytest\b", stripped_line):
            tokens = stripped_line.split()
            try:
                command_index = next(
                    index for index, token in enumerate(tokens) if "pytest" in token
                )
                arguments = [
                    token
                    for token in tokens[command_index + 1 :]
                    if not token.startswith("-")
                ]
                if not arguments:
                    combined_directory = normalize_relative_path(working_directory)
                    for python_file in python_files:
                        if path_covers_file(combined_directory, python_file):
                            return True
                for argument in arguments:
                    combined_path = (
                        f"{working_directory}/{argument}"
                        if working_directory
                        else argument
                    )
                    combined_path = normalize_relative_path(combined_path)
                    for python_file in python_files:
                        if path_covers_file(combined_path, python_file):
                            return True
            except StopIteration:
                pass
    return False


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

    raw_text = workflow_path.read_text(encoding="utf-8")
    try:
        parsed_document = parse_yaml_document(raw_text)
    except Exception as error:
        return [f"{path}: lint.yml failed to parse as YAML: {error}"]

    if not isinstance(parsed_document, dict):
        return [f"{path}: lint.yml top-level structure is not a mapping"]

    errors = []

    on_triggers = parsed_document.get("on")
    if not isinstance(on_triggers, dict):
        errors.append(f"{path}: lint.yml push trigger is not branch-filtered to main")
        errors.append(
            f"{path}: lint.yml pull_request trigger is not branch-filtered to main"
        )
        errors.append(f"{path}: lint.yml is missing a workflow_dispatch trigger")
    else:
        push_trigger = on_triggers.get("push")
        if isinstance(push_trigger, dict):
            push_branches = push_trigger.get("branches")
            if push_branches != ["main"] and push_branches != "main":
                errors.append(
                    f"{path}: lint.yml push trigger is not branch-filtered to main"
                )
        else:
            errors.append(
                f"{path}: lint.yml push trigger is not branch-filtered to main"
            )

        pull_request_trigger = on_triggers.get("pull_request")
        if isinstance(pull_request_trigger, dict):
            pull_request_branches = pull_request_trigger.get("branches")
            if pull_request_branches != ["main"] and pull_request_branches != "main":
                errors.append(
                    f"{path}: lint.yml pull_request trigger is not branch-filtered to main"
                )
        else:
            errors.append(
                f"{path}: lint.yml pull_request trigger is not branch-filtered to main"
            )

        if "workflow_dispatch" not in on_triggers:
            errors.append(f"{path}: lint.yml is missing a workflow_dispatch trigger")

    jobs = parsed_document.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        errors.append(f"{path}: lint.yml has no markdownlint step")
        errors.append(f"{path}: lint.yml has no timeout-minutes on any job")
        return errors

    has_markdownlint = False
    has_timeout_minutes = False

    for _job_name, job_data in jobs.items():
        if not isinstance(job_data, dict):
            continue
        if job_data.get("timeout-minutes") is not None:
            has_timeout_minutes = True
        steps = job_data.get("steps")
        if isinstance(steps, list):
            for step in steps:
                if isinstance(step, dict):
                    uses = str(step.get("uses") or "")
                    run_command = str(step.get("run") or "")
                    if (
                        "markdownlint" in uses.lower()
                        or "markdownlint" in run_command.lower()
                    ):
                        has_markdownlint = True

    if not has_markdownlint:
        errors.append(f"{path}: lint.yml has no markdownlint step")
    if not has_timeout_minutes:
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
    python_files = [
        candidate_file
        for candidate_file in files
        if candidate_file.endswith(".py") and not is_fixture_path(candidate_file)
    ]
    shell_files = [
        candidate_file
        for candidate_file in files
        if candidate_file.endswith(".sh") and not is_fixture_path(candidate_file)
    ]
    if not python_files and not shell_files:
        return []

    raw_text = workflow_path.read_text(encoding="utf-8")
    try:
        parsed_document = parse_yaml_document(raw_text)
    except Exception:
        parsed_document = None

    if not isinstance(parsed_document, dict):
        jobs = {}
    else:
        jobs = parsed_document.get("jobs", {})
        if not isinstance(jobs, dict):
            jobs = {}
        if "steps" in parsed_document and isinstance(parsed_document["steps"], list):
            jobs["default_job"] = {"steps": parsed_document["steps"]}

    has_ruff = False
    has_pytest = False
    has_shellcheck = False

    for _job_name, job_data in jobs.items():
        if not isinstance(job_data, dict):
            continue
        steps = job_data.get("steps")
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue
                working_directory = extract_step_working_directory(job_data, step)
                if python_files:
                    if not has_ruff and step_covers_ruff(
                        step, working_directory, python_files
                    ):
                        has_ruff = True
                    if not has_pytest and step_covers_pytest(
                        step, working_directory, python_files
                    ):
                        has_pytest = True
                if (
                    shell_files
                    and not has_shellcheck
                    and step_covers_shellcheck(step, working_directory, shell_files)
                ):
                    has_shellcheck = True

    errors = []
    if python_files and not (has_ruff and has_pytest):
        errors.append(
            f"{path}: {len(python_files)} tracked .py file(s) outside fixture dirs "
            f"(e.g. {python_files[0]}) but lint.yml has no ruff+pytest step"
        )
    if shell_files and not has_shellcheck:
        errors.append(
            f"{path}: {len(shell_files)} tracked .sh file(s) outside fixture dirs "
            f"(e.g. {shell_files[0]}) but lint.yml has no shellcheck step"
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
