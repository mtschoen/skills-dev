"""Hook definitions, commands, and decisions storage for manage_hooks."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

UTF_8 = "utf-8"
DECISIONS_FILE_NAME = ".hook-decisions.json"
DECISION_YES = "yes"
DECISION_NO = "no"
DECISION_LATER = "later"
DECISION_QUIT = "quit"

MODE_WARN = "warn"
MODE_DENY = "deny"

INTERPRETER_BASH = "bash"
INTERPRETER_PYTHON = "python"
INTERPRETER_PYTHON3 = "python3"
INTERPRETER_PWSH = "pwsh"

ACTION_STORE_TRUE = "store_true"

HARNESS_CLAUDE = "claude"
HARNESS_GEMINI = "gemini"
HARNESS_HERMES = "hermes"
HARNESS_AGENTS = "agents"

STATUS_REGISTERED = "registered"
STATUS_DECLINED = "declined"
STATUS_DEFERRED = "deferred"
STATUS_UNCONFIGURED = "unconfigured"
STATUS_NOT_INSTALLED = "not_installed"


@dataclass(frozen=True)
class HookDefinition:
    skill_name: str
    hook_name: str
    event: str
    matcher: str | None
    script_relative_path_posix: str
    script_relative_path_windows: str
    interpreter_posix: str
    interpreter_windows: str
    description: str
    supports_modes: bool = False
    default_mode: str | None = None

    @property
    def key(self) -> str:
        return f"{self.skill_name}/{self.hook_name}"


HOOK_DEFINITIONS: tuple[HookDefinition, ...] = (
    HookDefinition(
        skill_name="project-lock",
        hook_name="pre_tool_use",
        event="PreToolUse",
        matcher="Edit|Write|NotebookEdit|Bash",
        script_relative_path_posix="hooks/pre_tool_use.py",
        script_relative_path_windows="hooks/pre_tool_use.py",
        interpreter_posix=INTERPRETER_PYTHON3,
        interpreter_windows=INTERPRETER_PYTHON,
        description="Enforces cooperative project and worktree locks before tool execution (Edit/Write/NotebookEdit/Bash).",
        supports_modes=True,
        default_mode=MODE_WARN,
    ),
    HookDefinition(
        skill_name="progress-beacon",
        hook_name="prompt_reminder",
        event="UserPromptSubmit",
        matcher=None,
        script_relative_path_posix="hooks/prompt-reminder.sh",
        script_relative_path_windows="hooks/prompt-reminder.sh",
        interpreter_posix=INTERPRETER_BASH,
        interpreter_windows=INTERPRETER_BASH,
        description="Injects progress-beacon trigger reminder on each user prompt.",
    ),
    HookDefinition(
        skill_name="progress-beacon",
        hook_name="recency_nudge",
        event="PostToolUse",
        matcher="*",
        script_relative_path_posix="hooks/recency-nudge.sh",
        script_relative_path_windows="hooks/recency-nudge.sh",
        interpreter_posix=INTERPRETER_BASH,
        interpreter_windows=INTERPRETER_BASH,
        description="Nudges when no progress beacon has been emitted recently in active session.",
    ),
    HookDefinition(
        skill_name="research-first",
        hook_name="prompt_reminder",
        event="UserPromptSubmit",
        matcher=None,
        script_relative_path_posix="hooks/prompt-reminder.sh",
        script_relative_path_windows="hooks/prompt-reminder.sh",
        interpreter_posix=INTERPRETER_BASH,
        interpreter_windows=INTERPRETER_BASH,
        description="Injects research-first discipline reminder before decisions.",
    ),
    HookDefinition(
        skill_name="wrap",
        hook_name="session_end_reminder",
        event="SessionEnd",
        matcher=None,
        script_relative_path_posix="hooks/session-end-reminder.sh",
        script_relative_path_windows="hooks/session-end-reminder.ps1",
        interpreter_posix=INTERPRETER_BASH,
        interpreter_windows=INTERPRETER_PWSH,
        description="Prints a wrap-worthy reminder at session end if repository has uncommitted or unpushed changes.",
    ),
)


def get_hook_script_path(
    destination_root: Path, definition: HookDefinition, is_windows: bool = False
) -> Path:
    relative_path = (
        definition.script_relative_path_windows
        if is_windows
        else definition.script_relative_path_posix
    )
    return destination_root / definition.skill_name / relative_path


def build_hook_command(
    definition: HookDefinition, hook_path: Path, is_windows: bool = False
) -> str:
    path_string = str(hook_path)
    if is_windows:
        if definition.interpreter_windows == INTERPRETER_PWSH:
            return f'pwsh -NoProfile -File "{path_string}"'
        if definition.interpreter_windows == INTERPRETER_PYTHON:
            return f'python "{path_string}"'
        return f'bash "{path_string}"'
    if definition.interpreter_posix == INTERPRETER_PYTHON3:
        return f'python3 "{path_string}"'
    return f'bash "{path_string}"'


def command_matches_hook(
    command_string: str, definition: HookDefinition, hook_path: Path
) -> bool:
    if not command_string:
        return False
    posix_relative = definition.script_relative_path_posix.replace("\\", "/")
    windows_relative = definition.script_relative_path_windows.replace("/", "\\")
    skill_posix = f"{definition.skill_name}/{posix_relative}"
    skill_windows = f"{definition.skill_name}\\{windows_relative}"

    cmd_normalized = command_string.replace("\\", "/")
    if skill_posix in cmd_normalized or skill_windows in command_string:
        return True
    if str(hook_path).replace("\\", "/") in cmd_normalized:
        return True
    return str(hook_path) in command_string


def get_decisions_file_path(destination_root: Path) -> Path:
    return destination_root / DECISIONS_FILE_NAME


def load_decisions(destination_root: Path) -> dict[str, Any]:
    decisions_file = get_decisions_file_path(destination_root)
    if not decisions_file.exists():
        return {}
    try:
        data = json.loads(decisions_file.read_text(encoding=UTF_8))
        if isinstance(data, dict):
            decisions = data.get("decisions", {})
            if isinstance(decisions, dict):
                return decisions
    except (OSError, json.JSONDecodeError):
        return {}
    return {}


def save_decisions(
    destination_root: Path, decisions: dict[str, Any], dry_run: bool = False
) -> None:
    if dry_run:
        return
    decisions_file = get_decisions_file_path(destination_root)
    payload = {
        "version": 1,
        "decisions": decisions,
    }
    destination_root.mkdir(parents=True, exist_ok=True)
    temp_file = destination_root / f".hook-decisions.tmp.{os.getpid()}"
    temp_file.write_text(json.dumps(payload, indent=2) + "\n", encoding=UTF_8)
    temp_file.replace(decisions_file)


def record_hook_decision(
    destination_root: Path,
    hook_key: str,
    decision: str,
    harness: str,
    mode: str | None = None,
    command: str | None = None,
    dry_run: bool = False,
) -> None:
    decisions = load_decisions(destination_root)
    now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    entry: dict[str, Any] = {
        "decision": decision,
        "harness": harness,
        "updated_at": now_iso,
    }
    if mode:
        entry["mode"] = mode
    if command:
        entry["command"] = command
    decisions[hook_key] = entry
    save_decisions(destination_root, decisions, dry_run=dry_run)
