# skills-ref Validation Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Replace skills-dev's hand-rolled SKILL.md frontmatter validator with the official Agent Skills validator (`agentskills`, from the pinned `skills-ref==0.1.1` PyPI package), keeping only the fleet-level logic that is irreducibly ours, and add skill-content validation by extending the existing markdownlint CI.

**Architecture:** First migrate the 8 remaining `skill-draft`-layout skills to root layout so the fleet is uniform (this lets `agentskills` — which requires `name == parent-dir` — validate every skill directly with no staging shim, and lets the installer drop its dual-path branch). Then the Python validator becomes a thin fleet wrapper: it iterates `.gitmodules`, applies the anti-vacuous + WIP-skip + empty-dir guards, and delegates each skill to `agentskills validate <dir>` through an injectable runner seam (so fleet logic is unit-testable offline while integration tests exercise the real binary). Content validation is pure config: extend the umbrella's markdownlint job to check skill `*/*.md` + `*/references/**/*.md` with `submodules: recursive`.

**Tech Stack:** Python 3 (stdlib only — `yaml` dependency removed), `skills-ref==0.1.1` (CLI `agentskills validate`, exit 0 valid / 1 invalid), `markdownlint-cli2-action`, Gitea Actions, git submodules (Gitea `origin` + GitHub `github`).

**Verified facts (resolved 2026-05-23, live):** `pip install skills-ref==0.1.1` installs console script **`agentskills`** (the README's `skills-ref validate` is wrong). `agentskills validate <root-layout-skill>` → `Valid skill: <path>` exit 0; name mismatch → `Directory name 'X' must match skill name 'Y'` exit 1. It tolerates root-layout extra files (LICENSE, evals/, workspace/, .markdownlint-cli2.jsonc). markdownlint-cli2 merges rule config down the tree but reads `globs` only from the invocation dir.

---

## Phase 2: Simplify the installer (drop the dual-path branch)

All skills are root layout now, so the `skill-draft/` detection and exclude are dead code.

### Task 2.1: Simplify `install-skills.sh`

**Files:** Modify `install-skills.sh`

- [x] **Step 1: Update the header comment**

Replace lines 4–7:
```bash
# Each top-level dir here is a skill submodule. The installable content is
# either `<skill>/skill-draft/` (legacy layout) or `<skill>/` itself (new
# layout, detected by a SKILL.md at the root). Dev-only files are excluded
# for the root layout.
```
with:
```bash
# Each top-level dir here is a skill submodule with a SKILL.md at its root.
# The installable content is `<skill>/` itself; dev-only files (evals/,
# tests/, README, LICENSE, etc.) are excluded — see ROOT_EXCLUDES.
```

- [x] **Step 2: Remove `skill-draft` from `ROOT_EXCLUDES`**

In the `ROOT_EXCLUDES=(...)` array, delete the line containing just `skill-draft` (currently line 75).

- [x] **Step 3: Collapse the layout detection in `install_skill_to_destination`**

Replace this block (currently lines 135–145):
```bash
    local content_dir layout
    if [ -d "$src_dir/skill-draft" ]; then
        content_dir="$src_dir/skill-draft"
        layout="draft"
    elif [ -f "$src_dir/SKILL.md" ]; then
        content_dir="$src_dir"
        layout="root"
    else
        echo "skip $name (no SKILL.md and no skill-draft/)"
        return
    fi
```
with:
```bash
    local content_dir layout
    if [ -f "$src_dir/SKILL.md" ]; then
        content_dir="$src_dir"
        layout="root"
    else
        echo "skip $name (no SKILL.md)"
        return
    fi
```
(`layout` stays — `sync_dir`/`diff_args_for` branch on `"$layout" = "root"`, which is now always true; leaving the variable avoids touching those functions.)

### Task 2.2: Simplify `install-skills.bat`

**Files:** Modify `install-skills.bat`

- [x] **Step 1: Update the header comment**

Replace lines 6–9:
```bat
rem Each top-level dir here is a skill submodule. Installable content is
rem either <skill>\skill-draft\ (legacy layout) or <skill>\ itself (new
rem layout, detected by a SKILL.md at the root). Dev-only files are
rem excluded for the root layout.
```
with:
```bat
rem Each top-level dir here is a skill submodule with a SKILL.md at its
rem root. Installable content is <skill>\ itself; dev-only files are
rem excluded for the root layout (see EXCLUDE_DIRS / EXCLUDE_FILES).
```

- [x] **Step 2: Remove `skill-draft` from `EXCLUDE_DIRS`**

Change line 57 from:
```bat
set "EXCLUDE_DIRS=.git .github docs evals node_modules reports skill-draft tests"
```
to:
```bat
set "EXCLUDE_DIRS=.git .github docs evals node_modules reports tests"
```

- [x] **Step 3: Collapse the layout detection in `:install_skill`**

Replace this block (currently lines 109–118):
```bat
if exist "!src!\skill-draft\" (
    set "content_dir=!src!\skill-draft"
    set "layout=draft"
) else if exist "!src!\SKILL.md" (
    set "content_dir=!src!"
    set "layout=root"
) else (
    echo skip !n! ^(no SKILL.md and no skill-draft\^)
    exit /b 0
)
```
with:
```bat
if exist "!src!\SKILL.md" (
    set "content_dir=!src!"
    set "layout=root"
) else (
    echo skip !n! ^(no SKILL.md^)
    exit /b 0
)
```

- [x] **Step 4: Verify the .bat still has CRLF line endings**

The Write/Edit tools emit LF on Windows; cmd.exe needs CRLF for `:label` lookup. Run (Bash tool):
```bash
cd /c/Users/mtsch/skills-dev
file install-skills.bat   # or: grep -c $'\r' install-skills.bat
sed -i 's/\([^\r]\)$/\1\r/' install-skills.bat   # only if lines lack CR
```
Expected: lines end with CRLF. (Skip the `sed` if already CRLF.)

### Task 2.3: Verify the installer (dry-run)

- [x] **Step 1: Dry-run a root-layout skill that didn't change — expect no surprises**

Run (PowerShell):
```powershell
.\install-skills.bat -n pushback
```
Expected: `unchanged pushback (claude)` (or a diff if it was edited), never a `skip`.

- [x] **Step 2: Dry-run a migrated skill — expect it now installs from root layout**

Run (PowerShell):
```powershell
.\install-skills.bat -n smoke-test remote-claude
```
Expected: an `update`/`unchanged` line for each, no `skip ... no SKILL.md`. For remote-claude the diff may show `tests/` being removed from the installed copy — that is correct (now excluded).

- [x] **Step 3: Commit the installer changes**

Run (Bash tool):
```bash
git add install-skills.sh install-skills.bat
git commit -m "refactor: drop skill-draft layout from installers

All skills are root layout now; remove the dual-path branch and the
skill-draft exclude.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3: Swap the validator engine to agentskills

Replace the hand-rolled frontmatter parser with a thin fleet wrapper around `agentskills validate`. Keep the validator on PATH locally via the scratch venv so integration tests run:
```
.claude/spikes/skills-ref-verify/Scripts/  (Windows)  — contains agentskills.exe
```
Add it to PATH for the test runs, e.g. (PowerShell): `$env:PATH = "$PWD\.claude\spikes\skills-ref-verify\Scripts;$env:PATH"`.

### Task 3.1: Rename the script and its tests (preserve history)

**Files:** Rename `scripts/validate_skill_frontmatter.py` → `scripts/validate_skills.py`; `scripts/test_validate_skill_frontmatter.py` → `scripts/test_validate_skills.py`

- [ ] **Step 1: git mv both files**

Run (Bash tool):
```bash
cd /c/Users/mtsch/skills-dev
git mv scripts/validate_skill_frontmatter.py scripts/validate_skills.py
git mv scripts/test_validate_skill_frontmatter.py scripts/test_validate_skills.py
```

### Task 3.2: Rewrite the test file for the new contract (TDD — tests first)

**Files:** Overwrite `scripts/test_validate_skills.py`

- [ ] **Step 1: Replace the entire test file with this content**

```python
#!/usr/bin/env python3
"""Tests for validate_skills.

Fleet-logic tests inject a fake runner and need no external tools. Integration
tests invoke the real `agentskills` binary and are skipped if it isn't on PATH.

Runs under pytest, or standalone: python scripts/test_validate_skills.py
(no third-party dependency).
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_skills as validator


def _gitmodules(paths):
    return "".join(
        f'[submodule "{p}"]\n\tpath = {p}\n\turl = ../skills-{p}.git\n' for p in paths
    )


def _good_skill(name):
    return f'---\nname: {name}\ndescription: "A valid one-line description."\n---\n\n# Title\n'


def _make_repo(skills):
    """skills: dict name -> SKILL.md text | None (empty dir) | dict (files, no SKILL.md)."""
    root = Path(tempfile.mkdtemp())
    (root / ".gitmodules").write_text(_gitmodules(list(skills)), encoding="utf-8")
    for name, content in skills.items():
        d = root / name
        if content is None:
            d.mkdir(parents=True, exist_ok=True)
        elif isinstance(content, dict):
            d.mkdir(parents=True, exist_ok=True)
            for filename, body in content.items():
                (d / filename).write_text(body, encoding="utf-8")
        else:
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(content, encoding="utf-8")
    return root


def _pass_runner(skill_dir):
    return (0, f"Valid skill: {skill_dir}")


def _fail_runner(skill_dir):
    return (1, f"Validation failed for {skill_dir}:\n  - some rule violated")


# --- parse_submodule_paths ---

def test_parse_submodule_paths_reads_every_path():
    assert validator.parse_submodule_paths(_gitmodules(["foo", "bar-baz"])) == ["foo", "bar-baz"]


def test_parse_submodule_paths_empty_returns_empty_list():
    assert validator.parse_submodule_paths("") == []


# --- validate_skill fleet logic (injected runner, no external tool) ---

def test_good_skill_passes():
    repo = _make_repo({"alpha": _good_skill("alpha")})
    assert validator.validate_skill(repo, "alpha", runner=_pass_runner) == []


def test_invalid_skill_surfaces_runner_output():
    repo = _make_repo({"alpha": _good_skill("alpha")})
    errors = validator.validate_skill(repo, "alpha", runner=_fail_runner)
    assert errors, "a non-zero runner exit must surface as errors"
    assert all(e.startswith("alpha:") for e in errors), errors
    assert any("some rule violated" in e for e in errors), errors


def test_empty_submodule_dir_is_an_error():
    repo = _make_repo({"alpha": None})
    errors = validator.validate_skill(repo, "alpha", runner=_pass_runner)
    assert errors and any("check" in e.lower() for e in errors), errors


def test_wip_submodule_with_content_but_no_skill_md_is_skipped():
    repo = _make_repo({"alpha": {"HANDOFF.md": "wip notes\n", "LICENSE": "x\n"}})
    assert validator.validate_skill(repo, "alpha", runner=_pass_runner) == []


# --- validate_repo / evaluate ---

def test_validate_repo_counts_validated_skills():
    repo = _make_repo({"alpha": _good_skill("alpha"), "beta": _good_skill("beta")})
    errors, validated, skipped = validator.validate_repo(repo, runner=_pass_runner)
    assert errors == [] and validated == 2 and skipped == []


def test_validate_repo_reports_skipped_wip():
    repo = _make_repo({"alpha": _good_skill("alpha"), "wip": {"HANDOFF.md": "n\n"}})
    errors, validated, skipped = validator.validate_repo(repo, runner=_pass_runner)
    assert errors == [] and validated == 1 and skipped == ["wip"]


def test_evaluate_clean_repo_exits_zero():
    repo = _make_repo({"alpha": _good_skill("alpha")})
    code, _lines = validator.evaluate(repo, runner=_pass_runner)
    assert code == 0


def test_evaluate_invalid_repo_exits_one():
    repo = _make_repo({"alpha": _good_skill("alpha")})
    code, _lines = validator.evaluate(repo, runner=_fail_runner)
    assert code == 1


def test_evaluate_broken_checkout_empty_dirs_exits_one():
    code, _lines = validator.evaluate(_make_repo({"alpha": None, "beta": None}), runner=_pass_runner)
    assert code == 1


def test_evaluate_no_submodules_refuses_vacuous_pass():
    repo = Path(tempfile.mkdtemp())
    (repo / ".gitmodules").write_text("", encoding="utf-8")
    code, lines = validator.evaluate(repo, runner=_pass_runner)
    assert code == 2, "an empty submodule set must not pass — that hides a broken checkout"
    assert any("vacuous" in line.lower() for line in lines)


# --- integration: the real agentskills binary (skipped if not installed) ---

_AGENTSKILLS = shutil.which("agentskills")


def test_integration_real_good_skill():
    if _AGENTSKILLS is None:
        print("SKIP test_integration_real_good_skill (agentskills not on PATH)")
        return
    repo = _make_repo({"alpha": _good_skill("alpha")})
    assert validator.validate_skill(repo, "alpha") == []


def test_integration_real_bad_skill_name_mismatch():
    if _AGENTSKILLS is None:
        print("SKIP test_integration_real_bad_skill_name_mismatch (agentskills not on PATH)")
        return
    repo = _make_repo({"alpha": _good_skill("not-alpha")})
    errors = validator.validate_skill(repo, "alpha")
    assert errors, "agentskills must reject a skill whose name != parent dir"


def _run_all():
    tests = [(name, obj) for name, obj in sorted(globals().items())
             if name.startswith("test_") and callable(obj)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as exc:
            failures.append((name, f"AssertionError: {exc}"))
            print(f"FAIL {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((name, f"{type(exc).__name__}: {exc}"))
            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_all())
```

- [ ] **Step 2: Run the tests — expect failure (validate_skills still has the old API)**

Run (PowerShell):
```powershell
python scripts\test_validate_skills.py
```
Expected: failures/errors — the old module has no `runner=` parameter and still imports `yaml`. This confirms the tests drive the rewrite.

### Task 3.3: Rewrite the validator module

**Files:** Overwrite `scripts/validate_skills.py`

- [ ] **Step 1: Replace the entire module with this content**

```python
#!/usr/bin/env python3
"""Validate every skill's SKILL.md using the official Agent Skills validator.

Each top-level submodule in this repo is a skill with a SKILL.md at its root
(root layout). Per-skill validation is delegated to `agentskills validate`
(the console script from the pinned `skills-ref` PyPI package), which strict-
parses the YAML frontmatter and enforces the spec's naming/field rules.

This module keeps only the *fleet* logic the per-skill validator can't know:

  - the set of skills comes from `.gitmodules`, not from disk, so a broken
    recursive checkout can't pass vacuously;
  - empty/missing dir        -> ERROR (broken checkout);
  - content but no SKILL.md  -> SKIPPED (a WIP submodule, not a skill yet);
  - has a SKILL.md           -> handed to `agentskills validate`.

Exit codes: 0 = all valid, 1 = validation errors, 2 = nothing validated.

Run from anywhere:  python scripts/validate_skills.py
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

_PATH_LINE = re.compile(r"^\s*path\s*=\s*(.+?)\s*$", re.MULTILINE)


def parse_submodule_paths(gitmodules_text):
    """Return the ordered list of submodule paths declared in a .gitmodules file."""
    return _PATH_LINE.findall(gitmodules_text)


def find_skill_md(skill_dir: Path):
    """Return the root SKILL.md for a skill dir, or None if absent."""
    candidate = skill_dir / "SKILL.md"
    return candidate if candidate.is_file() else None


def has_content(skill_dir: Path):
    """True if the dir holds any file other than .git (i.e. it checked out)."""
    if not skill_dir.is_dir():
        return False
    return any(entry.name != ".git" for entry in skill_dir.iterdir())


def run_agentskills(skill_dir: Path):
    """Validate one skill dir with `agentskills validate`. Returns (exit_code, output).

    Raises RuntimeError if the `agentskills` console script isn't on PATH — a
    missing validator must fail loudly, never silently pass.
    """
    executable = shutil.which("agentskills")
    if executable is None:
        raise RuntimeError(
            "the 'agentskills' command was not found on PATH; "
            "install it with `pip install skills-ref==0.1.1`"
        )
    completed = subprocess.run(
        [executable, "validate", str(skill_dir)],
        capture_output=True,
        text=True,
    )
    return (completed.returncode, (completed.stdout + completed.stderr).strip())


def validate_skill(repo_root: Path, path: str, runner=run_agentskills):
    """Validate one skill. Returns a list of error strings ([] if clean or skipped).

    `runner(skill_dir) -> (exit_code, output)` is injected so the fleet logic is
    unit-testable without the real validator installed.
    """
    skill_dir = repo_root / path
    if find_skill_md(skill_dir) is None:
        if has_content(skill_dir):
            return []  # WIP submodule, not an authored skill yet — skip, not an error
        return [f"{path}: empty submodule dir, no SKILL.md — checkout looks broken"]

    code, output = runner(skill_dir)
    if code == 0:
        return []
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if lines:
        return [f"{path}: {line}" for line in lines]
    return [f"{path}: skills-ref reported invalid (exit {code})"]


def validate_repo(repo_root: Path, runner=run_agentskills):
    """Validate every skill declared in .gitmodules.

    Returns (errors, validated_count, skipped) where validated_count is the
    number of submodules that had a SKILL.md, and skipped lists WIP submodules.
    """
    gitmodules = repo_root / ".gitmodules"
    if not gitmodules.is_file():
        return ([f"{repo_root}: no .gitmodules file found"], 0, [])

    paths = parse_submodule_paths(gitmodules.read_text(encoding="utf-8"))
    errors = []
    validated = 0
    skipped = []
    for path in paths:
        skill_errors = validate_skill(repo_root, path, runner=runner)
        if find_skill_md(repo_root / path) is not None:
            validated += 1
        elif not skill_errors:
            skipped.append(path)
        errors.extend(skill_errors)
    return (errors, validated, skipped)


def evaluate(repo_root: Path, runner=run_agentskills):
    """Run validation and return (exit_code, output_lines)."""
    errors, validated, skipped = validate_repo(repo_root, runner=runner)
    notices = [f"note: skipped {name} (submodule has no SKILL.md yet)" for name in skipped]
    if errors:
        return (1, [f"skill validation failed ({len(errors)} issue(s)):",
                    *(f"  - {error}" for error in errors), *notices])
    if validated == 0:
        return (2, ["no skills with a SKILL.md were validated — refusing to pass "
                    "vacuously (is the checkout broken?)", *notices])
    return (0, [f"OK: all {validated} skills valid (agentskills)", *notices])


def main():
    repo_root = Path(__file__).resolve().parent.parent
    code, lines = evaluate(repo_root)
    print("\n".join(lines))
    sys.exit(code)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the tests with agentskills on PATH — expect all pass**

Run (PowerShell):
```powershell
$env:PATH = "$PWD\.claude\spikes\skills-ref-verify\Scripts;$env:PATH"
python scripts\test_validate_skills.py
```
Expected: `PASS` for every test (including the two integration tests — `agentskills` is on PATH), ending `N/N passed`.

- [ ] **Step 3: Run the validator against the real repo — expect all skills valid**

Run (PowerShell, with agentskills on PATH from Step 2):
```powershell
python scripts\validate_skills.py
```
Expected: `OK: all 16 skills valid (agentskills)` plus a `note: skipped ...` for any WIP submodule (e.g. `review-in-parallel-pipelines`, which has no SKILL.md). Exit 0.

- [ ] **Step 4: Commit the validator swap**

Run (Bash tool):
```bash
git add scripts/validate_skills.py scripts/test_validate_skills.py
git commit -m "refactor: delegate skill validation to agentskills (skills-ref)

Replace the hand-rolled frontmatter parser with a thin fleet wrapper
around 'agentskills validate'. Keep the .gitmodules iteration, the
anti-vacuous guard, the WIP-skip and empty-dir checks; drop the YAML
parsing and field checks (now the validator's job). Runner seam keeps
fleet logic unit-testable offline; integration tests exercise the real
binary when present.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4: CI wiring + content linting + end-to-end verification

### Task 4.1: Point the CI validation job at agentskills

**Files:** Modify `.gitea/workflows/lint.yml`

- [ ] **Step 1: Rewrite the `frontmatter` job as `validate-skills`**

Replace the `frontmatter:` job (currently lines 20–36) with:
```yaml
  validate-skills:
    # Validate every skill's SKILL.md with the official Agent Skills validator
    # (agentskills, from the pinned skills-ref package). Catches strict-YAML
    # parse failures (apostrophe-in-single-quote, flattened block scalar) plus
    # the spec's naming/field rules. Needs submodules checked out.
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive
      - uses: actions/setup-python@v5
        with:
          python-version: '3.x'
      - run: pip install skills-ref==0.1.1
      - name: Validate every skill with agentskills
        run: python scripts/validate_skills.py
```

- [ ] **Step 2: Make the markdown job lint skill content too**

In the `markdown:` job, change:
```yaml
      - uses: actions/checkout@v4
        with:
          submodules: false
```
to:
```yaml
      - uses: actions/checkout@v4
        with:
          submodules: recursive
```

### Task 4.2: Extend the root markdownlint globs to skill content

**Files:** Modify `.markdownlint-cli2.jsonc` (repo root)

- [ ] **Step 1: Broaden `globs`**

Change:
```jsonc
  "globs": ["*.md", "docs/**/*.md"],
```
to:
```jsonc
  "globs": ["*.md", "docs/**/*.md", "*/*.md", "*/references/**/*.md"],
```
(`*/*.md` catches each skill's `SKILL.md`, `README.md`, and loose refs like unity's `batch-mode-commands.md`; `*/references/**/*.md` catches nested reference docs. Per-skill `.markdownlint-cli2.jsonc` rule overrides still merge per-directory; `ignores: ["node_modules"]` backstops fixtures.)

### Task 4.3: Verify content lint locally and fix any surfaced violations

- [ ] **Step 1: Run markdownlint with the new globs from the repo root**

Run (PowerShell):
```powershell
npx --yes markdownlint-cli2
```
Expected: it now lints skill `SKILL.md` + `references/` files. **If violations appear**, they are real (this content was never linted by the umbrella before). Fix each in its **submodule** repo (edit the file, then in that submodule: commit + `git push origin main` + `git push github main`), then bump that pointer in skills-dev (`git add <skill>`). If zero violations, the per-skill repos were already clean — proceed.

- [ ] **Step 2: Re-run until clean**

Run (PowerShell):
```powershell
npx --yes markdownlint-cli2
```
Expected: exit 0, no violations.

### Task 4.4: Commit the CI + config changes

- [ ] **Step 1: Commit**

Run (Bash tool):
```bash
git add .gitea/workflows/lint.yml .markdownlint-cli2.jsonc
# also stage any submodule pointer bumps from 4.3 fixes, if any
git commit -m "ci: validate skills with agentskills + lint skill content

Swap the frontmatter job to 'agentskills validate' (pinned
skills-ref==0.1.1) over recursive submodules; extend the markdownlint
job to skill SKILL.md + references/ content (recursive checkout, root
globs broadened). Two complementary gates: agentskills = frontmatter +
naming, markdownlint = prose.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 4.5: End-to-end verification

- [ ] **Step 1: Reinstall skills locally (layouts changed)**

Run (PowerShell):
```powershell
.\install-skills.bat -y
```
Expected: each skill installs/updates without `skip`; migrated skills now install from root layout.

- [ ] **Step 2: Push the branch and confirm CI is green**

Run (Bash tool):
```bash
git push -u origin skills-ref-validation-upgrade
```
Then watch the Gitea Actions run for this branch. Expected: both `validate-skills` and `markdown` jobs green. (If using the gitea MCP, poll the run status; otherwise check the Actions UI.)

- [ ] **Step 3: Clean up the scratch venv**

Run (PowerShell):
```powershell
Remove-Item -Recurse -Force .\.claude\spikes\skills-ref-verify
```
(It's gitignored, so this is tidiness only.)

- [ ] **Step 4: Update CLAUDE.md layout note**

**Files:** Modify `CLAUDE.md` (the "Layout" section)

The section currently says the skill-draft layout is "deprecated" and the installer "detects which layout is in use." Update it to state all skills use root layout and the installer is single-path. Replace the Layout section body with:
```markdown
Per-skill repos use the **root layout**: `SKILL.md` at the repo root, plus
`evals/`, `README.md`, and `workspace/` (gitignored). The installer
(`install-skills.{sh,bat}`) installs from the skill root, excluding dev-only
files (`evals/`, `tests/`, `README.md`, `LICENSE`, etc.). Skill validation is
delegated to the official Agent Skills validator: CI runs `agentskills validate`
(pinned `skills-ref==0.1.1`) over every `.gitmodules` skill via
`scripts/validate_skills.py`, which keeps the fleet-level anti-vacuous / WIP-skip
guards; markdownlint covers skill prose content.
```

- [ ] **Step 5: Commit the docs update**

Run (Bash tool):
```bash
git add CLAUDE.md
git commit -m "docs: record root-layout-only + agentskills validation

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Finish the branch**

Use superpowers:finishing-a-development-branch to decide merge/PR. Before deletion, fold any durable insight into CLAUDE.md (done in Step 4) and update the relevant memory notes: `project_skills_dev_root_layout` (migration complete), `project_skill_validation_gate` (now agentskills-backed).

---

## Notes for the implementer

- **Multi-repo pushes:** Phase 1 + any 4.3 fixes push to 8 submodule repos on two remotes each. Commit as **Matt Schoen** (default identity) — bot identities are only for PRs where Gitea's self-approval block matters. Watch for the pr-crew bot advancing `origin/main`; `git pull --ff-only` before re-pushing if a push is rejected.
- **Worktree caveat:** git worktrees and submodules-with-their-own-`.git` interact badly. Prefer **inline execution on the `skills-ref-validation-upgrade` branch** (created in Task 1.3) over a worktree.
- **The `running-spikes` submodule** shows as modified at session start — that's pre-existing and unrelated; do not stage it.
