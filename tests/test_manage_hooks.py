"""Tests for scripts/manage_hooks.py."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.manage_hooks import (
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
    UTF_8,
    build_hook_command,
    command_matches_hook,
    evaluate_destination_hooks,
    load_claude_settings,
    load_decisions,
    main,
    prompt_user_for_hook,
    prune_dangling_hooks_in_settings,
    record_hook_decision,
    register_hook_in_claude_settings,
    resolve_destinations,
    run_hook_management,
    save_decisions,
    write_claude_settings,
)


def create_installed_skill_fixture(
    skills_dir: Path, skill_name: str, hook_files: list[str]
) -> Path:
    skill_dir = skills_dir / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {skill_name}\ndescription: test\n---\n# {skill_name}\n",
        encoding=UTF_8,
    )
    for hook_file in hook_files:
        hook_path = skill_dir / hook_file
        hook_path.parent.mkdir(parents=True, exist_ok=True)
        hook_path.write_text("#!/usr/bin/env bash\necho hook\n", encoding=UTF_8)
    return skill_dir


class TestHookDefinitions:
    def test_known_hooks_coverage(self):
        skill_names = {defn.skill_name for defn in HOOK_DEFINITIONS}
        assert "project-lock" in skill_names
        assert "progress-beacon" in skill_names
        assert "research-first" in skill_names
        assert "wrap" in skill_names

    def test_hook_keys_unique(self):
        keys = [defn.key for defn in HOOK_DEFINITIONS]
        assert len(keys) == len(set(keys))

    def test_build_hook_command_posix(self, tmp_path):
        defn_python = next(
            d for d in HOOK_DEFINITIONS if d.skill_name == "project-lock"
        )
        cmd_python = build_hook_command(
            defn_python, tmp_path / "pre_tool_use.py", is_windows=False
        )
        assert cmd_python.startswith("python3 ")
        assert "pre_tool_use.py" in cmd_python

        defn_bash = next(
            d for d in HOOK_DEFINITIONS if d.skill_name == "research-first"
        )
        cmd_bash = build_hook_command(
            defn_bash, tmp_path / "prompt-reminder.sh", is_windows=False
        )
        assert cmd_bash.startswith("bash ")

    def test_build_hook_command_windows(self, tmp_path):
        defn_wrap = next(d for d in HOOK_DEFINITIONS if d.skill_name == "wrap")
        cmd_wrap = build_hook_command(
            defn_wrap, tmp_path / "session-end-reminder.ps1", is_windows=True
        )
        assert cmd_wrap.startswith("pwsh -NoProfile -File ")

        defn_python = next(
            d for d in HOOK_DEFINITIONS if d.skill_name == "project-lock"
        )
        cmd_python = build_hook_command(
            defn_python, tmp_path / "pre_tool_use.py", is_windows=True
        )
        assert cmd_python.startswith("python ")

    def test_command_matches_hook(self, tmp_path):
        defn = next(d for d in HOOK_DEFINITIONS if d.skill_name == "project-lock")
        hook_path = tmp_path / "project-lock" / "hooks" / "pre_tool_use.py"

        assert command_matches_hook(
            'python "/path/to/project-lock/hooks/pre_tool_use.py"',
            defn,
            hook_path,
        )
        assert command_matches_hook(
            'python3 "$HOME/.claude/skills/project-lock/hooks/pre_tool_use.py"',
            defn,
            hook_path,
        )
        assert command_matches_hook(
            f'python3 "{hook_path}"',
            defn,
            hook_path,
        )
        assert not command_matches_hook(
            'python "/path/to/unrelated/script.py"',
            defn,
            hook_path,
        )
        assert not command_matches_hook("", defn, hook_path)


class TestDecisionsStorage:
    def test_load_empty_or_missing(self, tmp_path):
        assert load_decisions(tmp_path) == {}

    def test_save_and_load_decisions(self, tmp_path):
        decisions: dict[str, Any] = {
            "project-lock/pre_tool_use": {
                "decision": DECISION_YES,
                "mode": MODE_WARN,
                "harness": HARNESS_CLAUDE,
                "updated_at": "2026-08-26T00:00:00Z",
            }
        }
        save_decisions(tmp_path, decisions)
        loaded = load_decisions(tmp_path)
        assert loaded == decisions
        assert (tmp_path / DECISIONS_FILE_NAME).exists()

    def test_save_decisions_dry_run(self, tmp_path):
        decisions = {"test/hook": {"decision": DECISION_NO}}
        save_decisions(tmp_path, decisions, dry_run=True)
        assert not (tmp_path / DECISIONS_FILE_NAME).exists()

    def test_record_hook_decision(self, tmp_path):
        record_hook_decision(
            destination_root=tmp_path,
            hook_key="research-first/prompt_reminder",
            decision=DECISION_NO,
            harness=HARNESS_CLAUDE,
        )
        loaded = load_decisions(tmp_path)
        assert "research-first/prompt_reminder" in loaded
        assert loaded["research-first/prompt_reminder"]["decision"] == DECISION_NO
        assert "updated_at" in loaded["research-first/prompt_reminder"]


class TestClaudeSettingsManagement:
    def test_load_missing_settings(self, tmp_path):
        settings_file = tmp_path / "settings.json"
        assert load_claude_settings(settings_file) == {}

    def test_load_empty_settings(self, tmp_path):
        settings_file = tmp_path / "settings.json"
        settings_file.write_text("", encoding=UTF_8)
        assert load_claude_settings(settings_file) == {}

    def test_load_invalid_json_raises(self, tmp_path):
        settings_file = tmp_path / "settings.json"
        settings_file.write_text("{ invalid json", encoding=UTF_8)
        with pytest.raises(RuntimeError, match="Could not parse Claude settings"):
            load_claude_settings(settings_file)

    def test_write_settings_creates_backup(self, tmp_path):
        settings_file = tmp_path / "settings.json"
        initial_data = {"existing_key": "value"}
        settings_file.write_text(json.dumps(initial_data), encoding=UTF_8)

        new_data = {"existing_key": "value", "new_key": 123}
        write_claude_settings(settings_file, new_data)

        assert (tmp_path / "settings.json.bak").exists()
        backup_content = json.loads(
            (tmp_path / "settings.json.bak").read_text(encoding=UTF_8)
        )
        assert backup_content == initial_data
        updated_content = json.loads(settings_file.read_text(encoding=UTF_8))
        assert updated_content == new_data

    def test_register_hook_in_empty_settings(self, tmp_path):
        settings_data: dict[str, Any] = {}
        defn = next(d for d in HOOK_DEFINITIONS if d.skill_name == "project-lock")
        hook_path = tmp_path / "project-lock" / "hooks" / "pre_tool_use.py"

        registered = register_hook_in_claude_settings(
            settings_data=settings_data,
            definition=defn,
            hook_path=hook_path,
            mode=MODE_WARN,
        )
        assert registered is True
        assert "hooks" in settings_data
        assert "PreToolUse" in settings_data["hooks"]
        assert len(settings_data["hooks"]["PreToolUse"]) == 1
        entry = settings_data["hooks"]["PreToolUse"][0]
        assert entry.get("matcher") == "Edit|Write|NotebookEdit|Bash"
        assert len(entry.get("hooks", [])) == 1
        assert "pre_tool_use.py" in entry["hooks"][0]["command"]
        assert settings_data.get("env", {}).get("PROJECT_LOCK_ENFORCE") == MODE_WARN

    def test_register_hook_idempotent(self, tmp_path):
        settings_data: dict[str, Any] = {}
        defn = next(d for d in HOOK_DEFINITIONS if d.skill_name == "research-first")
        hook_path = tmp_path / "research-first" / "hooks" / "prompt-reminder.sh"

        first = register_hook_in_claude_settings(
            settings_data=settings_data, definition=defn, hook_path=hook_path
        )
        assert first is True
        assert len(settings_data["hooks"]["UserPromptSubmit"]) == 1

        second = register_hook_in_claude_settings(
            settings_data=settings_data, definition=defn, hook_path=hook_path
        )
        assert second is False
        assert len(settings_data["hooks"]["UserPromptSubmit"]) == 1


class TestPruneDanglingHooks:
    def test_prune_removes_missing_hook_command(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        settings_data: dict[str, Any] = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Edit|Write|NotebookEdit|Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f'python3 "{skills_dir}/project-lock/hooks/pre_tool_use.py"',
                            }
                        ],
                    }
                ],
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": "echo session-start"}]}
                ],
            }
        }

        pruned = prune_dangling_hooks_in_settings(settings_data, skills_dir)
        assert len(pruned) == 1
        assert "PreToolUse" in pruned[0]
        assert len(settings_data["hooks"]["PreToolUse"]) == 0
        assert len(settings_data["hooks"]["SessionStart"]) == 1


class TestEvaluationAndHarnesses:
    def test_unsupported_harnesses(self, tmp_path):
        for harness in (HARNESS_GEMINI, HARNESS_HERMES, HARNESS_AGENTS):
            evals, reason = evaluate_destination_hooks(
                harness=harness, destination_root=tmp_path
            )
            assert evals == []
            assert reason is not None
            assert len(reason) > 0

    def test_evaluate_claude_statuses(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        skills_dir = claude_dir / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        create_installed_skill_fixture(
            skills_dir, "project-lock", ["hooks/pre_tool_use.py"]
        )
        create_installed_skill_fixture(
            skills_dir, "research-first", ["hooks/prompt-reminder.sh"]
        )
        create_installed_skill_fixture(
            skills_dir, "wrap", ["hooks/session-end-reminder.sh"]
        )

        record_hook_decision(
            destination_root=skills_dir,
            hook_key="research-first/prompt_reminder",
            decision=DECISION_NO,
            harness=HARNESS_CLAUDE,
        )
        record_hook_decision(
            destination_root=skills_dir,
            hook_key="wrap/session_end_reminder",
            decision=DECISION_LATER,
            harness=HARNESS_CLAUDE,
        )

        settings_file = claude_dir / "settings.json"
        settings_data = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Edit|Write|NotebookEdit|Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f'python3 "{skills_dir}/project-lock/hooks/pre_tool_use.py"',
                            }
                        ],
                    }
                ]
            }
        }
        settings_file.write_text(json.dumps(settings_data), encoding=UTF_8)

        evals, reason = evaluate_destination_hooks(
            harness=HARNESS_CLAUDE, destination_root=skills_dir
        )
        assert reason is None
        status_by_key = {e.definition.key: e.status for e in evals}
        assert status_by_key.get("project-lock/pre_tool_use") == STATUS_REGISTERED
        assert status_by_key.get("research-first/prompt_reminder") == STATUS_DECLINED
        assert status_by_key.get("wrap/session_end_reminder") == STATUS_DEFERRED
        assert (
            status_by_key.get("progress-beacon/prompt_reminder") == STATUS_NOT_INSTALLED
        )


class TestPromptUser:
    def test_prompt_project_lock_warn(self, monkeypatch, tmp_path):
        defn = next(d for d in HOOK_DEFINITIONS if d.skill_name == "project-lock")
        monkeypatch.setattr("builtins.input", lambda _: "w")
        decision, mode = prompt_user_for_hook(
            defn, tmp_path / "hooks" / "pre_tool_use.py"
        )
        assert decision == DECISION_YES
        assert mode == MODE_WARN

    def test_prompt_project_lock_deny(self, monkeypatch, tmp_path):
        defn = next(d for d in HOOK_DEFINITIONS if d.skill_name == "project-lock")
        monkeypatch.setattr("builtins.input", lambda _: "deny")
        decision, mode = prompt_user_for_hook(
            defn, tmp_path / "hooks" / "pre_tool_use.py"
        )
        assert decision == DECISION_YES
        assert mode == MODE_DENY

    def test_prompt_general_yes(self, monkeypatch, tmp_path):
        defn = next(d for d in HOOK_DEFINITIONS if d.skill_name == "research-first")
        monkeypatch.setattr("builtins.input", lambda _: "y")
        decision, mode = prompt_user_for_hook(
            defn, tmp_path / "hooks" / "prompt-reminder.sh"
        )
        assert decision == DECISION_YES
        assert mode is None

    def test_prompt_no(self, monkeypatch, tmp_path):
        defn = next(d for d in HOOK_DEFINITIONS if d.skill_name == "research-first")
        monkeypatch.setattr("builtins.input", lambda _: "n")
        decision, _ = prompt_user_for_hook(
            defn, tmp_path / "hooks" / "prompt-reminder.sh"
        )
        assert decision == DECISION_NO

    def test_prompt_later(self, monkeypatch, tmp_path):
        defn = next(d for d in HOOK_DEFINITIONS if d.skill_name == "research-first")
        monkeypatch.setattr("builtins.input", lambda _: "l")
        decision, _ = prompt_user_for_hook(
            defn, tmp_path / "hooks" / "prompt-reminder.sh"
        )
        assert decision == DECISION_LATER

    def test_prompt_quit(self, monkeypatch, tmp_path):
        defn = next(d for d in HOOK_DEFINITIONS if d.skill_name == "research-first")
        monkeypatch.setattr("builtins.input", lambda _: "q")
        decision, _ = prompt_user_for_hook(
            defn, tmp_path / "hooks" / "prompt-reminder.sh"
        )
        assert decision == DECISION_QUIT


class TestRunHookManagementFlow:
    def test_check_mode_returns_one_when_unregistered(self, tmp_path):
        claude_skills = tmp_path / ".claude" / "skills"
        create_installed_skill_fixture(
            claude_skills, "project-lock", ["hooks/pre_tool_use.py"]
        )

        exit_code = run_hook_management(
            destinations=[(HARNESS_CLAUDE, claude_skills)],
            check_mode=True,
        )
        assert exit_code == 1

    def test_assume_yes_registers_and_check_passes(self, tmp_path):
        claude_skills = tmp_path / ".claude" / "skills"
        create_installed_skill_fixture(
            claude_skills, "project-lock", ["hooks/pre_tool_use.py"]
        )

        exit_code_apply = run_hook_management(
            destinations=[(HARNESS_CLAUDE, claude_skills)],
            assume_yes=True,
        )
        assert exit_code_apply == 0

        settings_file = tmp_path / ".claude" / "settings.json"
        assert settings_file.exists()
        settings_data = json.loads(settings_file.read_text(encoding=UTF_8))
        assert "PreToolUse" in settings_data.get("hooks", {})
        assert settings_data.get("env", {}).get("PROJECT_LOCK_ENFORCE") == MODE_WARN

        decisions = load_decisions(claude_skills)
        assert (
            decisions.get("project-lock/pre_tool_use", {}).get("decision")
            == DECISION_YES
        )

        exit_code_check = run_hook_management(
            destinations=[(HARNESS_CLAUDE, claude_skills)],
            check_mode=True,
        )
        assert exit_code_check == 0

    def test_dry_run_does_not_modify_settings(self, tmp_path):
        claude_skills = tmp_path / ".claude" / "skills"
        create_installed_skill_fixture(
            claude_skills, "research-first", ["hooks/prompt-reminder.sh"]
        )

        exit_code = run_hook_management(
            destinations=[(HARNESS_CLAUDE, claude_skills)],
            assume_yes=True,
            dry_run=True,
        )
        assert exit_code == 0
        settings_file = tmp_path / ".claude" / "settings.json"
        assert not settings_file.exists()

    def test_selected_skills_filter(self, tmp_path):
        claude_skills = tmp_path / ".claude" / "skills"
        create_installed_skill_fixture(
            claude_skills, "project-lock", ["hooks/pre_tool_use.py"]
        )
        create_installed_skill_fixture(
            claude_skills, "research-first", ["hooks/prompt-reminder.sh"]
        )

        run_hook_management(
            destinations=[(HARNESS_CLAUDE, claude_skills)],
            selected_skills={"research-first"},
            assume_yes=True,
        )

        settings_file = tmp_path / ".claude" / "settings.json"
        settings_data = json.loads(settings_file.read_text(encoding=UTF_8))
        assert "UserPromptSubmit" in settings_data.get("hooks", {})
        assert "PreToolUse" not in settings_data.get("hooks", {})


class TestResolveDestinations:
    def test_explicit_flags(self, tmp_path):
        parser = argparse.ArgumentParser()
        parser.add_argument("--claude", action="store_true")
        parser.add_argument("--gemini", action="store_true")
        parser.add_argument("--hermes", action="store_true")
        parser.add_argument("--agents", action="store_true")
        parser.add_argument("--all", action="store_true")

        args = parser.parse_args(["--all"])
        dests = resolve_destinations(args)
        harness_names = {name for name, _ in dests}
        assert harness_names == {
            HARNESS_CLAUDE,
            HARNESS_GEMINI,
            HARNESS_HERMES,
            HARNESS_AGENTS,
        }

    def test_default_existing_discovery(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / ".claude").mkdir()

        parser = argparse.ArgumentParser()
        parser.add_argument("--claude", action="store_true")
        parser.add_argument("--gemini", action="store_true")
        parser.add_argument("--hermes", action="store_true")
        parser.add_argument("--agents", action="store_true")
        parser.add_argument("--all", action="store_true")

        args = parser.parse_args([])
        dests = resolve_destinations(args)
        assert len(dests) == 1
        assert dests[0][0] == HARNESS_CLAUDE


class TestPromptEdgeCases:
    def test_eof_error(self, monkeypatch, tmp_path):
        defn = next(d for d in HOOK_DEFINITIONS if d.skill_name == "research-first")
        monkeypatch.setattr(
            "builtins.input",
            lambda _: (_ for _ in ()).throw(EOFError()),
        )
        decision, _ = prompt_user_for_hook(
            defn, tmp_path / "hooks" / "prompt-reminder.sh"
        )
        assert decision == DECISION_QUIT

    def test_unrecognized_input_defaults_to_later(self, monkeypatch, tmp_path):
        defn = next(d for d in HOOK_DEFINITIONS if d.skill_name == "research-first")
        monkeypatch.setattr("builtins.input", lambda _: "unknown_input")
        decision, _ = prompt_user_for_hook(
            defn, tmp_path / "hooks" / "prompt-reminder.sh"
        )
        assert decision == DECISION_LATER


class TestInteractiveManagement:
    def test_interactive_no_and_later(self, monkeypatch, tmp_path):
        claude_skills = tmp_path / ".claude" / "skills"
        create_installed_skill_fixture(
            claude_skills, "research-first", ["hooks/prompt-reminder.sh"]
        )

        monkeypatch.setattr("builtins.input", lambda _: "n")
        exit_code = run_hook_management(
            destinations=[(HARNESS_CLAUDE, claude_skills)],
        )
        assert exit_code == 0
        decisions = load_decisions(claude_skills)
        assert (
            decisions.get("research-first/prompt_reminder", {}).get("decision")
            == DECISION_NO
        )

    def test_interactive_quit(self, monkeypatch, tmp_path):
        claude_skills = tmp_path / ".claude" / "skills"
        create_installed_skill_fixture(
            claude_skills, "research-first", ["hooks/prompt-reminder.sh"]
        )

        monkeypatch.setattr("builtins.input", lambda _: "q")
        exit_code = run_hook_management(
            destinations=[(HARNESS_CLAUDE, claude_skills)],
        )
        assert exit_code == 0

    def test_prune_mode_in_run_hook_management(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_skills = claude_dir / "skills"
        claude_skills.mkdir(parents=True, exist_ok=True)

        settings_file = claude_dir / "settings.json"
        settings_data = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Edit|Write|NotebookEdit|Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f'python3 "{claude_skills}/project-lock/hooks/pre_tool_use.py"',
                            }
                        ],
                    }
                ]
            }
        }
        settings_file.write_text(json.dumps(settings_data), encoding=UTF_8)

        exit_code = run_hook_management(
            destinations=[(HARNESS_CLAUDE, claude_skills)],
            prune_mode=True,
        )
        assert exit_code == 0
        updated_settings = json.loads(settings_file.read_text(encoding=UTF_8))
        assert len(updated_settings["hooks"]["PreToolUse"]) == 0


class TestMainCli:
    def test_main_with_claude_flag(self, monkeypatch, tmp_path):
        claude_skills = tmp_path / ".claude" / "skills"
        create_installed_skill_fixture(
            claude_skills, "research-first", ["hooks/prompt-reminder.sh"]
        )
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(
            sys, "argv", ["manage_hooks.py", "--claude", "-y", "research-first"]
        )

        exit_code = main()
        assert exit_code == 0
        settings_file = tmp_path / ".claude" / "settings.json"
        assert settings_file.exists()

    def test_main_no_destinations(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(sys, "argv", ["manage_hooks.py"])
        assert main() == 0
