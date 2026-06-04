# docs-update Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `docs-update` disposition skill (smoke-test sibling) that runs as the post-smoke-test step in the completion ritual - once a change is verified working and no more edits are planned, check whether it made any docs lie - plus thin references from smoke-test / wrap / project-maintenance and an explicit docs task in the superpowers planning skills.

**Architecture:** Canonical skill + thin references. The `docs-update` skill (new `skills-docs-update` submodule, root layout) holds the full behavior; sibling skills get real hooks into the moment but point at the skill for the procedure. The eval harness is cloned from the escalate-over-shortcut model (copy seed -> per-run workspace, agent edits with Write/Edit, grade by inspecting resulting files + chat), because the strong signal is "did the stale doc actually get fixed (or correctly left alone)." Spec source: `docs/superpowers/specs/2026-06-04-docs-update-skill-design.md`.

**Tech Stack:** Markdown skill content; Python eval harness (`claude -p` driver + rubric grader, stdlib only); git submodules on Gitea (primary) + GitHub (mirror); markdownlint + ruff + aislop lint gates; `agentskills validate`.

**Cross-repo note:** Phases 1-4 are in `skills-dev` (the skill + its submodule integration + sibling-skill references). Phase 5 edits the **superpowers** repo (`~/superpowers`), which is separate - its own commit, not a skills-dev change.

**Commit identity:** Matt Schoen default for all direct commits (per skills-dev convention). Bot identities are only for PRs where Gitea self-approval matters.

**No em-dashes** in any generated content (skill prose, README, commit messages). Use ` - `, `:`, or parens.

---

## Phase 1: Author the docs-update skill content

Work in a temporary local directory `docs-update/` at the skills-dev root (it becomes a submodule in Phase 3). Root layout, mirroring smoke-test / escalate-over-shortcut.

### Task 1.1: Write SKILL.md

**Files:**
- Create: `docs-update/SKILL.md`

- [ ] **Step 1: Write the skill file** with exactly this content:

````markdown
---
name: docs-update
description: "Use after you've finished and verified a change (smoke test passed) and have no further edits planned - before declaring work done, committing, pushing to main, or opening a PR. Checks whether the change made any documentation lie: README, CLAUDE.md / AGENTS.md, other in-repo docs, inline doc comments. Most invocations end 'no docs affected' - that's healthy; the value is the check. Does NOT fire per-edit mid-work."
---

# Docs Update

## The Problem This Solves

Code changes silently invalidate the prose that describes them. A renamed flag, a moved command, a changed default, a deleted helper - and now the README, the CLAUDE.md build instructions, or a docstring is quietly lying. The next reader (often a future agent session) trusts the stale doc and wastes time, or worse, acts on it.

Updating docs after *every* edit is wasted effort - the change might get undone or redone differently. So there is no natural per-edit moment, and docs rot. The fix is to anchor the check to one specific moment: after the change has settled.

## Where This Fits

docs-update is the step right after smoke-test in the same completion ritual. It is a sibling skill, sequenced second:

```
finish change -> smoke-test (does it work?) -> docs-update (do the docs still tell the truth?) -> declare done / commit / push / open PR
```

The guard that keeps this from firing per-edit: run it only once the change is **verified working AND you have no further edits planned**. Before that, any doc you touch might be invalidated again by your next edit. After that, the change is real and the docs either match it or they don't.

## When to Run

Run once, after smoke-test passes and before you declare done / commit / push to main / open a PR, whenever the change altered something a doc could describe.

## When NOT to Run

- Mid-work, between edits, when more changes are still coming. Wait until the change settles.
- Changes with no externally-describable surface: a comment-only edit, a whitespace pass, an internal variable rename that nothing documents.
- When the smoke test failed. Fix the code first; do not document a broken change.

## The Check

1. **What did this change alter that is described somewhere?** Public API, CLI flags, commands, setup / build / test steps, config keys, environment variables, architecture, conventions, observable behavior, defaults.
2. **For each surface below, ask: does this change make any statement here false or incomplete?**
3. **Update only what drifted.** Minimal, justified edits that bring the doc back in line with reality - not a gratuitous rewrite, not a style pass, not new documentation the change didn't call for.
4. **Bundle the doc edits into the same commit / PR as the code** so a reviewer sees the behavior change and the doc change side by side.
5. **If unsure whether a doc statement is load-bearing** (would removing or changing it mislead someone?), surface it to the user rather than silently editing or silently skipping.
6. **State the docs impact when you report completion** - even "no docs affected, checked README + CLAUDE.md." Brief is fine. This is the docs analogue of smoke-test's "report what you verified."

## Surfaces To Check

| Surface | What drifts | Why it matters |
|---------|-------------|----------------|
| README | Usage, examples, flag / command references, feature list, install steps | First thing a human reads; wrong examples waste real time |
| CLAUDE.md / AGENTS.md | Build / test commands, conventions, architecture pointers | A future agent session trusts these as ground truth; drift here actively misleads |
| Other in-repo docs | ARCHITECTURE.md, `docs/`, CHANGELOG, API reference | Longer-form descriptions of behavior the change may have altered |
| Inline doc comments | Docstrings, XML doc, module headers next to the changed code | The most local docs; easiest to leave stale after a refactor |

## State the Docs Impact

When you finish, say what you checked and what you changed - concretely, briefly:

- "Updated README usage example for the renamed `--out` flag and the docstring on `export()`. No other docs affected."
- "No docs affected - checked README and CLAUDE.md, neither references the internal cache layer I changed."

A bare "done" hides whether you even looked. The one-line docs-impact note is the evidence that you did.

## When You'll Be Tempted To Skip

The check matters most exactly when you want to skip it:

- **Late in a long session**, when you just want to wrap up. This is when drift is most likely and least likely to be noticed.
- **After a "trivial" change** - a rename, a default flip, a moved command. These are precisely the changes that invalidate a one-line doc reference.
- **After a long debugging win**, when the fix finally landed and you want to call it done. The fix may have changed behavior a doc still describes the old way.
- **When the docs live somewhere slightly out of the way** (a `docs/` folder, a CHANGELOG you have to open). Out of sight is how docs rot.

In all of these: run the check. It is usually seconds, and it ends in "no docs affected" more often than not. The cost is small; the cost of a lying doc compounds.

## Non-Goals

- **Authoring brand-new documentation from scratch.** This skill fixes drift in docs the change touched, not missing docs in general.
- **Style, grammar, or formatting nitpicking.** Only fix statements the change made false or incomplete.
- **Updating docs for changes you did not make.** Pre-existing drift you happen to notice can be surfaced to the user, but it is not this change's job to fix it.
- **A hard gate.** This is a disposition, not a CI check that blocks. The judgment of "did this change make a doc lie" stays with you.
````

- [ ] **Step 2: Verify the frontmatter and structure**

Run: `head -5 docs-update/SKILL.md`
Expected: a `---` fence, `name: docs-update`, a `description:` line beginning with `"Use after`, and a closing `---`.

### Task 1.2: Write README.md

**Files:**
- Create: `docs-update/README.md`
- Reference: `smoke-test/README.md` (sibling shape to mirror)

- [ ] **Step 1: Read the sibling README for shape**

Run: `cat smoke-test/README.md`
Use its structure (title, one-paragraph what/why, "When it fires", "What it checks", a line on the eval harness, install note) as the template.

- [ ] **Step 2: Write `docs-update/README.md`** covering: what the skill is (the post-smoke-test docs-drift check); the smoke-test -> docs-update sibling sequence; the four surfaces it checks; that most invocations end "no docs affected"; how the eval harness is run (`evals/run.py` then `evals/grade.py`, point at the escalate-over-shortcut harness as the shared lineage); and that it installs via the skills-dev `install-skills` script. Do NOT hyperlink superpowers plugin skills as user repos (they are private plugin skills, not `mtschoen/skills-*`).

### Task 1.3: Add repo scaffolding files

**Files:**
- Create: `docs-update/LICENSE`, `docs-update/.gitignore`, `docs-update/.markdownlint-cli2.jsonc`, `docs-update/.gitea/workflows/lint.yml`
- Reference: the same files in `escalate-over-shortcut/`

- [ ] **Step 1: Copy the scaffolding from a sibling skill**

```bash
cp escalate-over-shortcut/LICENSE docs-update/LICENSE
cp escalate-over-shortcut/.gitignore docs-update/.gitignore
cp escalate-over-shortcut/.markdownlint-cli2.jsonc docs-update/.markdownlint-cli2.jsonc
mkdir -p docs-update/.gitea/workflows
cp escalate-over-shortcut/.gitea/workflows/lint.yml docs-update/.gitea/workflows/lint.yml
```

- [ ] **Step 2: Confirm `.gitignore` excludes the eval workspace**

Run: `grep -q '^workspace/' docs-update/.gitignore && echo OK || echo "ADD workspace/"`
Expected: `OK`. If `ADD workspace/`, append `workspace/` to `docs-update/.gitignore` (the eval harness writes run artifacts under `workspace/`, which must never be tracked).

- [ ] **Step 3: Check the lint workflow references no skill-specific name that needs changing**

Run: `grep -n 'escalate\|skill_name\|skill-name' docs-update/.gitea/workflows/lint.yml`
Expected: no skill-name-specific lines (the workflow lints `*.md` and `evals/*.py` generically). If any escalate-specific path appears, rewrite it to the docs-update equivalent.

### Task 1.4: Smoke-test the skill content (lint)

- [ ] **Step 1: markdownlint the skill prose**

Run: `npx -y markdownlint-cli2 "docs-update/**/*.md"`
Expected: no errors. Fix any reported (typically heading spacing, list markers, line length per `.markdownlint-cli2.jsonc`).

- [ ] **Step 2: aislop scan the new skill (pinned binary, NOT npx)**

Run: `aislop scan docs-update/`
Expected: no findings. (Uses the globally-installed pinned fork per skills-dev CLAUDE.md; do not use `npx aislop`.)

- [ ] **Step 3: Leave the content un-versioned for now**

Do NOT `git init` here. Phase 1 produces a plain local `docs-update/` directory; its first commit is the submodule's initial commit in Phase 3.2 (`git init` + commit + push to Gitea). No skills-dev commit happens in Phase 1 - the lint checks above are the only Phase 1 gate.

---

## Phase 2: Eval harness

Clone the escalate-over-shortcut harness and adapt it to docs-drift semantics. The harness lives inside the (future) submodule at `docs-update/evals/`.

### Task 2.1: Port the runner

**Files:**
- Create: `docs-update/evals/run.py`
- Reference: `escalate-over-shortcut/evals/run.py` (copy as the base)

- [ ] **Step 1: Copy the runner verbatim**

```bash
mkdir -p docs-update/evals
cp escalate-over-shortcut/evals/run.py docs-update/evals/run.py
```

- [ ] **Step 2: Adapt three things only** (the workspace-copy, invoke, and discovery machinery stay identical):

1. Module docstring: replace "escalate-over-shortcut iteration-2" framing with docs-update framing.
2. `SKILL_SECTION_WRAPPER`: change the skill name line to `## Skill available: docs-update` and the sentence to "Apply its guidance after you finish and verify the change, before declaring done."
3. `AGENT_PROMPT_TEMPLATE`: keep the subagent framing but set the post-change completion moment explicitly. The brief (from `brief.md`) describes a change the agent has *already made and verified*; the template's "How to proceed" becomes: "The change described in the brief is already implemented and verified in this workspace. You have no further code edits to make. Do a final pass before declaring done, then summarize what you did and what docs (if any) you touched."

Keep `--tools Read,Grep,Glob,Edit,Write,Bash` (the agent must be able to edit docs) and `--model claude-sonnet-4-6` default.

- [ ] **Step 3: Verify the runner parses and dry-runs**

Run: `python docs-update/evals/run.py --evals docs-update/evals/evals.json --skill-md docs-update/SKILL.md --output-dir docs-update/workspace/smoke --dry-run`
Expected: prints "Discovered N work units" and one line per (scenario, config, run). (Requires Task 2.3's evals.json + scenarios to exist; sequence this step after Task 2.3 if running top to bottom.)

### Task 2.2: Port and adapt the grader

**Files:**
- Create: `docs-update/evals/grade.py`
- Reference: `escalate-over-shortcut/evals/grade.py`

- [ ] **Step 1: Copy the grader verbatim**

```bash
cp escalate-over-shortcut/evals/grade.py docs-update/evals/grade.py
```

- [ ] **Step 2: Keep the indicator machinery verbatim, adapt only the bucketing.** Preserve `_check_indicator` (all kinds: `file_contains`, `file_contains_any`, `file_exists_glob`, `any_file_contains_glob`, `chat_pattern`, `llm_judge`), the LLM-judge plumbing, `discover_units`, and `summarize` unchanged. Rewrite `grade_unit`'s outcome model to docs-update semantics:

   - Rubric fields become: `drift_remaining_indicators` (the stale doc statement still present in post-state -> FAIL), `updated_indicators` (doc now reflects the change -> the success signal for drift scenarios), `over_edit_indicators` (doc churn on a control scenario -> FAIL), `surface_indicators` (chat: agent flagged an unsure-if-load-bearing doc statement to the user).
   - Outcomes: `docs_updated` | `docs_stale` | `over_edited` | `no_op`.
     - `drift_remaining` matched -> `docs_stale`.
     - else `updated` matched -> `docs_updated`.
     - else (drift scenario, neither) -> `no_op` (missed the drift).
   - `expected_outcome` values in evals/rubrics: `"update"` (a doc must change) or `"no-change"` (control: change touches no doc; agent must not churn docs).
     - For `update` scenarios: pass if outcome is `docs_updated`, OR the agent surfaced the statement for confirmation (`surface_indicators` matched) instead of editing - both are acceptable per the skill's "surface if unsure" clause.
     - For `no-change` control scenarios: pass if outcome is `no_op` AND no `over_edit_indicators` matched.

- [ ] **Step 3: Verify the grader parses**

Run: `python docs-update/evals/grade.py --help`
Expected: usage text listing `--responses-dir`, `--evals`, `--llm-judge`, `--llm-judge-model`.

### Task 2.3: Author scenarios + evals.json

**Files:**
- Create: `docs-update/evals/evals.json`
- Create: `docs-update/evals/scenarios/<name>/{brief.md,rubric.json,seed/...}` for each scenario
- Reference: `escalate-over-shortcut/evals/scenarios/todo-in-committed-code/` for the brief.md + rubric.json + seed shape

Author four scenarios (3 drift + 1 control). Each `seed/` is a tiny repo where the brief's change is *already applied to the code* but the matching doc still describes the old behavior.

- [ ] **Step 1: Scenario `readme-flag-rename` (expected `update`).** Seed: a small CLI (Python or Node) whose code now uses flag `--output` but whose `README.md` usage example still shows the old `--out`. brief.md: "You renamed the `--out` flag to `--output` in `cli.py`; tests pass." rubric.json:
   - `drift_remaining_indicators`: `{kind: file_contains, path: README.md, pattern: "--out\\b"}` (old flag still present -> stale).
   - `updated_indicators`: `{kind: file_contains, path: README.md, pattern: "--output"}`.
   - `expected_outcome: "update"`.

- [ ] **Step 2: Scenario `claude-md-command-drift` (expected `update`).** Seed: a repo whose test command moved from `pytest` to `python -m pytest tests/` (reflected in a Makefile/script) but `CLAUDE.md` still says "run tests with `pytest`". brief.md describes the command change. rubric.json:
   - `drift_remaining_indicators`: `{kind: file_contains, path: CLAUDE.md, pattern: "run tests with `pytest`"}` (exact stale line).
   - `updated_indicators`: `{kind: file_contains, path: CLAUDE.md, pattern: "python -m pytest"}`.
   - `expected_outcome: "update"`.

- [ ] **Step 3: Scenario `docstring-behavior-drift` (expected `update`).** Seed: a function whose body changed (e.g. now returns a 256x256 thumbnail instead of 128x128) but whose docstring still says the old size. brief.md describes the behavior change. rubric.json:
   - `drift_remaining_indicators`: `{kind: file_contains, path: src/thumbnails.py, pattern: "128"}` in the docstring region.
   - `updated_indicators`: `{kind: file_contains, path: src/thumbnails.py, pattern: "256"}`.
   - `expected_outcome: "update"`.

- [ ] **Step 4: Control scenario `internal-rename-no-docs` (expected `no-change`).** Seed: a repo where an internal private helper was renamed (`_compute` -> `_calculate`), with a README and CLAUDE.md that describe only public behavior and mention neither name. brief.md describes the internal rename. rubric.json:
   - `over_edit_indicators`: `{kind: any_file_contains_glob, glob: "*.md", pattern: "_calculate"}` (agent dragged the internal name into docs that shouldn't mention it) and/or a `chat_pattern` for the agent claiming it updated docs.
   - `expected_outcome: "no-change"`.
   - No `updated_indicators` (nothing should change).

- [ ] **Step 5: Write `evals.json`** listing the four scenarios with `id`, `name`, `scenario_dir` (e.g. `scenarios/readme-flag-rename`), and `expected_outcome`, matching the escalate-over-shortcut evals.json shape (`{"skill_name": "docs-update", "evals": [ ... ]}`).

- [ ] **Step 6: Verify discovery**

Run: `python docs-update/evals/run.py --evals docs-update/evals/evals.json --skill-md docs-update/SKILL.md --output-dir docs-update/workspace/smoke --dry-run`
Expected: "Discovered 8 work units" (4 scenarios x 2 configs x 1 run) and one line per unit.

### Task 2.4: Harness smoke run (optional live check)

- [ ] **Step 1: Run one scenario live, both configs, n=1** (only if `claude -p` is available in this environment and the user wants the live check; otherwise note as deferred):

```bash
python docs-update/evals/run.py --evals docs-update/evals/evals.json --skill-md docs-update/SKILL.md \
  --output-dir docs-update/workspace/smoke --only-eval 0 --runs-per-config 1
python docs-update/evals/grade.py --responses-dir docs-update/workspace/smoke \
  --evals docs-update/evals/evals.json --llm-judge
```

Expected: the runner produces `with_skill/run-1/workspace/README.md` (edited) and a grading summary. This is a wiring smoke test (does the harness end-to-end run), NOT a statistical result - do not iterate SKILL.md on n=1 (per the "no iteration on n=1 evals" discipline). Get n>=3 variance bars before any prose tuning.

---

## Phase 3: Repo creation + submodule conversion

Follow the skills-dev submodule workflow (CLAUDE.md "Adding a new skill" + the gitea-submodule-workflow memory note). Repo name `skills-docs-update` on both hosts; submodule path `docs-update`. Verify current Gitea endpoints/tokens against the global CLAUDE.md "Gitea" section before running (the memory note may be stale).

### Task 3.1: Create remote repos

- [ ] **Step 1: Confirm Gitea repo does not exist**

```bash
TOKEN=$(tr -d '\n\r' < ~/.gitea-token)
curl -sk "https://gitea.llamabox.internal/api/v1/repos/schoen/skills-docs-update" \
  -H "Authorization: token $TOKEN" -o /dev/null -w "%{http_code}\n"
```
Expected: `404`.

- [ ] **Step 2: Create the Gitea repo (schoen namespace, admin token)**

```bash
curl -sk -X POST "https://gitea.llamabox.internal/api/v1/user/repos" \
  -H "Authorization: token $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"skills-docs-update","description":"docs-update skill: post-smoke-test docs-drift check","private":true,"default_branch":"main","auto_init":false}'
```
Expected: `201`.

- [ ] **Step 3: Create the GitHub repo (public)**

```bash
gh repo create mtschoen/skills-docs-update --public \
  --description "docs-update skill: post-smoke-test docs-drift check"
```
Expected: repo created; no push yet.

### Task 3.2: Init, commit, push to Gitea

- [ ] **Step 1: Init the local dir and push to Gitea**

```bash
cd docs-update
git init -q -b main && git add -A && git -c commit.gpgsign=false commit -m "Initial commit: docs-update skill"
git remote add origin gitea@llamabox.internal:schoen/skills-docs-update.git
git push -u origin main
cd ..
```
Expected: push succeeds (CRLF warnings are cosmetic).

### Task 3.3: Convert to submodule

- [ ] **Step 1: Remove the local dir (Windows busy-cwd gotcha: cd out first)**

```bash
cd "$(git rev-parse --show-toplevel)"
rm -rf docs-update
[ -d docs-update ] && rmdir docs-update || true
```
Expected: `docs-update/` gone.

- [ ] **Step 2: Add as submodule via ABSOLUTE Gitea URL, then rewrite to relative**

```bash
git submodule add gitea@llamabox.internal:schoen/skills-docs-update.git docs-update
git config -f .gitmodules submodule.docs-update.url ../skills-docs-update.git
```
Expected: `.gitmodules` gains a `docs-update` entry with the relative `../skills-docs-update.git` URL. Do NOT run `git submodule sync` afterward (it would clobber the working-tree origin).

- [ ] **Step 3: Add the GitHub remote on the submodule and push (no `-u`)**

```bash
git -C docs-update remote add github git@github.com:mtschoen/skills-docs-update.git
git -C docs-update push github main
```
Expected: GitHub now has main. Upstream stays `origin/main` (Gitea); `-u github` would wrongly retarget it.

- [ ] **Step 4: Add the submodule to the ruff exclude list**

**Files:** Modify: `pyproject.toml` (`[tool.ruff]` `exclude`)

Add `"docs-update"` to the `exclude` array so the umbrella lint gate does not lint the submodule (each skill owns its own gate).

Run: `grep -n 'docs-update' pyproject.toml`
Expected: the new exclude entry appears.

### Task 3.4: Verify install + commit the pointer

- [ ] **Step 1: Confirm install-skills picks it up (dry run)**

```bash
./install-skills.sh -n docs-update
```
Expected: one line `install docs-update -> ~/.claude/skills/docs-update` (fresh-install dry runs show only that line).

- [ ] **Step 2: Real install so the skill is live locally**

```bash
./install-skills.sh -y docs-update
```
Expected: installs `SKILL.md` (+ any allowlisted dirs) into `~/.claude/skills/docs-update/`. `evals/`, `README.md`, `workspace/` are excluded by the top-level allowlist.

- [ ] **Step 3: Commit the submodule pointer + .gitmodules + pyproject in skills-dev**

```bash
git add .gitmodules docs-update pyproject.toml
git commit -m "Add docs-update as submodule"
```

- [ ] **Step 4: Push both hosts**

```bash
./scripts/push-all.sh
```
Expected: skills-dev + the new submodule push to Gitea and GitHub; summary reports up-to-date / FF, no diverged states.

---

## Phase 4: References from sibling skills (skills-dev submodules)

Each sibling is its own submodule: edit inside it, commit + push the submodule, then bump the pointer in skills-dev. Re-run `./install-skills.sh -y <name>` after each so the live copy reflects the edit. Thin references only - point at docs-update, do not restate its procedure.

### Task 4.1: smoke-test closing pointer

**Files:** Modify: `smoke-test/SKILL.md` (append a section after "When You Can't Fully Verify")

- [ ] **Step 1: Append the pointer section**

```markdown
## After the Smoke Test Passes

Once the smoke test passes and you have no more changes to make, the change has settled. That is the moment to check whether it made any documentation lie. Use the **docs-update** skill - the sibling step to this one. It checks README, CLAUDE.md / AGENTS.md, other in-repo docs, and inline doc comments for drift your change introduced, and bundles any fixes into the same commit. Most of the time nothing needs updating; the value is the check.
```

- [ ] **Step 2: Lint, commit, push, bump, reinstall**

```bash
npx -y markdownlint-cli2 "smoke-test/SKILL.md"
git -C smoke-test add SKILL.md && git -C smoke-test commit -m "Point at docs-update as the post-smoke-test sibling step"
git -C smoke-test push && git -C smoke-test push github main
git add smoke-test && git commit -m "Bump smoke-test: docs-update pointer"
./install-skills.sh -y smoke-test
```
Expected: clean lint; both remotes updated; pointer bumped.

### Task 4.2: wrap docs-drift sweep

**Files:** Modify: `wrap/references/hygiene-checklist.md` (add a docs-drift item) and a one-line pointer in `wrap/SKILL.md` Phase 3c description.

- [ ] **Step 1: Read the hygiene checklist to find the insertion point**

Run: `cat wrap/references/hygiene-checklist.md`
Identify where per-repo hygiene items are listed.

- [ ] **Step 2: Add a docs-drift item** to `wrap/references/hygiene-checklist.md`: for any repo the session changed code in, check whether those changes left docs stale (README / CLAUDE.md / AGENTS.md / in-repo docs / inline comments). Reference the docs-update skill for the actual check. Surface findings as a per-repo opt-in (default: surface, let the user approve the edit), consistent with wrap's other hygiene findings. Note this is the catch-net for sessions that changed code but never reached a commit/PR moment where docs-update would normally fire.

- [ ] **Step 3: Add a one-line pointer in `wrap/SKILL.md`** Phase 3c paragraph noting the hygiene pass now includes a docs-drift check (see `references/hygiene-checklist.md`), pointing at docs-update.

- [ ] **Step 4: Lint, commit, push, bump, reinstall**

```bash
npx -y markdownlint-cli2 "wrap/**/*.md"
git -C wrap add -A && git -C wrap commit -m "Add docs-drift check to hygiene pass (references docs-update)"
git -C wrap push && git -C wrap push github main
git add wrap && git commit -m "Bump wrap: docs-drift hygiene check"
./install-skills.sh -y wrap
```

### Task 4.3: project-maintenance docs-content-drift check

**Files:** Modify: `project-maintenance/references/checklist.md` (add a check) and `project-maintenance/SKILL.md` step 2 (add the finding kind).

- [ ] **Step 1: Read the PM checklist**

Run: `cat project-maintenance/references/checklist.md`
Find where checks are enumerated.

- [ ] **Step 2: Add a `docs_content_drift` check** to `project-maintenance/references/checklist.md`, explicitly distinct from the existing `agents_convention` structural check: `agents_convention` validates the `@AGENTS.md` import *shape*; `docs_content_drift` asks whether the *content* of README / CLAUDE.md / AGENTS.md / in-repo docs still matches current code. Low-confidence, research-backed finding (read the doc, compare to code) per PM's "research before asking" principle. Reference docs-update for the per-surface check.

- [ ] **Step 3: Add the finding kind to `project-maintenance/SKILL.md`** step 2's research list (a bullet describing how to enrich a `docs_content_drift` finding: cite the stale statement and the code that contradicts it).

- [ ] **Step 4: Lint, commit, push, bump, reinstall**

```bash
npx -y markdownlint-cli2 "project-maintenance/**/*.md"
git -C project-maintenance add -A && git -C project-maintenance commit -m "Add docs-content-drift check (references docs-update)"
git -C project-maintenance push && git -C project-maintenance push github main
git add project-maintenance && git commit -m "Bump project-maintenance: docs-content-drift check"
./install-skills.sh -y project-maintenance
```

- [ ] **Step 5: Push the umbrella pointers**

```bash
./scripts/push-all.sh
```

---

## Phase 5: superpowers planning-skill edits (separate repo)

These edit `~/superpowers` (the plugin repo), NOT skills-dev. Commit in that repo separately. Verify its branch/remote conventions before committing (`git -C ~/superpowers status`, `git -C ~/superpowers remote -v`). Use the superpowers repo's own commit conventions.

### Task 5.1: writing-plans explicit Documentation task

**Files:** Modify: `~/superpowers/skills/writing-plans/SKILL.md`

- [ ] **Step 1: Add a "Documentation Task" convention** after the "Task Structure" section. Content: plans should include an explicit Documentation task near the end of each feature (or each phase that changes externally-described behavior) - update README / CLAUDE.md / AGENTS.md / in-repo docs / inline comments that the feature's changes affect, bundled with the work. This makes "docs as a phase of the plan" concrete rather than relying on the branch-finish lifecycle note. Reference the docs-update skill as the per-surface check the implementer runs.

```markdown
## Documentation Task

Behavior a plan changes is usually described somewhere - a README usage line, a CLAUDE.md command, a docstring. A plan that ships those changes but not the doc updates ships drift. Include an explicit **Documentation** task near the end of each feature (or each phase that alters externally-described behavior):

- [ ] **Update docs affected by this feature** - run the docs-update check across README, CLAUDE.md / AGENTS.md, in-repo docs, and inline doc comments; bring any drifted statements in line with the new behavior; commit the doc edits with (or immediately after) the code.

This is distinct from the branch-finish "fold durable insight into docs" step (that captures *new* architectural insight; this fixes *drifted* existing docs).
```

- [ ] **Step 2: Lint the edit**

Run: `npx -y markdownlint-cli2 "$HOME/superpowers/skills/writing-plans/SKILL.md"`
Expected: no errors.

### Task 5.2: finishing-a-development-branch docs-update reference

**Files:** Modify: `~/superpowers/skills/finishing-a-development-branch/SKILL.md` (Plan Disposal, step 1 "Extract durable insight")

- [ ] **Step 1: Add a docs-drift pointer** to the "Extract durable insight, if any" step. The existing step folds *new* insight into docs; add a sentence: before integrating, also run the docs-update check across the branch's diff to catch *drift* the work introduced in existing docs (README / CLAUDE.md / AGENTS.md / inline comments), not just new-insight folding. Reference the docs-update skill.

```markdown
**1a. Check for docs drift across the branch.** Beyond folding in new
insight, run the docs-update check against the branch diff
(`git diff <base>..HEAD`): did any change on this branch make an
existing doc statement false (a renamed flag in the README, a changed
command in CLAUDE.md, a stale docstring)? Fix drift now, in this branch,
before it merges. See the docs-update skill for the per-surface check.
```

- [ ] **Step 2: Lint the edit**

Run: `npx -y markdownlint-cli2 "$HOME/superpowers/skills/finishing-a-development-branch/SKILL.md"`
Expected: no errors.

### Task 5.3: Commit superpowers edits

- [ ] **Step 1: Commit in the superpowers repo**

```bash
git -C ~/superpowers add skills/writing-plans/SKILL.md skills/finishing-a-development-branch/SKILL.md
git -C ~/superpowers commit -m "Add explicit docs-update step to planning + branch-finish skills"
```
Expected: committed. Push per the user's preference for the superpowers repo (confirm before pushing - it is a separate publishing surface).

---

## Final verification

- [ ] **Validate every skill via the official validator** (umbrella CI gate runs this; run locally to catch issues early):

```bash
python scripts/validate_skills.py
```
Expected: all `.gitmodules` skills (now including docs-update) pass `agentskills validate`.

- [ ] **Umbrella lint gate is clean:**

```bash
ruff check scripts/ tests/ && ruff format --check scripts/ tests/
npx -y aislop@0.9.4 ci
```
Expected: 0 findings (the new submodule is excluded from the umbrella ruff scope; its own gate covers it).

- [ ] **Live skill load check:** in a fresh `claude` session in a repo, after a code change, confirm `docs-update` appears in the skill catalog and that smoke-test's new closing section points at it.
