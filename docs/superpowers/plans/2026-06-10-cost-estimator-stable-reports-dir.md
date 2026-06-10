# Cost-Estimator Stable Reports Directory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all cost-estimator generated output (sessions.csv, daily.csv, HTML charts, saved markdown reports) out of the installed skill tree to a stable user-level directory that skill redeploys can never touch.

**Architecture:** Add one shared helper, `reports_directory()`, to `scripts/roots.py` (the stdlib-only shared module every script can already import). Default: `~/.claude/cost-estimator/reports/`, overridable via the `CLAUDE_COST_REPORTS_DIR` environment variable (naming mirrors the existing `CLAUDE_COST_ROOTS`). Point every script's default output/input path at the helper; explicit `--out`/`--csv` flags keep working unchanged. Update SKILL.md and README.md. Finally (optional, umbrella repo) retire the installer's `reports/`-preservation special case, which becomes dead weight once nothing writes into the install tree.

**Tech Stack:** Python 3 stdlib only, pytest. Two repos are touched: the `skills-cost-estimator` submodule at `~/skills-dev/cost-estimator` (Phases 1-4) and the `skills-dev` umbrella (Phase 5, optional).

---

## Context (why)

On 2026-06-09 a skill redeploy wiped `~/.claude/skills/cost-estimator/reports/`, deleting generated CSVs and saved reports. The installer was since patched to *preserve* `reports/` across installs (see `install-skills.sh` `IGNORE_PATTERNS`, `install-skills.bat` `ROBO_EXCL`), but that is a band-aid: generated data still lives inside an installer-managed tree, and the preservation list must be kept in sync forever. The real fix is to write output somewhere the installer never looks.

Current hard-coded `<skill-root>/reports/` locations (verified 2026-06-10):

| File | Lines | What |
|---|---|---|
| `scripts/analyze-month.py` | 203-205 | `--out` default |
| `scripts/summarize.py` | 42-45 | `--csv` default |
| `scripts/plot-session.py` | 18, 257, 289-293 | docstring, `--out` help, fallback path |
| `scripts/plot-trend.py` | 233-234 | `DEFAULT_CSV_PATH`, `DEFAULT_OUT_DIR` |
| `scripts/plot-compare.py` | 35-36 | `DEFAULT_CSV_PATH`, `DEFAULT_OUT_DIR` |
| `SKILL.md` | 98, 114, 131, 165-173, 260, 275, 288-289 | step text + tool reference + layout |
| `README.md` | 32, 143-144 | usage + layout |

NOT in scope: `dev/regen-screenshots.{sh,bat}` pass explicit repo-relative `--out reports/_*.html` for dev-only screenshot fixtures; that stays repo-local on purpose. The source repo's `.gitignore` keeps `reports/` ignored for those dev artifacts.

## Phase 1: Shared helper (repo: `~/skills-dev/cost-estimator`)

### Task 1: `reports_directory()` in `scripts/roots.py`

**Files:**
- Modify: `scripts/roots.py` (imports at lines 9-13, new function at end)
- Test: `tests/test_roots.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_roots.py` (it already inserts `scripts/` on `sys.path` and does `import roots`):

```python
def test_reports_directory_default_is_outside_skill_tree(monkeypatch):
    monkeypatch.delenv("CLAUDE_COST_REPORTS_DIR", raising=False)
    result = roots.reports_directory()
    assert result == Path.home() / ".claude" / "cost-estimator" / "reports"


def test_reports_directory_environment_override(monkeypatch):
    monkeypatch.setenv("CLAUDE_COST_REPORTS_DIR", "/custom/spot")
    assert roots.reports_directory() == Path("/custom/spot")


def test_reports_directory_override_expands_user(monkeypatch):
    monkeypatch.setenv("CLAUDE_COST_REPORTS_DIR", "~/elsewhere")
    assert roots.reports_directory() == Path.home() / "elsewhere"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_roots.py -v` (from the submodule root)
Expected: 3 FAILURES with `AttributeError: module 'roots' has no attribute 'reports_directory'`

- [ ] **Step 3: Implement the helper**

In `scripts/roots.py`, add `import os` to the import block (it currently imports only `sys`, `datetime`, `pathlib`), then add at module level:

```python
def reports_directory() -> Path:
    """Stable output directory for CSVs, HTML charts, and saved reports.

    Lives OUTSIDE the installed skill tree so skill reinstalls can never
    delete generated data. Override with CLAUDE_COST_REPORTS_DIR.
    """
    override = os.environ.get("CLAUDE_COST_REPORTS_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "cost-estimator" / "reports"
```

(Callers create the directory on demand, exactly as they did for `<skill-root>/reports/`. The helper stays pure so importing it has no side effects.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_roots.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/roots.py tests/test_roots.py
git commit -m "feat: add reports_directory() helper for stable output path"
```

## Phase 2: Repoint script defaults

All five scripts below already do (or will get) the `sys.path.insert(0, str(Path(__file__).parent))` dance before sibling imports; match each file's existing `# noqa: E402` comment style.

### Task 2: `analyze-month.py`

**Files:**
- Modify: `scripts/analyze-month.py:43-47` (import block), `:203-205` (`--out` default)

- [ ] **Step 1: Extend the existing roots import**

```python
from roots import (  # noqa: E402  -- after sys.path manipulation
    _resolve_roots,
    date_bounds,
    month_bounds,
    reports_directory,
)
```

- [ ] **Step 2: Replace the `--out` default**

```python
    parser.add_argument("--out",
                        default=str(reports_directory()),
                        help="Output directory for CSVs "
                             "(default: ~/.claude/cost-estimator/reports/, "
                             "override dir via CLAUDE_COST_REPORTS_DIR)")
```

- [ ] **Step 3: Verify the writer creates the directory**

Confirm the CSV-writing code calls `mkdir(parents=True, exist_ok=True)` on the output directory before writing (it created `<skill-root>/reports/` on demand before; if that mkdir is missing for the new deeper path, add it where the CSVs are written).

- [ ] **Step 4: Smoke test**

Run: `python scripts/analyze-month.py "$HOME/.claude/projects" --month 2026-06`
Expected: `Wrote .../​.claude/cost-estimator/reports/sessions.csv` (home-anchored path, NOT under the repo)

- [ ] **Step 5: Commit**

```bash
git add scripts/analyze-month.py
git commit -m "feat: analyze-month writes CSVs to stable reports directory"
```

### Task 3: `summarize.py`

**Files:**
- Modify: `scripts/summarize.py:17-22` (imports), `:42-45` (`--csv` default)

- [ ] **Step 1: Add the sibling-import dance (this script has none today)**

```python
import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from roots import reports_directory  # noqa: E402  -- after sys.path manipulation
```

- [ ] **Step 2: Replace the `--csv` default**

```python
    parser.add_argument("--csv",
                        default=str(reports_directory() / "sessions.csv"),
                        help="sessions.csv path produced by analyze-month.py "
                             "(default: ~/.claude/cost-estimator/reports/sessions.csv)")
```

- [ ] **Step 3: Smoke test**

Run: `python scripts/summarize.py` (after Task 2's smoke test, so the CSV exists)
Expected: summary prints from the new location with no `--csv` flag

- [ ] **Step 4: Commit**

```bash
git add scripts/summarize.py
git commit -m "feat: summarize reads sessions.csv from stable reports directory"
```

### Task 4: `plot-session.py`

**Files:**
- Modify: `scripts/plot-session.py:18` (docstring), `:31-33` (imports), `:256-257` (help), `:289-293` (fallback)

- [ ] **Step 1: Add import**

```python
sys.path.insert(0, str(Path(__file__).parent))
from pricing import iter_assistant_turns, model_family  # noqa: E402
from chart_runtime import chartjs_script_tags  # noqa: E402
from roots import reports_directory  # noqa: E402
```

- [ ] **Step 2: Replace the output fallback (lines 289-293)**

```python
    if arguments.out:
        output_path = Path(arguments.out)
    else:
        output_path = reports_directory() / f"session-{session_id[:8]}.html"
```

(The existing `output_path.parent.mkdir(parents=True, exist_ok=True)` two lines below already handles directory creation.)

- [ ] **Step 3: Update the docstring (line 18) and `--out` help (line 257)** to say `~/.claude/cost-estimator/reports/session-<prefix>.html`.

- [ ] **Step 4: Smoke test**

Run: `python scripts/plot-session.py <any-recent-session-id-prefix>`
Expected: `Wrote .../​.claude/cost-estimator/reports/session-<prefix>.html`

- [ ] **Step 5: Commit**

```bash
git add scripts/plot-session.py
git commit -m "feat: plot-session writes HTML to stable reports directory"
```

### Task 5: `plot-trend.py` and `plot-compare.py`

**Files:**
- Modify: `scripts/plot-trend.py:30-32` (imports), `:233-234` (constants)
- Modify: `scripts/plot-compare.py:28-33` (imports), `:35-36` (constants)

- [ ] **Step 1: Add `from roots import reports_directory  # noqa: E402` after each file's existing post-`sys.path` imports**

- [ ] **Step 2: Replace both files' module constants (identical change in each)**

```python
DEFAULT_CSV_PATH = reports_directory() / "sessions.csv"
DEFAULT_OUT_DIR = reports_directory()
```

- [ ] **Step 3: Verify each file mkdirs `DEFAULT_OUT_DIR` (or the resolved out path's parent) before writing; add `output_path.parent.mkdir(parents=True, exist_ok=True)` if absent**

- [ ] **Step 4: Smoke test**

Run: `python scripts/plot-trend.py --month 2026-06` and `python scripts/plot-compare.py --month 2026-06`
Expected: both read sessions.csv from and write HTML to `~/.claude/cost-estimator/reports/`

- [ ] **Step 5: Run the full test suite and lint gate**

Run: `python -m pytest tests/ -v` then the repo's lint (`ruff check scripts/ tests/` if configured here; CI's lint.yml is authoritative). Also `aislop scan .` per umbrella convention.
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add scripts/plot-trend.py scripts/plot-compare.py
git commit -m "feat: trend/compare plots use stable reports directory"
```

## Phase 3: Documentation

### Task 6: SKILL.md and README.md

**Files:**
- Modify: `SKILL.md` (lines 98, 114, 131, 165-173, 260, 275, 288-289)
- Modify: `README.md` (lines 32, 143-144)

- [ ] **Step 1: Introduce the location once, early in SKILL.md** (near the workflow's first output-producing step): state that all generated output lands in `~/.claude/cost-estimator/reports/` (override: `CLAUDE_COST_REPORTS_DIR`), then replace every later `<skill-root>/reports/...` mention with `<reports-dir>/...` or the literal path.

- [ ] **Step 2: Rewrite SKILL.md step 10 (lines 165-173)**: the "That folder (and everything in it) is gitignored" sentence is obsolete; replace with a note that the folder lives outside the skill install and survives reinstalls. Update the `summarize.py > .../summary.txt` redirect example to the new path.

- [ ] **Step 3: Rewrite the layout bullets** (SKILL.md 288-289, README.md 143-144): `reports/` in the repo is now dev-screenshot scratch only; generated data lives in `~/.claude/cost-estimator/reports/`. Update README.md line 32 the same way.

- [ ] **Step 4: Portability-guard check**

Run the umbrella validator over this skill: `python ../scripts/validate_skills.py` (from the submodule, or run umbrella CI's command from `~/skills-dev`). The new `~/.claude/cost-estimator/reports/` strings are user-generic (tilde-anchored), which the deny patterns should accept; if the guard flags them, fix the wording rather than exempting.

- [ ] **Step 5: Run docs-update check and commit**

```bash
git add SKILL.md README.md
git commit -m "docs: reports live in ~/.claude/cost-estimator/reports/"
```

## Phase 4: Rollout and data migration (per machine: chonkers, then llamabox)

### Task 7: Reinstall and migrate

- [ ] **Step 1: Reinstall the skill** from `~/skills-dev`: `./install-skills.sh cost-estimator` (llamabox) / `install-skills.bat cost-estimator` (chonkers).

- [ ] **Step 2: Move existing generated data** from `~/.claude/skills/cost-estimator/reports/` to `~/.claude/cost-estimator/reports/` (create the destination first). On chonkers this includes the full-history `sessions.csv` (3,069 rows) and `daily.csv` regenerated on 2026-06-10, plus any saved `*.md`/`*.html` reports.

- [ ] **Step 3: Smoke test on the installed copy**: `python ~/.claude/skills/cost-estimator/scripts/summarize.py` should find the migrated CSV with no flags.

- [ ] **Step 4: Push the submodule** (origin = Gitea, github = GitHub) and bump the submodule pointer in the umbrella per the skills-dev CLAUDE.md conventions.

## Phase 5 (OPTIONAL, repo: `~/skills-dev` umbrella): retire the installer band-aid

Only after BOTH machines have migrated (Phase 4) - removing the exclusion makes the mirror DELETE any `reports/` still sitting in an install destination.

### Task 8: Remove `reports` from the preservation lists

**Files:**
- Modify: `install-skills.sh:53` (`IGNORE_PATTERNS=(__pycache__ '*.pyc' '*.pyo' .pytest_cache reports)`) and the comments at lines 8-14, 48-52, 58 that mention reports
- Modify: `install-skills.bat:49` (`ROBO_EXCL`) and comments at lines 11-15, 44-48

- [ ] **Step 1: Decide whether to do this at all.** Keeping `reports` in the ignore list is harmless if other skills may someday write into their install dir; removing it keeps the installer honest (install tree = exactly what is shipped). Lean remove, but it is a judgment call for the executing session.

- [ ] **Step 2: Remove the `reports` entries and update the comments** in both scripts, keeping `__pycache__`/`*.pyc`/`.pytest_cache` (those are created by running installed scripts regardless).

- [ ] **Step 3: Dry-run check**: `./install-skills.sh -n cost-estimator` should show no `reports/` deletions on a migrated machine.

- [ ] **Step 4: Run umbrella gates** (`ruff check scripts/ tests/`, `shellcheck install-skills.sh`, `aislop ci .`) **and commit**

```bash
git add install-skills.sh install-skills.bat
git commit -m "chore: installer no longer needs to preserve reports/ (outputs moved to ~/.claude/cost-estimator/)"
```

## Open decisions locked in by this plan

- **Location:** `~/.claude/cost-estimator/reports/` (Claude-Code-adjacent data, survives reinstall; precedent: `~/.project_tracker/` for project-tracker). If the executing session prefers `~/.cost-estimator/`, change only `reports_directory()` and the doc strings - everything else flows through the helper.
- **Env var name:** `CLAUDE_COST_REPORTS_DIR`, mirroring the existing `CLAUDE_COST_ROOTS`.
- **No legacy fallback:** scripts do NOT silently fall back to `<skill-root>/reports/` if the new dir is empty. Migration is a one-time manual move (Phase 4). YAGNI.
