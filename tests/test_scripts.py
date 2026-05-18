"""Tests for scripts/push-all.sh and scripts/pull-all.sh.

These tests use real git repositories to verify the submodule traversal
and argument parsing logic.
"""

import subprocess
import pytest

from .conftest import run_push_script, run_pull_script, tmp_git_repo


def _bare_git_init(path):
    """Initialize a bare git repo at *path*."""
    subprocess.run(["git", "init", "--bare", str(path)], check=True,
                   capture_output=True)


def _git_init(path):
    """Initialize a git repo at *path*, add a commit, and create main branch."""
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email",
                    "test@example.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name",
                    "Test"], check=True, capture_output=True)
    # Create initial commit
    (path / "initial.txt").write_text("initial\n")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "init"],
                   check=True, capture_output=True)
    # Rename branch to main (standard for this repo)
    subprocess.run(["git", "-C", str(path), "branch", "-M", "main"],
                   check=True, capture_output=True)


def _git_add_remote(path, name, url):
    """Add a git remote to the repo at *path*."""
    subprocess.run(["git", "-C", str(path), "remote", "add", name, str(url)],
                   check=True, capture_output=True)


class TestPushAllHelpAndUsage:
    """Test --help and unknown argument handling for push-all.sh."""

    def test_help_flag_exits_zero(self, tmp_repo):
        result = run_push_script(tmp_repo, "--help")
        assert result.returncode == 0
        assert "push-all.sh" in result.stdout

    def test_short_help_flag_exits_zero(self, tmp_repo):
        result = run_push_script(tmp_repo, "-h")
        assert result.returncode == 0

    def test_unknown_argument_exits_two(self, tmp_repo):
        result = run_push_script(tmp_repo, "--bogus")
        assert result.returncode == 2
        assert "unknown argument" in result.stderr

    def test_remote_flag_without_value_exits_two(self, tmp_repo):
        result = run_push_script(tmp_repo, "--remote")
        assert result.returncode == 2
        assert "requires a value" in result.stderr

    def test_remote_flag_usage_in_help(self, tmp_repo):
        result = run_push_script(tmp_repo, "--help")
        assert "--remote" in result.stdout


class TestPullAllHelpAndUsage:
    """Test --help and unknown argument handling for pull-all.sh."""

    def test_help_flag_exits_zero(self, tmp_repo):
        result = run_pull_script(tmp_repo, "--help")
        assert result.returncode == 0
        assert "pull-all.sh" in result.stdout

    def test_short_help_flag_exits_zero(self, tmp_repo):
        result = run_pull_script(tmp_repo, "-h")
        assert result.returncode == 0

    def test_unknown_argument_exits_two(self, tmp_repo):
        result = run_pull_script(tmp_repo, "--bogus")
        assert result.returncode == 2
        assert "unknown argument" in result.stderr

    def test_remote_flag_without_value_exits_two(self, tmp_repo):
        result = run_pull_script(tmp_repo, "--remote")
        assert result.returncode == 2
        assert "requires a value" in result.stderr


class TestPushAllSubmoduleTraversal:
    """Test that push-all.sh correctly discovers and iterates submodules."""

    def test_push_all_no_submodules(self, tmp_git_repo):
        """With no submodules, push-all.sh should still succeed and list skills-dev."""
        # Create a minimal git repo with no .gitmodules
        _git_init(tmp_git_repo)
        result = run_push_script(tmp_git_repo)
        assert result.returncode == 0
        assert "=== skills-dev (index) ===" in result.stdout

    def test_push_all_with_uninitialized_submodules(self, tmp_git_repo):
        """Uninitialized submodules (no .git) should be skipped."""
        _git_init(tmp_git_repo)

        # Create a .gitmodules file with a path
        (tmp_git_repo / ".gitmodules").write_text(
            '[submodule "mock-sub"]\n\tpath = mock-sub\n\turl = ./mock-sub.git\n'
        )

        # Create the directory but without .git (simulating uninitialized)
        (tmp_git_repo / "mock-sub").mkdir()

        result = run_push_script(tmp_git_repo)
        assert result.returncode == 0
        # The uninitialized submodule should be skipped
        assert "(not initialized, skipping)" in result.stdout


class TestPushAllRemoteFlag:
    """Test --remote flag for push-all.sh."""

    def test_remote_flag_adds_extra_remote(self, tmp_git_repo):
        """--remote flag should add an additional remote to push to."""
        remote_dir = tmp_git_repo / "remote"
        _bare_git_init(remote_dir)

        _git_init(tmp_git_repo)
        _git_add_remote(tmp_git_repo, "origin", str(remote_dir))
        _git_add_remote(tmp_git_repo, "backup", str(remote_dir))

        # Push main to bare repos so rev-list comparison works
        subprocess.run(["git", "-C", str(tmp_git_repo), "push", "origin", "main"],
                       capture_output=True, check=True)
        subprocess.run(["git", "-C", str(tmp_git_repo), "push", "backup", "main"],
                       capture_output=True, check=True)

        result = run_push_script(tmp_git_repo, "--remote", "backup")
        assert result.returncode == 0
        # Should push to both origin and backup
        assert "=== skills-dev (index) ===" in result.stdout
        assert "-> backup" in result.stdout


class TestPushAllWithSubmodules:
    """Test push-all.sh with initialized submodules."""

    def test_push_all_with_initialized_submodule(self, tmp_git_repo):
        """Initialized submodules with .git files should be discovered."""
        main_remote = tmp_git_repo / "main-remote"
        _bare_git_init(main_remote)

        sub_remote = tmp_git_repo / "sub-remote"
        _bare_git_init(sub_remote)

        _git_init(tmp_git_repo)
        _git_add_remote(tmp_git_repo, "origin", str(main_remote))

        # Push main so remote comparison works
        subprocess.run(["git", "-C", str(tmp_git_repo), "push", "origin", "main"],
                       capture_output=True, check=True)

        # Create a .gitmodules file (required for push-all.sh to discover submodules)
        (tmp_git_repo / ".gitmodules").write_text(
            '[submodule "test-sub"]\n\tpath = test-sub\n\turl = ./test-sub.git\n'
        )

        # Create a submodule directory that is itself a real git repo (simulates an
        # initialized submodule where .git is a directory, not a file).
        sub_dir = tmp_git_repo / "test-sub"
        sub_dir.mkdir()
        _git_init(sub_dir)
        _git_add_remote(sub_dir, "origin", str(sub_remote))

        # Push main to the submodule's separate remote so it doesn't conflict
        subprocess.run(["git", "-C", str(sub_dir), "push", "origin", "main"],
                       capture_output=True, check=True)

        result = run_push_script(tmp_git_repo)
        assert result.returncode == 0
        # Should process the submodule
        assert "=== test-sub ===" in result.stdout


class TestPullAllSubmoduleTraversal:
    """Test that pull-all.sh correctly discovers and iterates submodules."""

    def test_pull_all_with_uninitialized_submodules(self, tmp_git_repo):
        """Uninitialized submodules should show 'not initialized' message."""
        _git_init(tmp_git_repo)

        (tmp_git_repo / ".gitmodules").write_text(
            '[submodule "my-sub"]\n\tpath = my-sub\n\turl = ./my-sub.git\n'
        )
        (tmp_git_repo / "my-sub").mkdir()

        result = run_pull_script(tmp_git_repo)
        assert result.returncode == 0
        assert "(not initialized, skipping)" in result.stdout


class TestPullAllRemoteFlag:
    """Test --remote flag for pull-all.sh."""

    def test_remote_flag_fetches_from_extra_remote(self, tmp_git_repo):
        """--remote flag should fetch from the extra remote as well."""
        remote_dir = tmp_git_repo / "remote2"
        _bare_git_init(remote_dir)

        _git_init(tmp_git_repo)
        _git_add_remote(tmp_git_repo, "origin", str(remote_dir))
        _git_add_remote(tmp_git_repo, "extra", str(remote_dir))

        result = run_pull_script(tmp_git_repo, "--remote", "extra")
        assert result.returncode == 0


class TestScriptsWorkFromRepoRoot:
    """Test that scripts work correctly when run from repo root."""

    def test_push_all_reads_gitmodules(self, tmp_git_repo):
        """push-all.sh reads .gitmodules to discover submodule paths."""
        _git_init(tmp_git_repo)

        # Create a .gitmodules file
        (tmp_git_repo / ".gitmodules").write_text(
            '[submodule "sub-one"]\n\tpath = sub-one\n\turl = ./sub-one.git\n'
        )

        result = run_push_script(tmp_git_repo)
        assert result.returncode == 0
        assert "skills-dev (index)" in result.stdout

    def test_pull_all_reads_gitmodules(self, tmp_git_repo):
        """pull-all.sh reads .gitmodules to discover submodule paths."""
        _git_init(tmp_git_repo)

        (tmp_git_repo / ".gitmodules").write_text(
            '[submodule "sub-two"]\n\tpath = sub-two\n\turl = ./sub-two.git\n'
        )

        result = run_pull_script(tmp_git_repo)
        assert result.returncode == 0
