# Design Spec: Reconsidering One-Repo-Per-Skill (Monorepo vs. Families vs. Status Quo)

Status: Proposed Design Evaluation
Issue: Closes schoen/skills-dev#25
Date: 2026-08-19

## Executive Summary & Core Recommendation

When the skills ecosystem started with 5 skills, one git repository per skill provided clear separation and independent experimentation. At 25 skills, this architecture imposes a substantial configuration and maintenance tax that scales linearly with every added skill without providing corresponding value in practice.

A comprehensive audit conducted on 2026-08-19 surfaced significant silent drift:
- 5 skills with cross-forge divergence (merged PRs on GitHub missing from Gitea)
- 4 skills with broken remote configurations (missing GitHub push URLs)
- 11 repositories missing branch protections
- 22 stale local main branches detached from recorded pointers
- High friction on cross-cutting changes (e.g. the coordinated `fix/hook-offer-pointer` refactor required fanning out across 25 independent repos and PRs)

### The Verdict: Monorepo Wins Decisively

This design pass evaluates three architectural alternatives:
1. **Option A: Status Quo + Automated Scans** (Retain 25+ submodules; add scheduled drift detection)
2. **Option B: Skill Families** (Group skills into ~5 thematic repositories with submodules)
3. **Option C: Unified Monorepo** (Consolidate all skills directly into `skills-dev`; eliminate submodules entirely)

**Recommendation: Migrate to a Unified Monorepo (Option C).**

Skill Families (Option B) reduce the number of submodules by ~80%, but they retain 100% of the structural pain points: submodule synchronization traps, detached HEAD checkouts, dual-forge repository provisioning, multi-repo PR coordination, and relative submodule path fragility. Furthermore, family boundaries are inherently fuzzy and subject to ongoing taxonomy debates.

A Unified Monorepo (Option C) eliminates submodule overhead completely. It enables atomic cross-skill refactoring in a single commit/PR, simplifies authoring a new skill from an 8-step multi-forge ritual down to a simple directory creation, unifies CI into a single fast pipeline, and simplifies the installer logic.

---

## The Evidence: Why One-Repo-Per-Skill Failed to Scale

The 2026-08-19 audit demonstrated that independent repositories create an unmaintainable surface area:

| Maintenance Surface | 1-Repo-Per-Skill (25 skills) | Families (~5 repos) | Unified Monorepo (1 repo) |
|---|---|---|---|
| Remote endpoints (GitHub + Gitea) | 52 endpoints | 12 endpoints | 2 endpoints |
| Submodule entries in `.gitmodules` | 25 submodules | 5 submodules | 0 (none) |
| CI workflow definitions (`lint.yml`) | 26 workflows | 6 workflows | 1 workflow |
| Branch protection / ruleset policies | 26 configurations | 6 configurations | 1 configuration |
| Operations to add a new skill | 8 steps (API + remotes + submodule) | Add to family repo | 1 step (`mkdir`) |
| PRs for cross-skill refactors | 25 PRs + umbrella bump | ~5 PRs + umbrella bump | 1 PR (atomic) |
| Risk of detached HEAD / pointer drift | High (routine on pull) | Moderate | Zero |

### What One-Repo-Per-Skill Was Intended to Buy vs. Reality

1. **Independent history and issues:**
   - *Intended:* Clean per-skill commit histories and isolated issue trackers.
   - *Reality:* Most skill commits are minor prose adjustments, prompt tuning, or shared reference updates. Managing 25 issue trackers across two forges fragments context rather than organizing it.

2. **Selective installation:**
   - *Intended:* Allowing users to clone only the skills they need.
   - *Reality:* The runtime deployment tooling (`install-skills.sh` and `install-skills.bat`) already supports selective installation of specific skills (e.g. `./install-skills.sh smoke-test pushback`) regardless of source repository structure. The runtime destinations (`~/.agents/skills/`, `~/.claude/skills/`, `~/.gemini/config/skills/`, `<hermes>/skills/`) are always structured per-skill.

---

## Detailed Evaluation of the 5 Open Design Questions

### 1. History Preservation

**Question:** Is per-skill history worth preserving through the merge, and is the added complexity worth it?

**Analysis:**
- Commits in skill repositories contain valuable rationale for specific prompt formulations, edge-case handling in scripts, and eval evolutions.
- Preserving history is technically straightforward in Git using either `git subtree add` or `git filter-repo` before merging.
- A flat file copy would discard `git blame` context and commit timestamps, making future audits harder.

**Decision:**
- Preserve full commit history using `git subtree add` (or directory-prefix rewriting via `git filter-repo`).
- Because each skill repository has relatively few total commits (typically 10 - 50 commits each), merging all 25 histories into `skills-dev` will create a clean, compact combined commit graph of ~500 - 800 commits, with zero repository bloat.

### 2. Impact on Installers and Tooling

**Question:** How do `install-skills.sh`, `install-skills.bat`, and validation scripts change?

**Analysis:**
- **Current installer mechanism:**
  `install-skills.sh` scans `$SRC_ROOT/*/` for directories with a `.git` entry and a `SKILL.md`. It executes `git -C "$src" ls-files` inside each submodule to build the list of tracked files matching the allowlist (`SKILL.md`, `scripts/`, `references/`, `assets/`, plus `.skillpack`).
- **Monorepo installer mechanism:**
  The installer will scan `$SRC_ROOT/skills/*/` (or top-level `$SRC_ROOT/*/` ignoring reserved directories like `scripts/`, `tests/`, `ci/`, `.github/`).
  Instead of spawning 25 separate `git -C <submodule> ls-files` subprocesses, the installer can either query `git ls-files "$src"` against the umbrella repo root or perform a single fast `git ls-files` invocation.
- **Top-level allowlist and `.skillpack`:**
  The packaging semantics remain identical: only git-tracked files in the skill directory matching `SKILL.md`, `scripts/`, `references/`, `assets/`, and optional `.skillpack` entries are staged and mirrored.
- **Validation scripts (`scripts/validate_skills.py`, `scripts/check_config_drift.py`):**
  - `validate_skills.py`: Replaces the `.gitmodules` parser with a filesystem discovery of skill directories containing `SKILL.md`. Continues running `agentskills validate` and portability checks across all skills.
  - `check_config_drift.py`: The ~400 lines of submodule drift checks (checking 25 `.markdownlint-cli2.jsonc` files, 25 `lint.yml` files, and fleet ruff pins) become completely obsolete. The umbrella's single root configuration naturally governs all skills.
- **Sync scripts (`scripts/push-all.sh`, `scripts/pull-all.sh`):**
  - Obsoleted. Standard `git pull` and `git push` work directly on `skills-dev`.

### 3. Families vs. Single Monorepo

**Question:** Do families or a single repo win? Does separation buy anything concrete?

**Comparison:**

| Evaluation Criteria | Option B: Skill Families (~5 repos) | Option C: Unified Monorepo (1 repo) | Winner |
|---|---|---|---|
| **Submodule Overhead** | Retains 5 submodules; still requires `.gitmodules`, recursive cloning, and pointer bumps. | Eliminates submodules entirely. Zero pointer management. | **Monorepo** |
| **Cross-Skill Atomicity** | Refactors spanning multiple families still require multi-repo PR coordination. | 100% atomic commits across all skills and umbrella tooling. | **Monorepo** |
| **CI Cost & Simplicity** | 6 separate CI workflows to maintain and trigger on every push. | 1 unified CI workflow. Faster execution via test batching. | **Monorepo** |
| **New Skill Creation** | Must decide family placement; still requires multi-step repo setup if a new family is needed. | `mkdir skills/<name>` and write `SKILL.md`. | **Monorepo** |
| **Tooling Complexity** | Installer must handle 2-level directory tree (`<family>/<skill>/`). | Installer handles clean, flat skill list (`skills/<name>/`). | **Monorepo** |
| **Independent Release Cadence** | Theoretical advantage, but unused: skills are not versioned or distributed via package managers. | Perfect match for actual workflow: skills updated and installed continuously. | **Monorepo** |

**Conclusion:** Families provide no concrete technical advantages. They retain the operational failure modes of submodules while adding taxonomy ambiguity. A single monorepo wins across every operational dimension.

### 4. The Boundary Rule and Taxonomy Problem

**Question:** What is the boundary rule for families, and how do we prevent arbitrary classification?

**Analysis of Proposed Families:**
- Proposed: `completion`, `orchestration`, `project-lifecycle`, `memory`, `practice`.
- Real-world classification friction:
  - `cost-estimator`: Is it `orchestration` (measuring agent sessions), `practice` (harness discipline), or `tooling`?
  - `using-a-debugger`: Is it `practice` (debugging methodology) or `tooling` (language debuggers)?
  - `project-lock`: Is it `project-lifecycle` (project management) or `orchestration` (multi-agent locking)?
  - `unity-batchmode-worktree`: Is it `orchestration` (worktree collaboration), `practice`, or a domain-specific category?

**Conclusion:**
Boundaries between skill categories are fluid. Coupling repository boundaries to subjective semantic categories guarantees ongoing debate, cross-family dependencies, and awkward refactoring boundaries. In a monorepo, logical categorization can exist purely in documentation (e.g. `README.md` or metadata tags) without imposing rigid repository-level constraints.

### 5. Migration Cost vs. Status Quo (Scan vs. Restructure)

**Question:** Is maintaining automated drift scans cheaper than migrating?

**Analysis:**
- **Cost of Status Quo + Scans:**
  - Automated drift scans (`check_config_drift.py`, scheduled forge syncs) detect drift after it happens, but they cannot prevent it.
  - The cognitive and procedural friction remains: creating a new skill requires 8 manual steps across GitHub and Gitea APIs; pulling updates frequently results in detached HEAD states; fanning out changes across 25 repos wastes substantial agent and developer time.
  - As the ecosystem grows toward 50 skills, this friction becomes crippling.
- **Cost of Monorepo Migration:**
  - One-time migration script (preserving git history via subtree merges).
  - Updating `install-skills.sh`, `install-skills.bat`, and `validate_skills.py`.
  - Updating CI to run directly over `skills/`.
  - Archiving child repositories on GitHub and Gitea with a redirection notice.
  - Estimated migration effort: 1 focused implementation sprint.

**Conclusion:**
The one-time migration cost is modest, whereas the recurring tax of managing 25+ submodules is permanent and compounding. Migration is overwhelmingly the better investment.

---

## Target Architecture: The Unified `skills-dev` Monorepo

### 1. Proposed Directory Layout

```text
skills-dev/
├── .github/
│   └── workflows/
│       └── lint.yml             # Single unified CI workflow
├── ci/
│   ├── post-coverage-status.py
│   └── ...
├── docs/
│   └── ...
├── install-skills.sh            # Updated for monorepo layout
├── install-skills.bat           # Updated for monorepo layout
├── pyproject.toml               # Single root configuration for ruff, pytest, coverage
├── README.md                    # Catalog of all skills with thematic groupings
├── AGENTS.md                    # Simplified developer and agent instructions
├── scripts/
│   ├── validate_skills.py       # Validates all skills/ directories
│   ├── clean-room.sh            # Clean-room test runner
│   └── hook-timing.py
├── skills/                      # All skill source directories
│   ├── agent-remote/
│   │   ├── SKILL.md
│   │   ├── README.md
│   │   ├── references/
│   │   ├── tests/
│   │   └── evals/
│   ├── capture-idea/
│   ├── check-memory/
│   ├── cost-estimator/
│   ├── docs-update/
│   ├── escalate-over-shortcut/
│   ├── external-harness-routing/
│   ├── fast-tests/
│   ├── find-task/
│   ├── fleet-orchestration/
│   ├── maintaining-full-coverage/
│   ├── memory-cleanup/
│   ├── progress-beacon/
│   ├── project-lock/
│   ├── project-maintenance/
│   ├── promote-project/
│   ├── pushback/
│   ├── reconcile-tasks/
│   ├── research-first/
│   ├── review-in-parallel-pipelines/
│   ├── running-spikes/
│   ├── smoke-test/
│   ├── unity-batchmode-worktree/
│   ├── using-a-debugger/
│   └── wrap/
└── tests/
    ├── test_install_skills.py
    └── test_validate_skills.py
```

### 2. Single-Step Workflow for Adding a New Skill

In the monorepo, adding a skill becomes trivial:
1. Create directory `skills/<name>/`
2. Add `SKILL.md` (and optional `references/`, `scripts/`, `assets/`, `evals/`, `.skillpack`)
3. Run `python scripts/validate_skills.py` and `pytest`
4. Commit and push directly to `skills-dev`

No GitHub repository creation, no Gitea API calls, no relative submodule wiring, and no submodule pointer commits.

### 3. Claude Code Plugin Compatibility

Claude Code supports loading a plugin directory with `SKILL.md` at its root via `--plugin-dir <path>` (Claude Code >= 2.1.142).
With the monorepo layout, each `skills/<name>` directory maintains `SKILL.md` at its root, so `--plugin-dir ./skills/<name>` continues to work identically for single-skill clean-room testing and local plugin invocation.

---

## Migration Execution Plan

### Phase 1: Scripted History Stitching
1. Write a migration helper script `scripts/migrate-to-monorepo.sh`.
2. For each submodule path in `.gitmodules`:
   - Use `git subtree add --prefix=skills/<name> <name> main` (or read the submodule commit directly).
   - Verify that history and file integrity match the submodule head.
3. Remove `.gitmodules` and all submodule git tracking configurations.

### Phase 2: Tooling & Installer Updates
1. Update `install-skills.sh` and `install-skills.bat`:
   - Change discovery root to `$SRC_ROOT/skills/*/`.
   - Update `build_staging` to stage files from `skills/<name>/`.
2. Update `scripts/validate_skills.py`:
   - Discover skills by scanning `$SRC_ROOT/skills/`.
3. Update `pyproject.toml` and `.markdownlint-cli2.jsonc`:
   - Adjust glob paths to cover `skills/**/*.py` and `skills/**/*.md`.
4. Remove obsolete scripts:
   - `scripts/push-all.sh`, `scripts/push-all.bat`
   - `scripts/pull-all.sh`, `scripts/pull-all.bat`
   - `scripts/check_config_drift.py` (and associated tests)

### Phase 3: Verification & Test Suite Adaptation
1. Run full test suite: `pytest`, `ruff check`, `ruff format --check`, `shellcheck`, `aislop scan`.
2. Execute `test-install.sh` to confirm dry-run, installation, mirror cleanup, and `.skillpack` behavior against the new directory layout.
3. Perform end-to-end dry-run install: `./install-skills.sh -n --all`.

### Phase 4: Remote Archival
1. On GitHub and Gitea, set standalone `skills-<name>` repositories to read-only / archived.
2. Update their READMEs with a banner redirecting contributors to `skills-dev`.

---

## Non-Goals & Invariants Preserved

- **Skill authoring format:** No changes to `SKILL.md` frontmatter, Markdown body, or YAML specification conformance (`agentskills validate`).
- **Runtime destinations:** Installed layout in `~/.agents/skills/<name>/`, `~/.claude/skills/<name>/`, `~/.gemini/config/skills/<name>/`, and `<hermes>/skills/<name>/` remains identical.
- **Portability rules:** Prohibition of machine-specific absolute paths in tracked files remains strictly enforced by CI.
