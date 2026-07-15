# Hermes Skill Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy source-controlled skills to Hermes Agent from both platform installers and detect deployment drift without writing.

**Architecture:** Extend the existing installer destination lists rather than adding a second packager. Resolve Hermes home through an override-first platform helper, reuse the existing tracked-file staging and preview code, and add a check-mode accumulator that returns nonzero when any selected destination is missing or changed. Repair Git Bash source enumeration first so Windows tests exercise real payloads.

**Tech Stack:** Bash, Windows batch, Git, pytest, shell integration tests, Ruff, ShellCheck, Aislop.

## Global Constraints

- Skill source repositories remain authoritative; Hermes runtime directories are generated mirrors.
- Do not install the umbrella repository as a Hermes plugin.
- `--check` must never prompt or write and must return 0 for clean, 1 for drift, and 2 for argument errors.
- Default mode adds Hermes only when its home exists; explicit `--hermes` and `--all` may create it.
- Do not change skill submodule pointers or hard-code machine-specific paths.
- Every production behavior change must have a test observed failing before implementation.

---

### Task 1: Cross-platform Hermes destination and drift checking

**Files:**
- Modify: `install-skills.sh`
- Modify: `install-skills.bat`
- Modify: `tests/test_install_skills.py`
- Modify: `tests/test-install.sh`
- Modify: `README.md`
- Delete at branch finish: `docs/superpowers/plans/2026-07-15-hermes-skill-deployment.md`

**Interfaces:**
- Bash produces `hermes_home() -> stdout path`, `git_workdir_path(path) -> stdout path`, and process exit codes 0/1/2.
- Batch produces `:set_hermes_home`, stores `HERMES_HOME_RESOLVED`, and returns process exit codes 0/1/2.
- Both accept `--hermes` and `--check`; `--check` implies dry run and tracks drift across every selected skill/destination.

- [x] **Step 1: Add failing regression tests for Git Bash tracked-file staging**

Keep the existing real-repository fixture and add an assertion that a failed `git ls-files` cannot produce exit 0. The existing Windows failures in `TestInstallContent` are the primary red signal. Add this focused case:

```python
import shutil


def test_git_enumeration_failure_is_fatal(tmp_repo, tmp_path):
    skill = make_skill(tmp_repo, "broken")
    shutil.rmtree(skill / ".git")
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
```

Run:

```bash
python -m pytest tests/test_install_skills.py::test_git_enumeration_failure_is_fatal tests/test_install_skills.py::TestInstallContent::test_yes_installs_skill_md -v
```

Expected: the new test fails because the script returns 0; on Windows the install-content test also fails because `git -C /tmp/...` cannot resolve the path.

- [x] **Step 2: Make Bash source enumeration fail safely and work under Git Bash**

Add a path helper and capture `git ls-files` before iterating so failure propagates:

```bash
git_workdir_path() {
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -w "$1"
    else
        printf '%s\n' "$1"
    fi
}
```

In `build_staging`, compute `git_src`, write tracked names to a temporary file, fail with `could not enumerate tracked files for <skill>` when Git fails, and iterate the file. Ensure cleanup occurs on both paths. Make `install_skill_to_destination` propagate the nonzero return rather than continuing with an empty staging tree.

Run the two focused tests again. Expected: both pass.

Commit:

```bash
git add install-skills.sh tests/test_install_skills.py docs/superpowers/plans/2026-07-15-hermes-skill-deployment.md
git commit -m "fix(installer): fail safely when source enumeration fails"
```

Mark Steps 1-2 complete in the plan in the same commit.

- [ ] **Step 3: Add failing Bash tests for Hermes resolution and selection**

Update help expectations to include `--hermes` and `--check`. Remove `--hermes` from the retired-flags assertion. Add tests with `HERMES_HOME` pointing to `tmp_path / "hermes-home"` for:

```python
def test_hermes_flag_installs_to_override_home(...):
    result = run_install_script(..., "--hermes", "-y", "hermes-skill", env_override=env)
    assert result.returncode == 0
    assert (hermes_home / "skills/hermes-skill/SKILL.md").exists()
```

Also test:

- Default mode includes Hermes when `<HERMES_HOME>` exists.
- Default mode skips Hermes when it does not exist.
- `--all` includes Hermes.

Run:

```bash
python -m pytest tests/test_install_skills.py -k 'hermes or help or retired' -v
```

Expected: failures because the flags and destination do not exist.

- [ ] **Step 4: Implement Bash Hermes home resolution**

Add `hermes_home` with this exact precedence: non-empty `HERMES_HOME`; Windows/MSYS `LOCALAPPDATA/hermes`; otherwise `$HOME/.hermes`. Normalize native values with `cygpath -u` when available. Add `--hermes`, include Hermes in `add_all_destinations`, and update no-destination/help text.

Run the focused tests. Expected: pass.

- [ ] **Step 5: Add failing Bash check-mode tests**

Add separate tests for:

```python
def test_check_returns_one_for_missing_install(...): ...
def test_check_returns_zero_after_install(...): ...
def test_check_returns_one_for_changed_install(...): ...
def test_check_does_not_modify_destination(...): ...
```

Each test must invoke real source and destination trees. Verify `--check` never changes contents and does not need `-y`.

Run:

```bash
python -m pytest tests/test_install_skills.py -k check -v
```

Expected: argument error because `--check` is not implemented.

- [ ] **Step 6: Implement Bash check mode minimally**

Add `CHECK_MODE=0` and `DRIFT_FOUND=0`. Parsing `--check` sets `CHECK_MODE=1`, `DRY_RUN=1`, and `ASSUME_YES=1`. Mark drift when a selected destination is missing or `diff -rq` reports a difference. After all skills, return 1 only when `CHECK_MODE=1` and drift was found. Preserve exit 2 for argument errors and fatal source enumeration failures.

Run all Bash pytest tests:

```bash
python -m pytest tests/test_install_skills.py -v
```

Expected: pass.

- [ ] **Step 7: Add failing Windows batch integration tests**

In `tests/test-install.sh`, set `HERMES_HOME` to a temporary native Windows path and assert that `--hermes` installs to `<home>/skills`. Then assert `--check --hermes demoskill` returns 0 when clean and nonzero after changing the tracked source. Capture the exit code explicitly because the test script intentionally does not use `set -e`.

Run:

```bash
bash tests/test-install.sh
```

Expected: Hermes or check assertions fail.

- [ ] **Step 8: Implement batch Hermes resolution and check mode**

Add `CHECK_MODE`, `DRIFT_FOUND`, `--hermes`, `--check`, and `:set_hermes_home`. The resolver uses `%HERMES_HOME%`, then `%LOCALAPPDATA%\hermes`, then `%USERPROFILE%\.hermes`. Include Hermes in `:add_all_dests`.

For a missing destination in check mode, set `DRIFT_FOUND=1` and remove staging. For existing destinations, treat robocopy preview codes 1 through 7 as drift and codes 8 or greater as fatal. At the final exit, return 1 when check mode found drift.

Run:

```bash
bash tests/test-install.sh
```

Expected: `ALL TESTS PASSED` and exit 0.

- [ ] **Step 9: Update durable documentation**

Update `README.md` and both installers' usage blocks to explain authoring source versus generated mirrors, Hermes path precedence, `--hermes`, default existing-only selection, `--all`, and `--check` exit behavior. Do not preserve historical wording about Hermes being retired.

- [ ] **Step 10: Run full gates and commit the integrated feature**

Run each gate separately and record every return code:

```bash
python -m pytest tests -q
ruff check scripts/ tests/
ruff format --check scripts/ tests/
bash tests/test-install.sh
shellcheck install-skills.sh tests/test-install.sh
aislop ci --changes
git diff --check
```

If ShellCheck is unavailable, record that fact and rely on CI rather than installing an unplanned dependency. Expected: all available gates pass and Aislop reports 100 for changed files.

Commit explicitly staged files:

```bash
git add install-skills.sh install-skills.bat tests/test_install_skills.py tests/test-install.sh README.md docs/superpowers/plans/2026-07-15-hermes-skill-deployment.md
git commit -m "feat(installer): deploy and check Hermes skills"
```

- [ ] **Step 11: Verify against the live Hermes destination without writing**

Run:

```bash
bash install-skills.sh --check --hermes
```

Expected: exit 0 if live deployment matches, or exit 1 with a symbolic drift report. A drift result is valid evidence that detection works and must not be auto-applied during this step.
