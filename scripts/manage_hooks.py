#!/usr/bin/env python3
"""Hook registration and management for skills in the skills-dev umbrella."""

from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.hook_claude import (
    HookEvaluation,
    OfferContext,
    evaluate_destination_hooks,
    find_registered_hook,
    get_claude_settings_path,
    is_command_dangling,
    load_claude_settings,
    prompt_user_for_hook,
    prune_dangling_hooks_in_settings,
    register_hook_in_claude_settings,
    resolve_destinations,
    write_claude_settings,
)
from scripts.hook_definitions import (
    ACTION_STORE_TRUE,
    DECISION_LATER,
    DECISION_NO,
    DECISION_QUIT,
    DECISION_YES,
    DECISIONS_FILE_NAME,
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
    get_decisions_file_path,
    get_hook_script_path,
    load_decisions,
    record_hook_decision,
    save_decisions,
)

__all__ = [
    "ACTION_STORE_TRUE",
    "DECISIONS_FILE_NAME",
    "DECISION_LATER",
    "DECISION_NO",
    "DECISION_QUIT",
    "DECISION_YES",
    "HARNESS_AGENTS",
    "HARNESS_CLAUDE",
    "HARNESS_GEMINI",
    "HARNESS_HERMES",
    "HOOK_DEFINITIONS",
    "MODE_DENY",
    "MODE_WARN",
    "STATUS_DECLINED",
    "STATUS_DEFERRED",
    "STATUS_NOT_INSTALLED",
    "STATUS_REGISTERED",
    "STATUS_UNCONFIGURED",
    "UTF_8",
    "HookDefinition",
    "HookEvaluation",
    "OfferContext",
    "build_hook_command",
    "command_matches_hook",
    "evaluate_destination_hooks",
    "find_registered_hook",
    "get_claude_settings_path",
    "get_decisions_file_path",
    "get_hook_script_path",
    "is_command_dangling",
    "load_claude_settings",
    "load_decisions",
    "main",
    "prompt_user_for_hook",
    "prune_dangling_hooks_in_settings",
    "record_hook_decision",
    "register_hook_in_claude_settings",
    "resolve_destinations",
    "run_hook_management",
    "save_decisions",
    "write_claude_settings",
]


def process_single_hook_offer(
    evaluation: HookEvaluation,
    context: OfferContext,
) -> tuple[bool, bool]:
    """Processes a single hook offer. Returns (settings_modified, should_quit)."""
    defn = evaluation.definition
    hook_path = evaluation.hook_script_path

    if context.assume_yes:
        decision = DECISION_YES
        mode_choice = (
            context.explicit_mode or defn.default_mode if defn.supports_modes else None
        )
    else:
        decision, mode_choice = prompt_user_for_hook(
            defn, hook_path, is_windows=context.is_windows
        )

    if decision == DECISION_QUIT:
        return False, True

    if decision == DECISION_YES:
        cmd_str = build_hook_command(defn, hook_path, is_windows=context.is_windows)
        registered = register_hook_in_claude_settings(
            context.settings_data,
            defn,
            hook_path,
            mode=mode_choice,
            is_windows=context.is_windows,
        )
        if registered:
            mode_info = f" (mode: {mode_choice})" if mode_choice else ""
            prefix = "would register" if context.dry_run else "registered"
            print(f"  {prefix}: {defn.skill_name} ({defn.event}){mode_info}")
            record_hook_decision(
                context.destination_root,
                defn.key,
                DECISION_YES,
                harness=context.harness_name,
                mode=mode_choice,
                command=cmd_str,
                dry_run=context.dry_run,
            )
            return True, False
    elif decision in (DECISION_NO, DECISION_LATER):
        label = "declined" if decision == DECISION_NO else "deferred"
        print(f"  {label}: {defn.skill_name} ({defn.event})")
        record_hook_decision(
            context.destination_root,
            defn.key,
            decision,
            harness=context.harness_name,
            dry_run=context.dry_run,
        )

    return False, False


def run_hook_management(
    destinations: list[tuple[str, Path]],
    selected_skills: set[str] | None = None,
    assume_yes: bool = False,
    dry_run: bool = False,
    check_mode: bool = False,
    prune_mode: bool = False,
    explicit_mode: str | None = None,
    is_windows: bool = False,
) -> int:
    """Executes the hook management flow across destinations. Returns exit code (0 or 1)."""
    drift_found = False

    for harness_name, destination_root in destinations:
        print(f"[{harness_name}] checking hooks at {destination_root}")
        evals, unsupported = evaluate_destination_hooks(
            harness_name, destination_root, selected_skills, is_windows
        )
        if unsupported:
            print(f"  uncovered: {unsupported}")
            continue

        settings_path = get_claude_settings_path(destination_root)
        settings_data = load_claude_settings(settings_path)
        settings_changed = False

        if prune_mode:
            pruned = prune_dangling_hooks_in_settings(settings_data, destination_root)
            for item in pruned:
                print(f"  pruned dangling hook: {item}")
            if pruned:
                settings_changed = True

        context = OfferContext(
            settings_data,
            destination_root,
            harness_name,
            assume_yes,
            dry_run,
            explicit_mode,
            is_windows,
        )

        for evaluation in evals:
            defn = evaluation.definition
            if evaluation.status == STATUS_NOT_INSTALLED:
                continue
            if evaluation.status == STATUS_REGISTERED:
                print(f"  registered: {defn.skill_name} ({defn.event})")
                continue
            if evaluation.status == STATUS_DECLINED:
                print(f"  declined: {defn.skill_name} ({defn.event}) (decision: no)")
                continue

            drift_found = True
            if check_mode:
                print(f"  unregistered: {defn.skill_name} ({defn.event})")
                continue

            modified, should_quit = process_single_hook_offer(evaluation, context)
            if modified:
                settings_changed = True
            if should_quit:
                print("  Aborted by user.")
                if settings_changed and not dry_run:
                    write_claude_settings(settings_path, settings_data)
                return 0

        if settings_changed and not dry_run:
            write_claude_settings(settings_path, settings_data, dry_run=dry_run)
            print("  settings updated.")

    return 1 if (check_mode and drift_found) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect and register hooks for skills across agent harnesses."
    )
    parser.add_argument(
        "-y",
        "--yes",
        dest="assume_yes",
        action=ACTION_STORE_TRUE,
        help="register hooks without interactive prompting",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        dest="dry_run",
        action=ACTION_STORE_TRUE,
        help="preview hook registration without modifying settings",
    )
    parser.add_argument(
        "--check",
        action=ACTION_STORE_TRUE,
        help="check for unregistered hooks (0 clean, 1 unregistered/drift)",
    )
    parser.add_argument(
        "--claude",
        action=ACTION_STORE_TRUE,
        help="target Claude Code (~/.claude/skills)",
    )
    parser.add_argument(
        "--gemini",
        action=ACTION_STORE_TRUE,
        help="target Antigravity (~/.gemini/config/skills)",
    )
    parser.add_argument(
        "--hermes",
        action=ACTION_STORE_TRUE,
        help="target Hermes (<Hermes home>/skills)",
    )
    parser.add_argument(
        "--agents",
        action=ACTION_STORE_TRUE,
        help="target canonical ~/.agents/skills",
    )
    parser.add_argument(
        "--all",
        action=ACTION_STORE_TRUE,
        help="target all known harness destinations",
    )
    parser.add_argument(
        "--prune",
        action=ACTION_STORE_TRUE,
        help="prune dangling hooks pointing to uninstalled skill files",
    )
    parser.add_argument(
        "--mode",
        choices=[MODE_WARN, MODE_DENY],
        help="enforcement mode for project-lock (warn or deny)",
    )
    parser.add_argument(
        "skills",
        nargs="*",
        metavar="skill",
        help="limit to specific skill names (default: all)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    destinations = resolve_destinations(args)
    if not destinations:
        print(
            "No existing skill destinations found on this machine. Pass --claude/--all to target one."
        )
        return 0

    selected = set(args.skills) if args.skills else None
    is_windows = platform.system() == "Windows"

    return run_hook_management(
        destinations=destinations,
        selected_skills=selected,
        assume_yes=args.assume_yes,
        dry_run=args.dry_run,
        check_mode=args.check,
        prune_mode=args.prune,
        explicit_mode=args.mode,
        is_windows=is_windows,
    )


if __name__ == "__main__":
    sys.exit(main())
