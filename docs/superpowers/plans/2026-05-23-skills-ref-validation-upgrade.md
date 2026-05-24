# skills-ref Validation Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Replace skills-dev's hand-rolled SKILL.md frontmatter validator with the official Agent Skills validator (`agentskills`, from the pinned `skills-ref==0.1.1` PyPI package), keeping only the fleet-level logic that is irreducibly ours, and add skill-content validation by extending the existing markdownlint CI.

**Architecture:** First migrate the 8 remaining `skill-draft`-layout skills to root layout so the fleet is uniform (this lets `agentskills` — which requires `name == parent-dir` — validate every skill directly with no staging shim, and lets the installer drop its dual-path branch). Then the Python validator becomes a thin fleet wrapper: it iterates `.gitmodules`, applies the anti-vacuous + WIP-skip + empty-dir guards, and delegates each skill to `agentskills validate <dir>` through an injectable runner seam (so fleet logic is unit-testable offline while integration tests exercise the real binary). Content validation is pure config: extend the umbrella's markdownlint job to check skill `*/*.md` + `*/references/**/*.md` with `submodules: recursive`.

**Tech Stack:** Python 3 (stdlib only — `yaml` dependency removed), `skills-ref==0.1.1` (CLI `agentskills validate`, exit 0 valid / 1 invalid), `markdownlint-cli2-action`, Gitea Actions, git submodules (Gitea `origin` + GitHub `github`).

**Verified facts (resolved 2026-05-23, live):** `pip install skills-ref==0.1.1` installs console script **`agentskills`** (the README's `skills-ref validate` is wrong). `agentskills validate <root-layout-skill>` → `Valid skill: <path>` exit 0; name mismatch → `Directory name 'X' must match skill name 'Y'` exit 1. It tolerates root-layout extra files (LICENSE, evals/, workspace/, .markdownlint-cli2.jsonc). markdownlint-cli2 merges rule config down the tree but reads `globs` only from the invocation dir.

---

## Phase 4: CI wiring + content linting + end-to-end verification

### Task 4.1: Point the CI validation job at agentskills

**Files:** Modify `.gitea/workflows/lint.yml`

- [x] **Step 1: Rewrite the `frontmatter` job as `validate-skills`**

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

- [x] **Step 2: Make the markdown job lint skill content too**

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

- [x] **Step 1: Broaden `globs`**

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

- [x] **Step 1: Run markdownlint with the new globs from the repo root**

Run (PowerShell):
```powershell
npx --yes markdownlint-cli2
```
Expected: it now lints skill `SKILL.md` + `references/` files. **If violations appear**, they are real (this content was never linted by the umbrella before). Fix each in its **submodule** repo (edit the file, then in that submodule: commit + `git push origin main` + `git push github main`), then bump that pointer in skills-dev (`git add <skill>`). If zero violations, the per-skill repos were already clean — proceed.

- [x] **Step 2: Re-run until clean**

Run (PowerShell):
```powershell
npx --yes markdownlint-cli2
```
Expected: exit 0, no violations.

### Task 4.4: Commit the CI + config changes

- [x] **Step 1: Commit**

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
