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
        (repo_root / "install-skills.sh").write_text(
            INSTALL_SKILLS_SH.read_text()
        )

    # Create scripts/ directory and copy push/pull scripts
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir()
    for src in (PUSH_ALL_SH, PULL_ALL_SH):
        if src.exists():
            (scripts_dir / src.name).write_text(src.read_text())

    return repo_root


@pytest.fixture()
def mock_skill_root_layout(tmp_path):
    """Create a mock skill with root layout (SKILL.md at root).

    Returns the path to the skill directory.
    """
    skill_dir = tmp_path / "mock-skill"
    skill_dir.mkdir()

    # Write a SKILL.md to indicate root layout
    skill_dir.joinpath("SKILL.md").write_text(
        "# Mock Skill\n\nThis is a mock skill for testing.\n"
    )

    # Write some installable files
    skill_dir.joinpath("README.md").write_text("Readme for mock skill.\n")
    skill_dir.joinpath("evals").mkdir()
    skill_dir.joinpath("evals", "example.md").write_text("eval\n")

    return skill_dir


@pytest.fixture()
def mock_skill_draft_layout(tmp_path):
    """Create a mock skill with draft layout (skill-draft/ subdirectory).

    Returns the path to the skill directory.
    """
    skill_dir = tmp_path / "mock-draft-skill"
    skill_dir.mkdir()

    # Create skill-draft/ directory with content
    draft_dir = skill_dir / "skill-draft"
    draft_dir.mkdir()
    draft_dir.joinpath("SKILL.md").write_text(
        "# Mock Draft Skill\n\nLegacy layout for testing.\n"
    )

    # Write a doc that would only be in skill-draft
    draft_dir.joinpath("docs", "usage.md")
    draft_dir.joinpath("docs").mkdir(exist_ok=True)
    draft_dir.joinpath("docs", "usage.md").write_text("Usage docs.\n")

    return skill_dir


@pytest.fixture()
def mock_skill_no_content(tmp_path):
    """Create a mock skill directory with no installable content.

    Neither SKILL.md nor skill-draft/ exists.
    """
    skill_dir = tmp_path / "mock-empty-skill"
    skill_dir.mkdir()

    # Write something that isn't SKILL.md
    skill_dir.joinpath("README.md").write_text("Just a readme.\n")

    return skill_dir


@pytest.fixture()
def mock_dest_dir(tmp_path):
    """Create a mock agent destination directory.

    Returns the path to the destination root.
    """
    dest = tmp_path / "agent" / "skills"
    dest.mkdir(parents=True)
    return dest


def create_mock_submodule(repo_root, skill_dir, name):
    """Create a submodule directory inside the mock repo with a .git marker.

    This simulates a git submodule directory that would be picked up by the
    install script's `[ -e "$src/.git" ]` check.
    """
    dest = repo_root / name
    dest.mkdir()
    # Submodule .git file (simulated - real submodules have gitdir: lines)
    dest.joinpath(".git").write_text(
        f"gitdir: {repo_root / '.git' / 'modules' / name}\n"
    )
    # Copy the skill content into the submodule directory
    for item in skill_dir.iterdir():
        if item.is_dir():
            import shutil
            shutil.copytree(item, dest / item.name)
        else:
            import shutil
            shutil.copy2(item, dest / item.name)


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
