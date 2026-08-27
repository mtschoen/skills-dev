"""Claude Code settings configuration and hook status evaluation."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.hook_definitions import (
    DECISION_LATER,
    DECISION_NO,
    DECISION_QUIT,
    DECISION_YES,
    HARNESS_AGENTS,
    HARNESS_CLAUDE,
    HARNESS_GEMINI,
    HARNESS_HERMES,
    HOOK_DEFINITIONS,
    MODE_DENY,
    MODE_WARN,
    STATUS_DECLINED,
    STATUS_DEFERRED,
    STATUS_NOT_INSTALLED,
    STATUS_REGISTERED,
    STATUS_UNCONFIGURED,
    UTF_8,
    HookDefinition,
    build_hook_command,
    command_matches_hook,
    get_hook_script_path,
    load_decisions,
)


@dataclass
class HookEvaluation:
    definition: HookDefinition
    harness: str
    destination_root: Path
    hook_script_path: Path
    status: str
    registered_command: str | None = None
    recorded_decision: str | None = None
    recorded_mode: str | None = None


@dataclass
class OfferContext:
    settings_data: dict[str, Any]
    destination_root: Path
    harness_name: str
    assume_yes: bool
    dry_run: bool
    explicit_mode: str | None
    is_windows: bool


def get_claude_settings_path(destination_root: Path) -> Path:
    return destination_root.parent / "settings.json"


def load_claude_settings(settings_path: Path) -> dict[str, Any]:
    if not settings_path.exists():
        return {}
    try:
        content = settings_path.read_text(encoding=UTF_8).strip()
        if not content:
            return {}
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Could not parse Claude settings file at {settings_path}: {exc}"
        ) from exc


def write_claude_settings(
    settings_path: Path, settings_data: dict[str, Any], dry_run: bool = False
) -> None:
    if dry_run:
        return
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    if settings_path.exists():
        backup_path = settings_path.with_suffix(".json.bak")
        with contextlib.suppress(OSError):
            shutil.copy2(settings_path, backup_path)
    temp_file = settings_path.parent / f"settings.tmp.{os.getpid()}"
    temp_file.write_text(json.dumps(settings_data, indent=2) + "\n", encoding=UTF_8)
    temp_file.replace(settings_path)


def find_registered_hook(
    settings_data: dict[str, Any],
    definition: HookDefinition,
    hook_path: Path,
) -> tuple[bool, str | None, dict[str, Any] | None]:
    hooks_section = settings_data.get("hooks", {})
    if not isinstance(hooks_section, dict):
        return False, None, None

    event_entries = hooks_section.get(definition.event, [])
    if not isinstance(event_entries, list):
        return False, None, None

    for entry in event_entries:
        if not isinstance(entry, dict):
            continue
        sub_hooks = entry.get("hooks", [])
        if isinstance(sub_hooks, list):
            for sub in sub_hooks:
                if isinstance(sub, dict):
                    cmd_str = sub.get("command", "")
                    if command_matches_hook(cmd_str, definition, hook_path):
                        return True, cmd_str, entry
        direct_cmd = entry.get("command", "")
        if direct_cmd and command_matches_hook(direct_cmd, definition, hook_path):
            return True, direct_cmd, entry

    return False, None, None


def register_hook_in_claude_settings(
    settings_data: dict[str, Any],
    definition: HookDefinition,
    hook_path: Path,
    mode: str | None = None,
    is_windows: bool = False,
) -> bool:
    is_registered, _, _ = find_registered_hook(settings_data, definition, hook_path)
    if is_registered:
        if definition.supports_modes and mode:
            env_dict = settings_data.setdefault("env", {})
            if isinstance(env_dict, dict):
                env_dict["PROJECT_LOCK_ENFORCE"] = mode
        return False

    if "hooks" in settings_data and not isinstance(settings_data["hooks"], dict):
        return False

    hooks_section = settings_data.setdefault("hooks", {})

    if definition.event in hooks_section and not isinstance(
        hooks_section[definition.event], list
    ):
        return False

    event_list = hooks_section.setdefault(definition.event, [])

    cmd_str = build_hook_command(definition, hook_path, is_windows=is_windows)
    new_entry: dict[str, Any] = {"hooks": [{"type": "command", "command": cmd_str}]}
    if definition.matcher is not None:
        new_entry["matcher"] = definition.matcher

    event_list.append(new_entry)

    if definition.supports_modes and mode:
        env_dict = settings_data.setdefault("env", {})
        if isinstance(env_dict, dict):
            env_dict["PROJECT_LOCK_ENFORCE"] = mode

    return True


def is_command_dangling(command_str: str, destination_root: Path) -> bool:
    """Returns True if command points to a missing hook script under destination_root."""
    for definition in HOOK_DEFINITIONS:
        posix_rel = definition.script_relative_path_posix.replace("\\", "/")
        skill_posix = f"{definition.skill_name}/{posix_rel}"
        if skill_posix in command_str.replace("\\", "/"):
            target_script = (
                destination_root
                / definition.skill_name
                / definition.script_relative_path_posix
            )
            if not target_script.exists():
                return True
    return False


def prune_dangling_hooks_in_settings(
    settings_data: dict[str, Any],
    destination_root: Path,
) -> list[str]:
    pruned_descriptions: list[str] = []
    hooks_section = settings_data.get("hooks", {})
    if not isinstance(hooks_section, dict):
        return pruned_descriptions

    for event_name, event_entries in list(hooks_section.items()):
        if not isinstance(event_entries, list):
            continue
        surviving_entries: list[Any] = []
        for entry in event_entries:
            if not isinstance(entry, dict):
                surviving_entries.append(entry)
                continue

            sub_hooks = entry.get("hooks")
            if isinstance(sub_hooks, list):
                surviving_sub_hooks: list[Any] = []
                for sub in sub_hooks:
                    cmd_str = sub.get("command", "") if isinstance(sub, dict) else ""
                    if cmd_str and is_command_dangling(cmd_str, destination_root):
                        pruned_descriptions.append(f"{event_name}: {cmd_str}")
                    else:
                        surviving_sub_hooks.append(sub)
                if surviving_sub_hooks:
                    entry["hooks"] = surviving_sub_hooks
                    surviving_entries.append(entry)
            elif "command" in entry:
                cmd_str = entry.get("command", "")
                if (
                    isinstance(cmd_str, str)
                    and cmd_str
                    and is_command_dangling(cmd_str, destination_root)
                ):
                    pruned_descriptions.append(f"{event_name}: {cmd_str}")
                else:
                    surviving_entries.append(entry)
            else:
                surviving_entries.append(entry)

        hooks_section[event_name] = surviving_entries

    return pruned_descriptions


def evaluate_destination_hooks(
    harness: str,
    destination_root: Path,
    selected_skills: set[str] | None = None,
    is_windows: bool = False,
) -> tuple[list[HookEvaluation], str | None]:
    """Evaluates hook status for a destination harness. Returns (evaluations, unsupported_reason)."""
    if harness != HARNESS_CLAUDE:
        unsupported = {
            HARNESS_GEMINI: (
                "Antigravity does not support command-based hook events"
                " (PreToolUse/PostToolUse/UserPromptSubmit/SessionEnd)."
            ),
            HARNESS_HERMES: "Hermes does not support command-based hook events.",
            HARNESS_AGENTS: (
                "Canonical ~/.agents/skills is a shared skills repository,"
                " not an agent runtime with hook settings."
            ),
        }
        return [], unsupported.get(
            harness,
            f"Harness '{harness}' does not have a supported hook configuration format.",
        )

    settings_path = get_claude_settings_path(destination_root)
    settings_data = load_claude_settings(settings_path)
    decisions = load_decisions(destination_root)
    evaluations: list[HookEvaluation] = []

    for defn in HOOK_DEFINITIONS:
        if selected_skills and defn.skill_name not in selected_skills:
            continue
        skill_dir = destination_root / defn.skill_name
        hook_path = get_hook_script_path(destination_root, defn, is_windows)
        if not (skill_dir / "SKILL.md").exists() or not hook_path.exists():
            evaluations.append(
                HookEvaluation(
                    defn, harness, destination_root, hook_path, STATUS_NOT_INSTALLED
                )
            )
            continue

        is_reg, reg_cmd, _ = find_registered_hook(settings_data, defn, hook_path)
        dec_entry = decisions.get(defn.key, {})
        rec_dec = dec_entry.get("decision") if isinstance(dec_entry, dict) else None
        rec_mode = dec_entry.get("mode") if isinstance(dec_entry, dict) else None

        if is_reg:
            status = STATUS_REGISTERED
        elif rec_dec == DECISION_NO:
            status = STATUS_DECLINED
        elif rec_dec == DECISION_LATER:
            status = STATUS_DEFERRED
        else:
            status = STATUS_UNCONFIGURED

        evaluations.append(
            HookEvaluation(
                defn,
                harness,
                destination_root,
                hook_path,
                status,
                reg_cmd,
                rec_dec,
                rec_mode,
            )
        )

    return evaluations, None


def prompt_user_for_hook(
    defn: HookDefinition, hook_path: Path, is_windows: bool = False
) -> tuple[str, str | None]:
    cmd_preview = build_hook_command(defn, hook_path, is_windows=is_windows)
    print(f"\nHook available for {defn.skill_name}:")
    print(f"  Event:       {defn.event}")
    if defn.matcher:
        print(f"  Matcher:     {defn.matcher}")
    print(f"  Command:     {cmd_preview}")
    print(f"  Description: {defn.description}")

    if defn.supports_modes:
        print(
            "  Enforcement: 'deny' blocks unlocked writes across projects."
            " 'warn' logs advisory notices."
        )
        prompt_text = f"Register {defn.event} hook for {defn.skill_name}? [w=warn (recommended) / d=deny / n=no / l=later / q=quit]: "
        try:
            choice = input(prompt_text).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return DECISION_QUIT, None

        if choice in ("w", "warn", "y", "yes", ""):
            return DECISION_YES, MODE_WARN
        if choice in ("d", "deny"):
            return DECISION_YES, MODE_DENY
        if choice in ("n", "no"):
            return DECISION_NO, None
        if choice in ("l", "later"):
            return DECISION_LATER, None
        if choice in ("q", "quit"):
            return DECISION_QUIT, None
        print(f"  Unrecognized choice '{choice}'; recording as later.")
        return DECISION_LATER, None

    prompt_text = f"Register {defn.event} hook for {defn.skill_name}? [y=yes / n=no / l=later / q=quit]: "
    try:
        choice = input(prompt_text).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return DECISION_QUIT, None

    if choice in ("y", "yes", ""):
        return DECISION_YES, None
    if choice in ("n", "no"):
        return DECISION_NO, None
    if choice in ("l", "later"):
        return DECISION_LATER, None
    if choice in ("q", "quit"):
        return DECISION_QUIT, None
    print(f"  Unrecognized choice '{choice}'; recording as later.")
    return DECISION_LATER, None


def resolve_destinations(args: argparse.Namespace) -> list[tuple[str, Path]]:
    destinations: list[tuple[str, Path]] = []
    user_home = Path.home()
    hermes_env = os.environ.get("HERMES_HOME")
    if hermes_env:
        hermes_dir = Path(hermes_env)
    elif platform.system() == "Windows" and os.environ.get("LOCALAPPDATA"):
        hermes_dir = Path(os.environ["LOCALAPPDATA"]) / "hermes"
    else:
        hermes_dir = user_home / ".hermes"

    explicit = args.claude or args.gemini or args.hermes or args.agents or args.all
    if args.claude or args.all:
        destinations.append((HARNESS_CLAUDE, user_home / ".claude" / "skills"))
    if args.gemini or args.all:
        destinations.append(
            (HARNESS_GEMINI, user_home / ".gemini" / "config" / "skills")
        )
    if args.hermes or args.all:
        destinations.append((HARNESS_HERMES, hermes_dir / "skills"))
    if args.agents or args.all:
        destinations.append((HARNESS_AGENTS, user_home / ".agents" / "skills"))

    if not explicit:
        candidates = [
            (HARNESS_CLAUDE, user_home / ".claude" / "skills"),
            (HARNESS_GEMINI, user_home / ".gemini" / "config" / "skills"),
            (HARNESS_HERMES, hermes_dir / "skills"),
            (HARNESS_AGENTS, user_home / ".agents" / "skills"),
        ]
        for name, path in candidates:
            if path.parent.exists():
                destinations.append((name, path))

    return destinations
