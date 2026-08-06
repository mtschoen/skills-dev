"""Shared pytest fixtures for skills-dev shell script tests."""

import os
import pathlib
import subprocess

import pytest

# Path to the repository root (where the scripts live)
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Shell scripts to test
INSTALL_SKILLS_SH = REPO_ROOT / "install-skills.sh"
PUSH_ALL_SH = REPO_ROOT / "scripts" / "push-all.sh"
PULL_ALL_SH = REPO_ROOT / "scripts" / "pull-all.sh"


@pytest.fixture()
def tmp_repo(tmp_path):
    """Create a temporary directory that mimics the skills-dev repo structure.

    Returns a Path to the repo root with:
      - install-skills.sh at the root
      - scripts/push-all.sh and scripts/pull-all.sh in scripts/

    """
    repo_root = tmp_path / "skills-repo"
    repo_root.mkdir()

    # Create a .git file in the repo root (simulates a git worktree)
    (repo_root / ".git").write_text("gitdir: .git\n")

    # Copy install-skills.sh to the repo root
    if INSTALL_SKILLS_SH.exists():
        (repo_root / "install-skills.sh").write_text(INSTALL_SKILLS_SH.read_text())

    # Create scripts/ directory and copy push/pull scripts
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir()
    for src in (PUSH_ALL_SH, PULL_ALL_SH):
        if src.exists():
            (scripts_dir / src.name).write_text(src.read_text())

    return repo_root


def make_skill(repo_root, name, files=None):
    """Create a mock skill submodule the installer will accept.

    The installer enumerates shippable files via `git ls-files`, so each mock
    skill must be a real git repo with its files tracked (a bare `.git` marker
    is not enough). `files` maps relative paths to text contents and defaults to
    a lone SKILL.md. Files are staged (not committed) - `git ls-files` reads the
    index, which is all build_staging needs.

    Returns the skill directory path.
    """
    if files is None:
        files = {"SKILL.md": f"# {name}\n"}
    skill_dir = repo_root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        target = skill_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    subprocess.run(
        ["git", "init", "-q"], cwd=skill_dir, check=True, capture_output=True
    )
    subprocess.run(["git", "add", "-A"], cwd=skill_dir, check=True, capture_output=True)
    return skill_dir


def run_install_script(repo_root, *args, cwd=None, env_override=None):
    """Run install-skills.sh with the given arguments.

    Returns the CompletedProcess result.
    """
    cmd = ["bash", str(repo_root / "install-skills.sh"), *args]
    run_env = os.environ.copy()
    if env_override:
        run_env.update(env_override)
    return subprocess.run(
        cmd,
        cwd=cwd or str(repo_root),
        capture_output=True,
        text=True,
        env=run_env,
    )


def run_push_script(repo_root, *args):
    """Run scripts/push-all.sh with the given arguments."""
    cmd = ["bash", str(repo_root / "scripts" / "push-all.sh"), *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def run_pull_script(repo_root, *args):
    """Run scripts/pull-all.sh with the given arguments."""
    cmd = ["bash", str(repo_root / "scripts" / "pull-all.sh"), *args]
    return subprocess.run(cmd, capture_output=True, text=True)


@pytest.fixture()
def tmp_git_repo(tmp_path):
    """Create a temporary git repo with scripts/push-all.sh and scripts/pull-all.sh.

    Unlike tmp_repo, this does NOT create a .git file at the root, making it
    suitable for tests that need to set up their own git structure
    (e.g., submodule traversal tests).

    Returns a Path to the repo root with:
      - scripts/push-all.sh
      - scripts/pull-all.sh

    """
    repo_root = tmp_path / "git-repo"
    repo_root.mkdir()

    # Create scripts/ directory
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir()
    for src in (PUSH_ALL_SH, PULL_ALL_SH):
        if src.exists():
            (scripts_dir / src.name).write_text(src.read_text())

    return repo_root
