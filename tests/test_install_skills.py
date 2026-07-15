"""Tests for install-skills.sh.

Covers argument parsing, --help, dry-run, allowlist staging (git-tracked
top-level allowlist + .skillpack), and the existing-only default destination
behavior (default mode installs only to harness dirs that already exist;
explicit flags force-create).

Mock skills are created with conftest.make_skill, which initializes a real git
repo and stages the files — the installer enumerates shippable content via
`git ls-files`, so a bare `.git` marker would stage nothing.
"""

import os
import shutil
import stat
import subprocess

from .conftest import make_skill, run_install_script


def home_with(tmp_path, *harness_dirs):
    """env_override pointing HOME at tmp_path, with the named parent harness
    dirs (e.g. ".claude") pre-created so default mode treats them as present."""
    for harness in harness_dirs:
        (tmp_path / harness).mkdir(parents=True, exist_ok=True)
    return {"HOME": str(tmp_path), "HERMES_HOME": str(tmp_path / "hermes-home")}


class TestMirrorPreservesDestinationOutput:
    """Dest-only generated output (__pycache__) must survive a
    reinstall on both mirror paths, including the no-rsync fallback that
    Windows Git-Bash takes."""

    def test_junk_survives_and_managed_entries_cleanup(self, tmp_repo, tmp_path):
        env = home_with(tmp_path, ".claude")
        make_skill(tmp_repo, "keeper", files={"SKILL.md": "# keeper v1\n"})
        result = run_install_script(tmp_repo, "-y", "keeper", env_override=env)
        assert result.returncode == 0
        dest = tmp_path / ".claude" / "skills" / "keeper"
        assert (dest / "SKILL.md").exists()

        (dest / "reports").mkdir()
        (dest / "reports" / "april.md").write_text("spend report\n")
        (dest / "__pycache__").mkdir()
        (dest / "__pycache__" / "x.pyc").write_text("junk\n")
        (dest / "stale.txt").write_text("left by an older install\n")

        # Change the source so the update path (mirror_tree) actually runs.
        (tmp_repo / "keeper" / "SKILL.md").write_text("# keeper v2\n")
        subprocess.run(
            ["git", "add", "SKILL.md"],
            cwd=tmp_repo / "keeper",
            check=True,
            capture_output=True,
        )

        result = run_install_script(tmp_repo, "-y", "keeper", env_override=env)
        assert result.returncode == 0
        assert (dest / "SKILL.md").read_text() == "# keeper v2\n"
        assert not (dest / "reports").exists()
        assert (dest / "__pycache__" / "x.pyc").exists()
        assert not (dest / "stale.txt").exists()


class TestHelpAndUsage:
    def test_help_long_flag_shows_usage_and_exits_zero(self, tmp_repo):
        result = run_install_script(tmp_repo, "--help")
        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert "install-skills.sh" in result.stdout
        assert "-y / --yes" in result.stdout
        assert "-n / --dry-run" in result.stdout

    def test_short_help_flag_shows_usage_and_exits_zero(self, tmp_repo):
        result = run_install_script(tmp_repo, "-h")
        assert result.returncode == 0
        assert "Usage:" in result.stdout

    def test_help_lists_all_destination_flags(self, tmp_repo):
        result = run_install_script(tmp_repo, "--help")
        for flag in [
            "--agents",
            "--claude",
            "--gemini",
            "--hermes",
            "--all",
            "--check",
        ]:
            assert flag in result.stdout, f"Flag '{flag}' not in help output"

    def test_help_first_line(self, tmp_repo):
        result = run_install_script(tmp_repo, "-h")
        assert result.returncode == 0
        first = result.stdout.strip().split("\n")[0]
        assert (
            first == "Install skills from this repo into one or more agent config dirs."
        )

    def test_help_documents_existing_only_default(self, tmp_repo):
        result = run_install_script(tmp_repo, "--help")
        assert "ALREADY EXIST" in result.stdout


class TestArgumentErrors:
    def test_unknown_long_flag_exits_two(self, tmp_repo):
        result = run_install_script(tmp_repo, "--bogus-flag")
        assert result.returncode == 2
        assert "unknown flag" in result.stderr

    def test_unknown_short_flag_exits_two(self, tmp_repo):
        result = run_install_script(tmp_repo, "-z")
        assert result.returncode == 2
        assert "unknown flag" in result.stderr

    def test_retired_flags_are_rejected(self, tmp_repo):
        """--pi/--codex were retired for the agents-canonical model."""
        for flag in ("--pi", "--codex"):
            result = run_install_script(tmp_repo, flag)
            assert result.returncode == 2, f"{flag} should now be unknown"
            assert "unknown flag" in result.stderr


class TestDryRun:
    def test_dry_run_short_flag_does_not_create_dest(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "dry-skill")
        env = home_with(tmp_path, ".claude")
        result = run_install_script(tmp_repo, "-n", "dry-skill", env_override=env)
        assert result.returncode == 0
        assert "install dry-skill" in result.stdout
        assert not (tmp_path / ".claude" / "skills" / "dry-skill").exists()

    def test_dry_run_long_flag_does_not_create_dest(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "dry-long")
        env = home_with(tmp_path, ".claude")
        result = run_install_script(tmp_repo, "--dry-run", "dry-long", env_override=env)
        assert result.returncode == 0
        assert not (tmp_path / ".claude" / "skills" / "dry-long").exists()


def make_writable_and_retry(func, path, _exc_info):
    """Allow the malformed-git fixture to remove Windows read-only git objects."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def test_git_enumeration_failure_is_fatal(tmp_repo, tmp_path):
    skill = make_skill(tmp_repo, "broken")
    shutil.rmtree(skill / ".git", onexc=make_writable_and_retry)
    (skill / ".git").write_text("gitdir: missing-git-directory\n")
    result = run_install_script(
        tmp_repo,
        "--claude",
        "-y",
        "broken",
        env_override={"HOME": str(tmp_path)},
    )
    assert result.returncode == 1
    assert "could not enumerate tracked files" in result.stderr


def test_comparison_infrastructure_failure_is_fatal(tmp_repo, tmp_path):
    make_skill(tmp_repo, "compare-broken")
    hermes_home = tmp_path / "hermes-home"
    env = {"HERMES_HOME": str(hermes_home), "HOME": str(tmp_path)}
    installed = run_install_script(
        tmp_repo, "--hermes", "-y", "compare-broken", env_override=env
    )
    assert installed.returncode == 0

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_diff = fake_bin / "diff"
    fake_diff.write_text("#!/usr/bin/env bash\nexit 2\n")
    fake_diff.chmod(fake_diff.stat().st_mode | stat.S_IXUSR)
    if os.name == "nt":
        shutil.copyfile(shutil.which("bash"), fake_bin / "diff.exe")
        fake_bin_path = subprocess.run(
            ["cygpath", "-u", str(fake_bin)], capture_output=True, check=True, text=True
        ).stdout.strip()
        shell_path = subprocess.run(
            ["bash", "-lc", 'printf %s "$PATH"'],
            capture_output=True,
            check=True,
            text=True,
        ).stdout
        env["PATH"] = f"{fake_bin_path}:{shell_path}"
    else:
        env["PATH"] = f"{fake_bin}{os.pathsep}{os.environ['PATH']}"

    result = run_install_script(
        tmp_repo, "--check", "--hermes", "compare-broken", env_override=env
    )
    assert result.returncode != 0
    assert "could not compare compare-broken" in result.stderr


def test_setup_debuggers_runs_selected_skill_script(tmp_repo, tmp_path):
    make_skill(
        tmp_repo,
        "using-a-debugger",
        files={
            "SKILL.md": "# using-a-debugger\n",
            "scripts/setup-debuggers.py": "# test probe\n",
        },
    )
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python3"
    fake_python.write_text('#!/usr/bin/env bash\nprintf "debugger setup invoked\\n"\n')
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)
    fake_bin_path = subprocess.run(
        ["cygpath", "-u", str(fake_bin)], capture_output=True, check=True, text=True
    ).stdout.strip()
    shell_path = subprocess.run(
        ["bash", "-lc", 'printf %s "$PATH"'], capture_output=True, check=True, text=True
    ).stdout
    env = home_with(tmp_path)
    env["PATH"] = f"{fake_bin_path}:{shell_path}"

    result = run_install_script(
        tmp_repo,
        "--agents",
        "-y",
        "--setup-debuggers",
        "using-a-debugger",
        env_override=env,
    )
    assert result.returncode == 0
    assert "debugger setup invoked" in result.stdout


def test_check_skips_debugger_setup_on_clean_install(tmp_repo, tmp_path):
    make_skill(
        tmp_repo,
        "using-a-debugger",
        files={
            "SKILL.md": "# using-a-debugger\n",
            "scripts/setup-debuggers.py": "# test probe\n",
        },
    )
    base_env = {"HOME": str(tmp_path)}
    installed = run_install_script(
        tmp_repo,
        "--agents",
        "-y",
        "using-a-debugger",
        env_override=base_env,
    )
    assert installed.returncode == 0

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    marker = tmp_path / "debugger-setup-ran"
    fake_python = fake_bin / "python3"
    fake_python.write_text(f"#!/usr/bin/env bash\ntouch '{marker}'\n")
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)
    fake_bin_path = subprocess.run(
        ["cygpath", "-u", str(fake_bin)], capture_output=True, check=True, text=True
    ).stdout.strip()
    shell_path = subprocess.run(
        ["bash", "-lc", 'printf %s "$PATH"'], capture_output=True, check=True, text=True
    ).stdout
    env = {"HOME": str(tmp_path), "PATH": f"{fake_bin_path}:{shell_path}"}

    result = run_install_script(
        tmp_repo,
        "--check",
        "--agents",
        "--setup-debuggers",
        "using-a-debugger",
        env_override=env,
    )

    assert result.returncode == 0
    assert not marker.exists()


class TestInstallContent:
    def test_yes_installs_skill_md(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "yes-skill")
        env = home_with(tmp_path, ".claude")
        result = run_install_script(tmp_repo, "-y", "yes-skill", env_override=env)
        assert result.returncode == 0
        assert (tmp_path / ".claude" / "skills" / "yes-skill" / "SKILL.md").exists()

    def test_allowlisted_subdir_content_copies(self, tmp_repo, tmp_path):
        make_skill(
            tmp_repo,
            "withref",
            files={
                "SKILL.md": "# withref\n",
                "references/note.txt": "hello\n",
            },
        )
        env = home_with(tmp_path, ".claude")
        result = run_install_script(tmp_repo, "-y", "withref", env_override=env)
        assert result.returncode == 0
        dest = tmp_path / ".claude" / "skills" / "withref"
        assert (dest / "SKILL.md").exists()
        assert (dest / "references" / "note.txt").read_text() == "hello\n"


class TestDestinationFlags:
    """Explicit flags target a single harness and force-create it even when
    the harness dir does not already exist (HOME here has no harness dirs)."""

    def test_agents_flag(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "agents-skill")
        result = run_install_script(
            tmp_repo,
            "--agents",
            "-y",
            "agents-skill",
            env_override={"HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        assert (tmp_path / ".agents" / "skills" / "agents-skill" / "SKILL.md").exists()

    def test_claude_flag(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "claude-skill")
        result = run_install_script(
            tmp_repo,
            "--claude",
            "-y",
            "claude-skill",
            env_override={"HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        assert (tmp_path / ".claude" / "skills" / "claude-skill" / "SKILL.md").exists()

    def test_gemini_flag(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "gemini-skill")
        result = run_install_script(
            tmp_repo,
            "--gemini",
            "-y",
            "gemini-skill",
            env_override={"HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        assert (
            tmp_path / ".gemini" / "config" / "skills" / "gemini-skill" / "SKILL.md"
        ).exists()


class TestExistingOnlyDefault:
    """Default mode (no agent flag) installs only to harness dirs that already
    exist; absent harnesses are skipped, not created."""

    def test_installs_to_each_existing_harness(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "deux")
        env = home_with(tmp_path, ".claude", ".gemini/config")  # .agents absent
        result = run_install_script(tmp_repo, "-y", env_override=env)
        assert result.returncode == 0
        assert (tmp_path / ".claude" / "skills" / "deux" / "SKILL.md").exists()
        assert (
            tmp_path / ".gemini" / "config" / "skills" / "deux" / "SKILL.md"
        ).exists()
        assert not (tmp_path / ".agents").exists()
        assert "skip agents" in result.stdout

    def test_skips_absent_harness(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "solo")
        env = home_with(tmp_path, ".claude")  # only claude present
        result = run_install_script(tmp_repo, "-y", env_override=env)
        assert result.returncode == 0
        assert (tmp_path / ".claude" / "skills" / "solo" / "SKILL.md").exists()
        assert not (tmp_path / ".gemini").exists()
        assert not (tmp_path / ".agents").exists()

    def test_no_existing_harness_exits_zero_with_message(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "lonely")
        env = {
            "HOME": str(tmp_path),
            "HERMES_HOME": str(tmp_path / "hermes-home"),
        }  # no harness dirs at all
        result = run_install_script(tmp_repo, "-y", env_override=env)
        assert result.returncode == 0
        assert "No existing skill destinations" in result.stdout
        for harness in (".agents", ".claude", ".gemini"):
            assert not (tmp_path / harness).exists()

    def test_explicit_flag_creates_absent_harness(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "forced")
        env = {"HOME": str(tmp_path)}  # .gemini absent
        result = run_install_script(
            tmp_repo, "--gemini", "-y", "forced", env_override=env
        )
        assert result.returncode == 0
        assert (
            tmp_path / ".gemini" / "config" / "skills" / "forced" / "SKILL.md"
        ).exists()

    def test_all_flag_force_creates_every_harness(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "everywhere")
        env = {"HOME": str(tmp_path)}  # nothing exists
        result = run_install_script(
            tmp_repo, "--all", "-y", "everywhere", env_override=env
        )
        assert result.returncode == 0
        assert (tmp_path / ".agents" / "skills" / "everywhere" / "SKILL.md").exists()
        assert (tmp_path / ".claude" / "skills" / "everywhere" / "SKILL.md").exists()
        assert (
            tmp_path / ".gemini" / "config" / "skills" / "everywhere" / "SKILL.md"
        ).exists()


class TestHermesDestination:
    def test_hermes_home_wins_over_localappdata_and_home(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "hermes-precedence")
        hermes_home = tmp_path / "explicit-hermes-home"
        localappdata = tmp_path / "local-app-data"
        result = run_install_script(
            tmp_repo,
            "--hermes",
            "-y",
            "hermes-precedence",
            env_override={
                "HERMES_HOME": str(hermes_home),
                "LOCALAPPDATA": str(localappdata),
                "HOME": str(tmp_path / "home"),
                "OSTYPE": "msys",
            },
        )
        assert result.returncode == 0
        assert (hermes_home / "skills" / "hermes-precedence" / "SKILL.md").exists()
        assert not (localappdata / "hermes").exists()

    def test_msys_uses_localappdata_when_hermes_home_is_absent(
        self, tmp_repo, tmp_path
    ):
        make_skill(tmp_repo, "hermes-localappdata")
        localappdata = tmp_path / "local-app-data"
        result = run_install_script(
            tmp_repo,
            "--hermes",
            "-y",
            "hermes-localappdata",
            env_override={
                "HERMES_HOME": "",
                "LOCALAPPDATA": str(localappdata),
                "HOME": str(tmp_path / "home"),
                "OSTYPE": "msys",
            },
        )
        assert result.returncode == 0
        assert (
            localappdata / "hermes" / "skills" / "hermes-localappdata" / "SKILL.md"
        ).exists()

    def test_hermes_uses_home_fallback_when_other_sources_are_absent(
        self, tmp_repo, tmp_path
    ):
        make_skill(tmp_repo, "hermes-home-fallback")
        home = tmp_path / "home"
        result = run_install_script(
            tmp_repo,
            "--hermes",
            "-y",
            "hermes-home-fallback",
            env_override={"HERMES_HOME": "", "LOCALAPPDATA": "", "HOME": str(home)},
        )
        assert result.returncode == 0
        assert (
            home / ".hermes" / "skills" / "hermes-home-fallback" / "SKILL.md"
        ).exists()

    def test_hermes_home_is_normalized_with_cygpath(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "hermes-normalized")
        fake_bin = tmp_path / "fake-bin"
        fake_bin.mkdir()
        normalized_home = tmp_path / "normalized-hermes-home"
        real_cygpath = shutil.which("cygpath")
        assert real_cygpath is not None
        fake_cygpath = fake_bin / "cygpath"
        fake_cygpath.write_text(
            "#!/usr/bin/env bash\n"
            'if [ "$1" = -u ]; then\n'
            f"    printf '%s\\n' '{normalized_home}'\n"
            "else\n"
            f"    '{real_cygpath}' \"$@\"\n"
            "fi\n"
        )
        fake_cygpath.chmod(fake_cygpath.stat().st_mode | stat.S_IXUSR)
        fake_bin_path = subprocess.run(
            ["cygpath", "-u", str(fake_bin)], capture_output=True, check=True, text=True
        ).stdout.strip()
        shell_path = subprocess.run(
            ["bash", "-lc", 'printf %s "$PATH"'],
            capture_output=True,
            check=True,
            text=True,
        ).stdout

        result = run_install_script(
            tmp_repo,
            "--hermes",
            "-y",
            "hermes-normalized",
            env_override={
                "HERMES_HOME": r"C:\\un-normalized-hermes-home",
                "HOME": str(tmp_path / "home"),
                "PATH": f"{fake_bin_path}:{shell_path}",
            },
        )
        assert result.returncode == 0
        assert (normalized_home / "skills" / "hermes-normalized" / "SKILL.md").exists()

    def test_hermes_flag_installs_to_override_home(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "hermes-skill")
        hermes_home = tmp_path / "hermes-home"
        result = run_install_script(
            tmp_repo,
            "--hermes",
            "-y",
            "hermes-skill",
            env_override={"HERMES_HOME": str(hermes_home), "HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        assert (hermes_home / "skills" / "hermes-skill" / "SKILL.md").exists()

    def test_default_mode_includes_existing_hermes_home(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "hermes-default")
        hermes_home = tmp_path / "hermes-home"
        hermes_home.mkdir()
        result = run_install_script(
            tmp_repo,
            "-y",
            "hermes-default",
            env_override={"HERMES_HOME": str(hermes_home), "HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        assert (hermes_home / "skills" / "hermes-default" / "SKILL.md").exists()

    def test_default_mode_skips_missing_hermes_home(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "hermes-absent")
        hermes_home = tmp_path / "hermes-home"
        result = run_install_script(
            tmp_repo,
            "-y",
            "hermes-absent",
            env_override={"HERMES_HOME": str(hermes_home), "HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        assert not hermes_home.exists()

    def test_all_flag_includes_hermes(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "hermes-all")
        hermes_home = tmp_path / "hermes-home"
        result = run_install_script(
            tmp_repo,
            "--all",
            "-y",
            "hermes-all",
            env_override={"HERMES_HOME": str(hermes_home), "HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        assert (hermes_home / "skills" / "hermes-all" / "SKILL.md").exists()


class TestCheckMode:
    def test_check_returns_one_for_missing_install(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "missing-check")
        result = run_install_script(
            tmp_repo,
            "--check",
            "--hermes",
            "missing-check",
            env_override={
                "HERMES_HOME": str(tmp_path / "hermes-home"),
                "HOME": str(tmp_path),
            },
        )
        assert result.returncode == 1
        assert "install missing-check" in result.stdout

    def test_check_returns_zero_after_install(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "clean-check")
        hermes_home = tmp_path / "hermes-home"
        env = {"HERMES_HOME": str(hermes_home), "HOME": str(tmp_path)}
        installed = run_install_script(
            tmp_repo, "--hermes", "-y", "clean-check", env_override=env
        )
        assert installed.returncode == 0

        result = run_install_script(
            tmp_repo, "--check", "--hermes", "clean-check", env_override=env
        )
        assert result.returncode == 0
        assert "unchanged clean-check (hermes)" in result.stdout

    def test_check_returns_one_for_changed_install(self, tmp_repo, tmp_path):
        skill = make_skill(tmp_repo, "changed-check")
        hermes_home = tmp_path / "hermes-home"
        env = {"HERMES_HOME": str(hermes_home), "HOME": str(tmp_path)}
        installed = run_install_script(
            tmp_repo, "--hermes", "-y", "changed-check", env_override=env
        )
        assert installed.returncode == 0
        (skill / "SKILL.md").write_text("# changed-check v2\n")

        result = run_install_script(
            tmp_repo, "--check", "--hermes", "changed-check", env_override=env
        )
        assert result.returncode == 1
        assert "~ SKILL.md (changed)" in result.stdout

    def test_check_does_not_modify_destination(self, tmp_repo, tmp_path):
        skill = make_skill(tmp_repo, "immutable-check")
        hermes_home = tmp_path / "hermes-home"
        env = {"HERMES_HOME": str(hermes_home), "HOME": str(tmp_path)}
        installed = run_install_script(
            tmp_repo, "--hermes", "-y", "immutable-check", env_override=env
        )
        assert installed.returncode == 0
        dest = hermes_home / "skills" / "immutable-check" / "SKILL.md"
        before = dest.read_text()
        (skill / "SKILL.md").write_text("# immutable-check v2\n")

        result = run_install_script(
            tmp_repo, "--check", "--hermes", "immutable-check", env_override=env
        )
        assert result.returncode == 1
        assert dest.read_text() == before


class TestDefaultSelection:
    def test_default_installs_all_skills(self, tmp_repo, tmp_path):
        for name in ("alpha", "beta", "gamma"):
            make_skill(tmp_repo, name)
        env = home_with(tmp_path, ".claude")
        result = run_install_script(tmp_repo, "-y", env_override=env)
        assert result.returncode == 0
        skills = tmp_path / ".claude" / "skills"
        for name in ("alpha", "beta", "gamma"):
            assert (skills / name / "SKILL.md").exists()

    def test_skips_non_submodule_dirs(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "real-skill")
        # A plain directory without a .git marker is not a submodule.
        non_skill = tmp_repo / "not-a-submodule"
        non_skill.mkdir()
        (non_skill / "SKILL.md").write_text("# not a submodule\n")
        env = home_with(tmp_path, ".claude")
        result = run_install_script(tmp_repo, "-y", env_override=env)
        assert result.returncode == 0
        skills = tmp_path / ".claude" / "skills"
        assert (skills / "real-skill" / "SKILL.md").exists()
        assert not (skills / "not-a-submodule").exists()

    def test_skips_skill_without_skill_md(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "no-content", files={"README.md": "just a readme\n"})
        env = home_with(tmp_path, ".claude")
        result = run_install_script(tmp_repo, "-y", env_override=env)
        assert result.returncode == 0
        assert not (tmp_path / ".claude" / "skills" / "no-content").exists()


class TestAllowlistStaging:
    def test_non_allowlisted_toplevel_is_excluded(self, tmp_repo, tmp_path):
        make_skill(
            tmp_repo,
            "trim",
            files={
                "SKILL.md": "# trim\n",
                "scripts/run.sh": "echo hi\n",  # allowlisted
                "README.md": "readme\n",  # not allowlisted
                ".gitignore": "*.tmp\n",  # not allowlisted
                "evals/case.md": "eval\n",  # not allowlisted
            },
        )
        env = home_with(tmp_path, ".claude")
        result = run_install_script(tmp_repo, "-y", "trim", env_override=env)
        assert result.returncode == 0
        dest = tmp_path / ".claude" / "skills" / "trim"
        assert (dest / "SKILL.md").exists()
        assert (dest / "scripts" / "run.sh").exists()
        assert not (dest / "README.md").exists()
        assert not (dest / ".gitignore").exists()
        assert not (dest / "evals").exists()
        assert not (dest / ".git").exists()

    def test_skillpack_extends_allowlist(self, tmp_repo, tmp_path):
        make_skill(
            tmp_repo,
            "packed",
            files={
                "SKILL.md": "# packed\n",
                "hooks/hook.sh": "echo hook\n",  # shipped via .skillpack
                "extras/data.txt": "x\n",  # not declared -> excluded
                ".skillpack": "hooks\n",
            },
        )
        env = home_with(tmp_path, ".claude")
        result = run_install_script(tmp_repo, "-y", "packed", env_override=env)
        assert result.returncode == 0
        dest = tmp_path / ".claude" / "skills" / "packed"
        assert (dest / "hooks" / "hook.sh").exists()
        assert not (dest / "extras").exists()
        assert not (dest / ".skillpack").exists()  # manifest itself never ships


class TestSelective:
    def test_single_skill_selection(self, tmp_repo, tmp_path):
        for name in ("alpha", "beta", "gamma"):
            make_skill(tmp_repo, name)
        env = home_with(tmp_path, ".claude")
        result = run_install_script(tmp_repo, "-y", "beta", env_override=env)
        assert result.returncode == 0
        skills = tmp_path / ".claude" / "skills"
        assert (skills / "beta" / "SKILL.md").exists()
        assert not (skills / "alpha").exists()
        assert not (skills / "gamma").exists()

    def test_multiple_skill_selection(self, tmp_repo, tmp_path):
        for name in ("alpha", "beta", "gamma"):
            make_skill(tmp_repo, name)
        env = home_with(tmp_path, ".claude")
        result = run_install_script(tmp_repo, "-y", "alpha", "gamma", env_override=env)
        assert result.returncode == 0
        skills = tmp_path / ".claude" / "skills"
        assert (skills / "alpha" / "SKILL.md").exists()
        assert not (skills / "beta").exists()
        assert (skills / "gamma" / "SKILL.md").exists()


class TestOutputMessages:
    def test_dry_run_shows_install_message(self, tmp_repo, tmp_path):
        make_skill(tmp_repo, "msg-skill")
        env = home_with(tmp_path, ".claude")
        result = run_install_script(tmp_repo, "-n", "msg-skill", env_override=env)
        assert result.returncode == 0
        assert "install msg-skill" in result.stdout

    def test_unknown_flag_message(self, tmp_repo):
        result = run_install_script(tmp_repo, "--fake")
        assert result.returncode == 2
        assert "unknown flag" in result.stderr


class TestUpdatePreview:
    """The update-an-already-installed-skill preview is rendered git-status
    style (+ new / ~ changed / - removed) with skill-relative paths. The
    clean tree is staged in a temp dir, but that absolute path must never
    leak into the user-facing preview (it reads like a bug otherwise)."""

    def test_update_preview_is_clean_and_symbolic(self, tmp_repo, tmp_path):
        skill = make_skill(
            tmp_repo,
            "evolve",
            files={
                "SKILL.md": "# evolve\nv1\n",
                "references/keep.md": "keep\n",
                "references/gone.md": "remove me\n",
            },
        )
        env = home_with(tmp_path, ".claude")

        # First install for real so the destination exists.
        first = run_install_script(tmp_repo, "-y", "evolve", env_override=env)
        assert first.returncode == 0
        dest = tmp_path / ".claude" / "skills" / "evolve"
        assert (dest / "references" / "gone.md").exists()

        # Evolve the skill: change SKILL.md, add a file, drop gone.md.
        (skill / "SKILL.md").write_text("# evolve\nv2 changed\n")
        (skill / "references" / "added.md").write_text("added\n")
        (skill / "references" / "gone.md").unlink()
        subprocess.run(["git", "add", "-A"], cwd=skill, check=True, capture_output=True)

        # Dry-run shows the diff preview without applying.
        result = run_install_script(tmp_repo, "-n", "evolve", env_override=env)
        assert result.returncode == 0
        out = result.stdout
        assert "~ SKILL.md (changed)" in out
        assert "+ references/added.md (new)" in out
        assert "- references/gone.md (removed, no longer shipped)" in out
        # The keep.md file is unchanged, so it must not appear.
        assert "keep.md" not in out
        # The TEMP staging dir must never leak into the preview.
        assert "skillinst" not in out
