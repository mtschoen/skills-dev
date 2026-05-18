"""Tests for install-skills.sh — argument parsing, help, error handling, and dry-run."""

import pytest

from .conftest import run_install_script


class TestInstallSkillsHelpAndUsage:
    """Test --help and -h flag behavior."""

    def test_help_flag_shows_usage_and_exits_zero(self, tmp_repo):
        result = run_install_script(tmp_repo, "--help")
        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert "install-skills.sh" in result.stdout
        assert "-y / --yes" in result.stdout
        assert "-n / --dry-run" in result.stdout
        assert "--claude" in result.stdout
        assert "--pi" in result.stdout
        assert "--all" in result.stdout

    def test_short_help_flag_shows_usage_and_exits_zero(self, tmp_repo):
        result = run_install_script(tmp_repo, "-h")
        assert result.returncode == 0
        assert "Usage:" in result.stdout

    def test_help_output_contains_all_flags(self, tmp_repo):
        result = run_install_script(tmp_repo, "--help")
        for flag in ["-y", "--yes", "-n", "--dry-run", "--claude", "--pi",
                     "--hermes", "--gemini", "--codex", "--all"]:
            assert flag in result.stdout, f"Flag '{flag}' not in help output"


class TestInstallSkillsArgumentErrors:
    """Test unknown argument handling and exit codes."""

    def test_unknown_flag_exits_two(self, tmp_repo):
        result = run_install_script(tmp_repo, "--bogus-flag")
        assert result.returncode == 2
        assert "unknown flag" in result.stderr

    def test_unknown_short_flag_exits_two(self, tmp_repo):
        result = run_install_script(tmp_repo, "-z")
        assert result.returncode == 2
        assert "unknown flag" in result.stderr

    def test_unknown_flag_prints_to_stderr(self, tmp_repo):
        result = run_install_script(tmp_repo, "--not-a-real-flag")
        assert result.returncode == 2
        assert "--not-a-real-flag" in result.stderr


class TestInstallSkillsDryRun:
    """Test dry-run mode (-n / --dry-run)."""

    def test_dry_run_short_flag(self, tmp_repo, tmp_path):
        dest = tmp_path / ".claude" / "skills"
        dest.mkdir(parents=True)
        # Create a mock submodule with .git marker
        skill_dir = tmp_repo / "dry-skill"
        skill_dir.mkdir()
        skill_dir.joinpath(".git").write_text("gitdir: .git\n")
        skill_dir.joinpath("SKILL.md").write_text("# Dry Skill\n")

        # Run with dry-run; set HOME to avoid real destination
        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "-n", "dry-skill", env_override=env_override)
        assert result.returncode == 0
        # Dry-run should show install message but not create the directory
        assert dest.joinpath("dry-skill").exists() is False

    def test_dry_run_long_flag(self, tmp_repo, tmp_path):
        dest = tmp_path / ".claude" / "skills"
        dest.mkdir(parents=True)
        skill_dir = tmp_repo / "dry-long"
        skill_dir.mkdir()
        skill_dir.joinpath(".git").write_text("gitdir: .git\n")
        skill_dir.joinpath("SKILL.md").write_text("# Dry Long\n")

        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "--dry-run", "dry-long", env_override=env_override)
        assert result.returncode == 0
        assert dest.joinpath("dry-long").exists() is False

    def test_dry_run_with_assume_yes(self, tmp_repo, tmp_path):
        dest = tmp_path / ".claude" / "skills"
        dest.mkdir(parents=True)
        skill_dir = tmp_repo / "dry-both"
        skill_dir.mkdir()
        skill_dir.joinpath(".git").write_text("gitdir: .git\n")
        skill_dir.joinpath("SKILL.md").write_text("# Dry Both\n")

        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "-y", "-n", "dry-both", env_override=env_override)
        assert result.returncode == 0


class TestInstallSkillsAssumeYes:
    """Test -y / --yes flag (no tty interaction needed)."""

    def test_yes_flag_short(self, tmp_repo, tmp_path):
        dest = tmp_path / ".claude" / "skills"
        dest.mkdir(parents=True)
        skill_dir = tmp_repo / "yes-skill"
        skill_dir.mkdir()
        skill_dir.joinpath(".git").write_text("gitdir: .git\n")
        skill_dir.joinpath("SKILL.md").write_text("# Yes Skill\n")
        skill_dir.joinpath("content.txt").write_text("hello\n")

        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "-y", "yes-skill", env_override=env_override)
        assert result.returncode == 0
        assert dest.joinpath("yes-skill", "SKILL.md").exists()
        assert dest.joinpath("yes-skill", "content.txt").read_text() == "hello\n"

    def test_yes_flag_long(self, tmp_repo, tmp_path):
        dest = tmp_path / ".claude" / "skills"
        dest.mkdir(parents=True)
        skill_dir = tmp_repo / "yes-long"
        skill_dir.mkdir()
        skill_dir.joinpath(".git").write_text("gitdir: .git\n")
        skill_dir.joinpath("SKILL.md").write_text("# Yes Long\n")

        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "--yes", "yes-long", env_override=env_override)
        assert result.returncode == 0
        assert dest.joinpath("yes-long", "SKILL.md").exists()


class TestInstallSkillsDestinationFlags:
    """Test destination selection flags."""

    def test_claude_flag(self, tmp_repo, tmp_path):
        dest = tmp_path / ".claude" / "skills"
        dest.mkdir(parents=True)
        skill_dir = tmp_repo / "claude-skill"
        skill_dir.mkdir()
        skill_dir.joinpath(".git").write_text("gitdir: .git\n")
        skill_dir.joinpath("SKILL.md").write_text("# Claude Skill\n")

        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "--claude", "-y", "claude-skill",
                                     env_override=env_override)
        assert result.returncode == 0
        assert dest.joinpath("claude-skill", "SKILL.md").exists()

    def test_pi_flag(self, tmp_repo, tmp_path):
        dest = tmp_path / ".pi" / "agent" / "skills"
        dest.mkdir(parents=True)
        skill_dir = tmp_repo / "pi-skill"
        skill_dir.mkdir()
        skill_dir.joinpath(".git").write_text("gitdir: .git\n")
        skill_dir.joinpath("SKILL.md").write_text("# Pi Skill\n")

        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "--pi", "-y", "pi-skill",
                                     env_override=env_override)
        assert result.returncode == 0
        assert dest.joinpath("pi-skill", "SKILL.md").exists()

    def test_hermes_flag(self, tmp_repo, tmp_path):
        dest = tmp_path / ".hermes" / "skills"
        dest.mkdir(parents=True)
        skill_dir = tmp_repo / "hermes-skill"
        skill_dir.mkdir()
        skill_dir.joinpath(".git").write_text("gitdir: .git\n")
        skill_dir.joinpath("SKILL.md").write_text("# Hermes Skill\n")

        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "--hermes", "-y", "hermes-skill",
                                     env_override=env_override)
        assert result.returncode == 0
        assert dest.joinpath("hermes-skill", "SKILL.md").exists()

    def test_gemini_flag(self, tmp_repo, tmp_path):
        dest = tmp_path / ".gemini" / "skills"
        dest.mkdir(parents=True)
        skill_dir = tmp_repo / "gemini-skill"
        skill_dir.mkdir()
        skill_dir.joinpath(".git").write_text("gitdir: .git\n")
        skill_dir.joinpath("SKILL.md").write_text("# Gemini Skill\n")

        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "--gemini", "-y", "gemini-skill",
                                     env_override=env_override)
        assert result.returncode == 0
        assert dest.joinpath("gemini-skill", "SKILL.md").exists()

    def test_codex_flag(self, tmp_repo, tmp_path):
        dest = tmp_path / ".codex" / "skills"
        dest.mkdir(parents=True)
        skill_dir = tmp_repo / "codex-skill"
        skill_dir.mkdir()
        skill_dir.joinpath(".git").write_text("gitdir: .git\n")
        skill_dir.joinpath("SKILL.md").write_text("# Codex Skill\n")

        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "--codex", "-y", "codex-skill",
                                     env_override=env_override)
        assert result.returncode == 0
        assert dest.joinpath("codex-skill", "SKILL.md").exists()


class TestInstallSkillsDefaultBehavior:
    """Test default installation behavior (no flags, all skills)."""

    def test_default_destination_is_claude(self, tmp_repo, tmp_path):
        """Without any --agent flag, default destination is ~/.claude/skills."""
        dest = tmp_path / ".claude" / "skills"
        dest.mkdir(parents=True)
        skill_dir = tmp_repo / "default-skill"
        skill_dir.mkdir()
        skill_dir.joinpath(".git").write_text("gitdir: .git\n")
        skill_dir.joinpath("SKILL.md").write_text("# Default Skill\n")

        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "-y", env_override=env_override)
        assert result.returncode == 0
        assert dest.joinpath("default-skill", "SKILL.md").exists()

    def test_default_installs_all_skills(self, tmp_repo, tmp_path):
        """Without positional args, all skills are installed."""
        dest = tmp_path / ".claude" / "skills"
        dest.mkdir(parents=True)

        for name in ("alpha", "beta", "gamma"):
            skill_dir = tmp_repo / name
            skill_dir.mkdir()
            skill_dir.joinpath(".git").write_text("gitdir: .git\n")
            skill_dir.joinpath("SKILL.md").write_text(f"# {name}\n")

        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "-y", env_override=env_override)
        assert result.returncode == 0
        assert dest.joinpath("alpha", "SKILL.md").exists()
        assert dest.joinpath("beta", "SKILL.md").exists()
        assert dest.joinpath("gamma", "SKILL.md").exists()

    def test_default_skips_non_submodules(self, tmp_repo, tmp_path):
        """Directories without .git are skipped (not submodules)."""
        dest = tmp_path / ".claude" / "skills"
        dest.mkdir(parents=True)

        # Create a submodule (has .git)
        skill_dir = tmp_repo / "real-skill"
        skill_dir.mkdir()
        skill_dir.joinpath(".git").write_text("gitdir: .git\n")
        skill_dir.joinpath("SKILL.md").write_text("# Real\n")

        # Create a non-submodule dir (no .git)
        non_skill = tmp_repo / "not-a-submodule"
        non_skill.mkdir()
        non_skill.joinpath("SKILL.md").write_text("# Not a submodule\n")

        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "-y", env_override=env_override)
        assert result.returncode == 0
        # Real skill should be installed
        assert dest.joinpath("real-skill", "SKILL.md").exists()
        # Non-submodule should NOT be installed
        assert not dest.joinpath("not-a-submodule").exists()

    def test_default_skips_no_content_skills(self, tmp_repo, tmp_path):
        """Skills with neither SKILL.md nor skill-draft/ are skipped."""
        dest = tmp_path / ".claude" / "skills"
        dest.mkdir(parents=True)

        skill_dir = tmp_repo / "no-content"
        skill_dir.mkdir()
        skill_dir.joinpath(".git").write_text("gitdir: .git\n")
        skill_dir.joinpath("README.md").write_text("Just a readme, no SKILL.md.\n")

        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "-y", env_override=env_override)
        assert result.returncode == 0
        assert not dest.joinpath("no-content").exists()


class TestInstallSkillsSelective:
    """Test positional skill name arguments."""

    def test_single_skill_selection(self, tmp_repo, tmp_path):
        """Only specified skill is installed."""
        dest = tmp_path / ".claude" / "skills"
        dest.mkdir(parents=True)

        for name in ("alpha", "beta", "gamma"):
            skill_dir = tmp_repo / name
            skill_dir.mkdir()
            skill_dir.joinpath(".git").write_text("gitdir: .git\n")
            skill_dir.joinpath("SKILL.md").write_text(f"# {name}\n")

        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "-y", "beta", env_override=env_override)
        assert result.returncode == 0
        assert dest.joinpath("beta", "SKILL.md").exists()
        assert not dest.joinpath("alpha").exists()
        assert not dest.joinpath("gamma").exists()

    def test_multiple_skill_selection(self, tmp_repo, tmp_path):
        """Multiple specified skills are installed."""
        dest = tmp_path / ".claude" / "skills"
        dest.mkdir(parents=True)

        for name in ("alpha", "beta", "gamma"):
            skill_dir = tmp_repo / name
            skill_dir.mkdir()
            skill_dir.joinpath(".git").write_text("gitdir: .git\n")
            skill_dir.joinpath("SKILL.md").write_text(f"# {name}\n")

        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "-y", "alpha", "gamma",
                                     env_override=env_override)
        assert result.returncode == 0
        assert dest.joinpath("alpha", "SKILL.md").exists()
        assert not dest.joinpath("beta").exists()
        assert dest.joinpath("gamma", "SKILL.md").exists()


class TestInstallSkillsDraftLayout:
    """Test legacy skill-draft/ layout."""

    def test_draft_layout_installs_from_skill_draft(self, tmp_repo, tmp_path):
        """Skills with skill-draft/ copy content from that subdirectory."""
        dest = tmp_path / ".claude" / "skills"
        dest.mkdir(parents=True)

        skill_dir = tmp_repo / "draft-skill"
        skill_dir.mkdir()
        skill_dir.joinpath(".git").write_text("gitdir: .git\n")
        draft_dir = skill_dir / "skill-draft"
        draft_dir.mkdir()
        draft_dir.joinpath("SKILL.md").write_text("# Draft Skill\n")
        draft_dir.joinpath("extra.txt").write_text("from draft\n")

        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "-y", "draft-skill",
                                     env_override=env_override)
        assert result.returncode == 0
        assert dest.joinpath("draft-skill", "SKILL.md").exists()
        assert dest.joinpath("draft-skill", "extra.txt").exists()

    def test_draft_layout_skips_root_excludes(self, tmp_repo, tmp_path):
        """Draft layout does NOT apply ROOT_EXCLUDES (evals, docs, etc.)."""
        dest = tmp_path / ".claude" / "skills"
        dest.mkdir(parents=True)

        skill_dir = tmp_repo / "draft-excl"
        skill_dir.mkdir()
        skill_dir.joinpath(".git").write_text("gitdir: .git\n")
        draft_dir = skill_dir / "skill-draft"
        draft_dir.mkdir()
        draft_dir.joinpath("SKILL.md").write_text("# Draft\n")
        # These would be excluded for root layout but NOT for draft
        draft_dir.joinpath("evals").mkdir()
        draft_dir.joinpath("evals", "test.md").write_text("eval\n")
        draft_dir.joinpath("docs").mkdir()
        draft_dir.joinpath("docs", "readme.md").write_text("doc\n")

        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "-y", "draft-excl",
                                     env_override=env_override)
        assert result.returncode == 0
        assert dest.joinpath("draft-excl", "evals", "test.md").exists()
        assert dest.joinpath("draft-excl", "docs", "readme.md").exists()


class TestInstallSkillsRootLayoutExclusion:
    """Test file exclusion for root-layout skills."""

    def test_root_layout_excludes_git(self, tmp_repo, tmp_path):
        """ROOT_EXCLUDES should exclude .git, .gitignore, etc."""
        dest = tmp_path / ".claude" / "skills"
        dest.mkdir(parents=True)

        skill_dir = tmp_repo / "root-excl"
        skill_dir.mkdir()
        skill_dir.joinpath(".git").write_text("gitdir: .git\n")
        skill_dir.joinpath("SKILL.md").write_text("# Root\n")
        skill_dir.joinpath(".gitignore").write_text("*.tmp\n")
        skill_dir.joinpath("README.md").write_text("Readme\n")
        skill_dir.joinpath("evals").mkdir()
        skill_dir.joinpath("evals", "test.md").write_text("eval\n")
        # Note: Do NOT create skill-draft/ here — the install script checks for it
        # first and would use draft layout, bypassing the root exclusion logic.

        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "-y", "root-excl",
                                     env_override=env_override)
        assert result.returncode == 0
        installed = dest.joinpath("root-excl")
        assert installed.exists()
        # Should NOT have excluded dirs/files
        assert not installed.joinpath(".git").exists()
        assert not installed.joinpath(".gitignore").exists()
        assert not installed.joinpath("README.md").exists()
        assert not installed.joinpath("evals").exists()
        # Should have the main content
        assert installed.joinpath("SKILL.md").exists()


class TestInstallSkillsOutputMessages:
    """Test stdout messages from the install script."""

    def test_dry_run_shows_install_message(self, tmp_repo, tmp_path):
        """Dry-run should print 'install name -> dest' message."""
        dest = tmp_path / ".claude" / "skills"
        dest.mkdir(parents=True)
        skill_dir = tmp_repo / "msg-skill"
        skill_dir.mkdir()
        skill_dir.joinpath(".git").write_text("gitdir: .git\n")
        skill_dir.joinpath("SKILL.md").write_text("# Msg\n")

        env_override = {"HOME": str(tmp_path)}
        result = run_install_script(tmp_repo, "-n", "msg-skill",
                                     env_override=env_override)
        assert result.returncode == 0
        assert "install msg-skill" in result.stdout

    def test_dry_run_shows_not_installed(self, tmp_repo, tmp_path):
        """Dry-run should not create destination directory."""
        dest = tmp_path / ".claude" / "skills"
        dest.mkdir(parents=True)
        skill_dir = tmp_repo / "not-installed"
        skill_dir.mkdir()
        skill_dir.joinpath(".git").write_text("gitdir: .git\n")
        skill_dir.joinpath("SKILL.md").write_text("# Not Installed\n")

        env_override = {"HOME": str(tmp_path)}
        run_install_script(tmp_repo, "-n", "not-installed",
                           env_override=env_override)
        assert not dest.joinpath("not-installed").exists()

    def test_unknown_flag_message(self, tmp_repo):
        """Unknown flags should produce an error message on stderr."""
        result = run_install_script(tmp_repo, "--fake")
        assert result.returncode == 2
        assert "unknown flag" in result.stderr

    def test_help_output_format(self, tmp_repo):
        """Help output should start with 'Install skills from this repo'."""
        result = run_install_script(tmp_repo, "-h")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "Install skills from this repo into one or more agent config dirs."
