"""Tests for the portability guard in scripts/validate_skills.py.

The guard scans every tracked file of each skill repo (and the umbrella's
own files) for references to paths that exist only on the author's
machines. Fixture dirs without git exercise the fallback walk, which
skips only directories git would never track.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from validate_skills import (
    check_portability,
    tracked_files,
    validate_skill,
)


def make_skill(repo_root, name, files):
    """Create a bare on-disk skill dir (no git: exercises the fallback walk)."""
    skill_dir = repo_root / name
    for relative, content in files.items():
        target = skill_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return skill_dir


class TestTrackedFiles:
    def test_walk_includes_dev_files(self, tmp_path):
        skill_dir = make_skill(
            tmp_path,
            "demo",
            {
                "SKILL.md": "# demo\n",
                "README.md": "dev readme\n",
                "evals/case.md": "eval\n",
                "tests/test_x.py": "pass\n",
            },
        )
        names = {f.relative_to(skill_dir).as_posix() for f in tracked_files(skill_dir)}
        assert names == {"SKILL.md", "README.md", "evals/case.md", "tests/test_x.py"}

    def test_walk_skips_generated_directories(self, tmp_path):
        skill_dir = make_skill(
            tmp_path,
            "demo",
            {
                "SKILL.md": "# demo\n",
                "scripts/__pycache__/run.cpython-313.pyc": "junk\n",
                "workspace/transcript.jsonl": "junk\n",
            },
        )
        names = {f.relative_to(skill_dir).as_posix() for f in tracked_files(skill_dir)}
        assert names == {"SKILL.md"}

    def test_git_repo_yields_only_tracked_files(self, tmp_path):
        skill_dir = make_skill(
            tmp_path,
            "demo",
            {"SKILL.md": "# demo\n", "untracked.md": "junk\n"},
        )
        subprocess.run(
            ["git", "init", "-q"], cwd=skill_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "add", "SKILL.md"], cwd=skill_dir, check=True, capture_output=True
        )
        names = {f.relative_to(skill_dir).as_posix() for f in tracked_files(skill_dir)}
        assert names == {"SKILL.md"}


class TestCheckPortability:
    def test_clean_skill_passes(self, tmp_path):
        make_skill(
            tmp_path,
            "demo",
            {
                "SKILL.md": "Read transcripts from ~/.claude/projects/<slug>/.\n",
                "scripts/run.py": "import os\n",
            },
        )
        assert check_portability(tmp_path, "demo") == []

    def test_memory_note_reference_is_flagged(self, tmp_path):
        make_skill(
            tmp_path,
            "demo",
            {"SKILL.md": "See ~/.claude/notes/reference_pricing.md for rates.\n"},
        )
        errors = check_portability(tmp_path, "demo")
        assert len(errors) == 1
        assert "demo/SKILL.md:1" in errors[0]
        assert "user memory note" in errors[0]

    def test_personal_repo_and_home_paths_are_flagged(self, tmp_path):
        make_skill(
            tmp_path,
            "demo",
            {
                "references/setup.md": (
                    "Copy ~/schoen-claude-status/settings.json\n"
                    "or /home/schoen/foo\n"
                    "or C:/Users/mtsch/bar\n"
                    "or Y:\\baz.\n"
                )
            },
        )
        errors = check_portability(tmp_path, "demo")
        assert len(errors) == 4

    def test_repo_name_mention_without_path_is_allowed(self, tmp_path):
        make_skill(
            tmp_path,
            "demo",
            {"README.md": "Seen during schoen-claude-status PR #9.\n"},
        )
        assert check_portability(tmp_path, "demo") == []

    def test_dev_files_are_scanned(self, tmp_path):
        make_skill(
            tmp_path,
            "demo",
            {
                "SKILL.md": "clean\n",
                "README.md": "See ~/.claude/notes/local_only.md\n",
                "evals/seed.md": "See ~/.claude/notes/local_only.md\n",
            },
        )
        assert len(check_portability(tmp_path, "demo")) == 2

    def test_running_spikes_notes_exemption(self, tmp_path):
        make_skill(
            tmp_path,
            "running-spikes",
            {"SKILL.md": "Save the note at ~/.claude/notes/spike_<slug>.md.\n"},
        )
        assert check_portability(tmp_path, "running-spikes") == []

    def test_exemption_is_per_rule_not_blanket(self, tmp_path):
        make_skill(
            tmp_path,
            "running-spikes",
            {"SKILL.md": "Example at C:/Users/mtsch/proj/server.py.\n"},
        )
        errors = check_portability(tmp_path, "running-spikes")
        assert len(errors) == 1
        assert "machine-specific home path" in errors[0]

    def test_checker_and_its_tests_are_file_exempt(self, tmp_path):
        make_skill(
            tmp_path,
            ".",
            {
                "scripts/validate_skills.py": "PATTERN = '~/.claude/notes/x'\n",
                "tests/test_validate_skills.py": "DATA = '/home/schoen/foo'\n",
                "docs/guide.md": "clean\n",
            },
        )
        assert check_portability(tmp_path, ".") == []


class TestValidateSkillIntegration:
    def test_portability_errors_surface_even_when_agentskills_passes(self, tmp_path):
        make_skill(
            tmp_path,
            "demo",
            {"SKILL.md": "See ~/.claude/notes/reference_pricing.md.\n"},
        )
        errors = validate_skill(tmp_path, "demo", runner=lambda _: (0, ""))
        assert len(errors) == 1
        assert "user memory note" in errors[0]

    def test_both_error_sources_combine(self, tmp_path):
        make_skill(
            tmp_path,
            "demo",
            {"SKILL.md": "See ~/.claude/notes/reference_pricing.md.\n"},
        )
        errors = validate_skill(
            tmp_path, "demo", runner=lambda _: (1, "bad frontmatter")
        )
        assert any("bad frontmatter" in e for e in errors)
        assert any("user memory note" in e for e in errors)
