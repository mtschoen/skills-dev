# Installer Allowlist Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the installer's failing exclude-list with a git-native top-level allowlist so generated junk (`__pycache__` etc.) can never ship, and make every install a true mirror that purges cruft left by prior installs.

**Architecture:** For each skill, derive the file set from `git -C <skill> ls-files` (tracked files only — untracked junk is structurally excluded), filter to a top-level allowlist (`SKILL.md` + `scripts/` + `references/` + `assets/` plus extras from an optional `.skillpack` manifest), copy the surviving tracked paths from the working tree into a temp staging dir (so uncommitted edits still install), then mirror staging → destination (removing dest entries absent from staging). Keep dual bash + batch — no Python, since git is already a hard dependency (skills are submodules). `cost-estimator/scripts/` is restructured to runtime-only so the allowlist needs no within-directory pruning.

**Tech Stack:** Bash + Windows batch; `git ls-files`; `cp`/`diff`/`mktemp` (bash) and `robocopy /MIR`/`copy` (batch); pytest (cost-estimator).

---

## Phase 4: Docs + umbrella integration

### Task 6: Update `CLAUDE.md` to describe the allowlist + `.skillpack`

**Files:**
- Modify: `CLAUDE.md` (the "Layout" section; add a `.skillpack` note)

- [x] **Step 1: Replace the "Layout" section body**

Find the paragraph in `CLAUDE.md` under `## Layout` that begins "Per-skill repos use the **root layout**" and currently describes the installer as "excluding dev-only files (`evals/`, `tests/`, ...)". Replace that installer description with:

```markdown
The installer (`install-skills.{sh,bat}`) ships only **git-tracked** files
(`git ls-files`), filtered to a **top-level allowlist**: `SKILL.md` +
`scripts/` + `references/` + `assets/`, plus any extra top-level entries a
skill declares in an optional `.skillpack` manifest at its repo root (one
entry per line, `#` comments). Shipping tracked-only means generated junk
(`__pycache__`, `.pytest_cache`) can never leak; the allowlist means dev dirs
(`evals/`, `tests/`, `workspace/`, `README.md`, `LICENSE`) are excluded by
omission. Each install mirrors a clean staging tree into the destination, so
files left by older installs are removed. Skill validation is delegated to the
official Agent Skills validator: CI runs `agentskills validate` (pinned
`skills-ref==0.1.1`) over every `.gitmodules` skill via
`scripts/validate_skills.py`, which keeps the fleet-level anti-vacuous / WIP-skip
guards; markdownlint covers skill prose.
```

- [x] **Step 2: Add a `.skillpack` bullet under "Naming conventions"**

Append to the "Naming conventions" list:
```markdown
- A skill ships extra top-level content (beyond `SKILL.md` + `scripts/` +
  `references/` + `assets/`) by listing it in a `.skillpack` file at the skill's
  repo root. Current users: `progress-beacon` (`hooks/`), `cost-estimator`
  (`REPORT_TEMPLATE.md`). The `.skillpack` file is itself never installed.
```

- [x] **Step 3: Commit the docs update**

```bash
git add CLAUDE.md
git commit -m "docs: describe installer allowlist + .skillpack manifest

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 7: Full-fleet dry-run, submodule-pointer bumps, cleanup verification

**Files:**
- Modify: umbrella submodule pointers for `cost-estimator`, `progress-beacon`

- [ ] **Step 1: Dry-run the real fleet on both installers and eyeball removals**

Run:
```bash
bash install-skills.sh -n --claude
```
Expected: for `cost-estimator`, the change list shows the leaked cruft as removals — `Only in (installed)` lines for `scripts/__pycache__`, `.pytest_cache`, `reports`, `screenshot*.png`, and the relocated dev scripts. For most skills: `unchanged`.

Then on Windows:
```bash
cmd.exe /c install-skills.bat -n --claude
```
Expected: the same cruft appears as `*EXTRA` (robocopy's removal marker) for `cost-estimator`.

- [ ] **Step 2: Apply the real install and confirm the cruft is gone**

Run:
```bash
bash install-skills.sh -y --claude cost-estimator
ls -a ~/.claude/skills/cost-estimator ~/.claude/skills/cost-estimator/scripts
```
Expected: no `__pycache__`, `.pytest_cache`, `reports/`, `screenshot*.png`, no `tests/`, no `README.md`, no `.skillpack`; `REPORT_TEMPLATE.md` and `scripts/*.py` (runtime only) present.

Verify a manifest skill:
```bash
bash install-skills.sh -y --claude progress-beacon
ls ~/.claude/skills/progress-beacon/hooks
```
Expected: `hooks/` present with `prompt-reminder.sh` and `recency-nudge.sh`.

- [ ] **Step 3: Stage the submodule-pointer bumps in the umbrella**

The Phase 1–2 submodule commits moved the recorded HEADs. Stage the pointers:
```bash
git add cost-estimator progress-beacon
git status --short    # expect: M cost-estimator, M progress-beacon
```

- [ ] **Step 4: Commit the umbrella submodule-pointer bumps**

```bash
git commit -m "chore: bump cost-estimator + progress-beacon (scripts/ restructure, .skillpack)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5: Final full harness run**

```bash
bash tests/test-install.sh
```
Expected: `ALL TESTS PASSED`. This is the verification gate before declaring the branch done.

**Pushing** (`scripts/push-all.{sh,bat}`) and branch integration are deferred to branch-finish (superpowers:finishing-a-development-branch), per the repo convention of pushing only when asked.
