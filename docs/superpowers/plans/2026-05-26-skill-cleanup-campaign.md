# Skills cleanup campaign — multi-session

**Started:** 2026-05-26 (out of a `/project-maintenance` pass on `skills-dev`).
**Mechanic:** budget-capped sessions. Each session works until ~200k context,
then updates the **Handoff log** + **Current status** below, commits this doc,
and stops. The next session reads this file first and resumes from Current
status. (Same spirit as the `wrap` skill, scoped to this campaign.)

**Standing constraints (read before editing any skill):**

- `feedback_lean_skill_bodies` — keep skill bodies lean; the user has flagged
  hefty skills. **Bias to TRIM placeholder/speculative content, not fill it.**
  The bar to add reference material is "genuinely global + load-bearing," not
  "we did it once."
- Each touched skill is its own submodule: commit there, push `origin`+`github`,
  then bump the umbrella pointer and push the umbrella. (See `scripts/push-all.sh`.)
- Watch for detached-HEAD submodules with a stale local `main` ref
  (`feedback_detached_head_stale_main`): `git branch -f main HEAD` before pushing.

## Current status

**All three sessions complete** (2026-05-27; all pushed to both hosts). See the
Handoff log for per-session detail. Net so far: fast-tests reference TODOs
trimmed; `restructure-over-exclude` relocated to `maintaining-full-coverage`
(now its `## Restructure Over Exclude` section, with the git-wizard
`AccessToDisposedClosure` example); MFC README staleness fixed; both stale
"Not yet built" HANDOFF.md files deleted (clearing the last
`escalate-over-improvise` refs).

**Discovery:** Session 3's beacon `drift`-field removal is **already done** —
three `progress-beacon` pointer-bump commits from the other machine landed on
`origin/main` (`2b63444`, `522132c`, `acf9fb0`) doing exactly that work. So
Session 3 below is now **only** the cost-estimator README predictive-cost fold.

The campaign's substantive work is **done**. The one remaining loose end is the
`.maintenance.json` breadcrumb — corrected durably in the Minor fixes section
below (the local untracked file itself left as-is; see there for the nuance).

## Open follow-ups (next session)

The three sessions are done; these two small items were deferred here by user
choice (wrapped as a handoff, 2026-05-27):

1. **Submodule detached-HEAD sweep.** The `.maintenance.json` finding named 5
   detached-HEAD submodules; this campaign re-checked and resolved 3
   (`cost-estimator`, `progress-beacon`, `review-in-parallel-pipelines`). **Still
   unchecked: `escalate-over-shortcut` and `running-spikes`.** For each, run
   `git -C <repo> symbolic-ref -q HEAD` (or `git submodule status`); if detached
   with a stale local `main`, reattach via `git branch -f main HEAD && git checkout main`
   — **but only when HEAD is at or ahead of `origin/main`.** Verify direction first
   (`git rev-list --left-right --count origin/main...HEAD`): the progress-beacon
   lesson this session was that some submodules were genuinely *behind* (real
   upstream commits), where the fix is a fast-forward, not `branch -f`.
2. **Close the seed note.** `~/.claude/notes/project_skills_cleanup_campaign.md`
   still reads "planned" — mark it complete, then `python ~/.claude/sync-memory.py`
   to propagate to the other machine. Once both follow-ups are done and this
   section is empty, this plan doc can be deleted per the skills-dev plans
   convention (lasting rationale already folded into the skills themselves).

## Sessions (sequenced; each ≈ one 200k-budget chunk)

### Session 1 — fast-tests references

- **Usage audit.** Grep `~/.claude/projects` transcripts for real `fast-tests`
  skill invocations. Judge whether anything we actually did was *globally*
  applicable (vs project-specific). Output: a short list of candidate lessons.
- **Capture the JetBrains use-after-dispose example** (see Captured knowledge)
  into `fast-tests/references/restructure-over-exclude.md` — it fills the
  existing `.NET` `TODO: concrete before/after restructure example`. Pull the
  concrete before/after from the actual project where it happened (user knows
  which; confirm at session start).
- **Decide trim-vs-fill** for the remaining reference TODOs:
  `references/tiering.md` (×3), `restructure-over-exclude.md` (Python + .NET),
  `pre-warming.md` (×3). Default to TRIM unless the audit produced a genuinely
  global lesson worth a few lines.
- Commit + push `fast-tests`; bump umbrella.

### Session 2 — stale HANDOFF.md scaffolding cleanup

**DONE (2026-05-27).** Both HANDOFF.md deleted after diffing against the shipped
SKILL.md (nothing load-bearing to fold — content survives in git history);
READMEs updated; the sweep found no other stale root scaffolding across the 17
submodules. Original bullets below for reference.

- Two `HANDOFF.md` files sit at the roots of *shipped* skills, both headed
  **"Status: Not yet built"**:
  - `review-in-parallel-pipelines/HANDOFF.md` (skill shipped, closes #5) — also
    holds the **last 2 `escalate-over-improvise` refs** (lines ~37, ~92).
  - `fast-tests/HANDOFF.md` (skill shipped).
- **Distill first, then delete.** Per repo convention, lasting design rationale
  folds into `SKILL.md`/`README.md` before the scaffolding is removed. Read each
  HANDOFF.md, diff its substance against the shipped SKILL.md, fold anything
  load-bearing, then `git rm` both. (Neither is shipped — outside the install
  allowlist — so removal is dev-tree-only.)
- Sweep the other ~15 skills for similar stale root scaffolding.
- Commit + push affected submodules; bump umbrella.

### Session 3 — cost-estimator (reduced; beacon-drift half already done)

- ~~**Fold predictive cost → progress-beacon.**~~ **DONE (Session 3, 2026-05-27).**
  cost-estimator's predictive section was already cost-only; added a "Scope: cost,
  not time" boundary note pointing time-to-complete at `progress-beacon`.
  cost-estimator → `a89f17c`.
- ~~**Land the beacon drift-field removal.**~~ **DONE — already shipped from the
  other machine** (umbrella commits `2b63444` "drop drift field", `522132c`
  "drop vestigial drift guidance", `acf9fb0` "drift wording cleanup";
  `progress-beacon` now at `0337307`, local llamabox fast-forwarded to match).
  The cross-repo `schoen-claude-status` / `PostToolUse` parser caution was
  presumably handled by whoever shipped it — worth a spot-check next time those
  parsers are touched, but no action queued here.
- Commit + push (skills-cost-estimator + umbrella) — only the README fold remains.

### Minor fixes (fold into whichever session is already in that repo)

- ~~`maintaining-full-coverage/README.md`: `test-report.txt` → `TEST-REPORT.md`~~
  **DONE (Session 1).** Also fixed stale `skill-draft/SKILL.md` install paths
  (post root-layout migration `b3a0a98`).
- **`.maintenance.json` breadcrumb (2026-05-26) — corrected (2026-05-27).** It
  flagged 5 submodules as detached HEADs whose `origin/main` "advanced 1-2 commits
  beyond the umbrella pointer," and this plan originally claimed that was uniformly
  a stale-local-`main` illusion. Session 3 found a **mix**: `cost-estimator`
  (HEAD==main==origin/main) and `review-in-parallel-pipelines` were genuine
  stale-ref/detached artifacts at the pinned pointer (resolved this campaign);
  `progress-beacon` genuinely **had** 3 upstream commits the local lacked (the
  drift-field removal — now integrated). `escalate-over-shortcut` + `running-spikes`
  were not re-checked. The `.maintenance.json` file is untracked/local-only and
  read by projdash tooling — left as-is rather than hand-editing a tool-read JSON;
  this tracked note is the durable correction.
- ~~Consider a stronger restructure-over-exclude worked example *in
  `maintaining-full-coverage` itself*~~ **DONE (Session 1)** — the entire
  `restructure-over-exclude` reference now lives in MFC's
  `## Restructure Over Exclude` section, with the git-wizard analyzer-suppression
  case as the .NET worked example.

## Captured knowledge (do not lose)

### JetBrains use-after-dispose → restructure-over-exclude (.NET)

Real case the user surfaced 2026-05-26: a JetBrains inspection flagged **using
disposables after they had been disposed**. The fix was not to suppress the
inspection — it required a **structural rewrite**, and that rewrite **surfaced /
fixed a potential real bug at the same time**. This is the canonical
"restructure over exclude / refactor over suppress" payoff: the analyzer warning
was not noise to silence; restructuring to satisfy it revealed a genuine defect.

Use this as the `.NET` worked example in
`fast-tests/references/restructure-over-exclude.md` (and/or as a stronger example
in `maintaining-full-coverage`). **Action for Session 1:** locate the actual
project + commit where this happened and lift the concrete before/after; the
prose above is the lesson, not yet the code.

## Handoff log

- **2026-05-26 (planning session):** Campaign scoped. The only code change
  shipped was the `escalate-over-shortcut` reference fix in `fast-tests`. This
  doc + `~/.claude/notes/project_skills_cleanup_campaign.md` are the seed.
  Next session: Session 1.
- **2026-05-27 (Session 1):** Done + pushed to both hosts. fast-tests: trimmed 8
  speculative reference TODOs (`eb320c3`), then relocated `restructure-over-exclude`
  to MFC and repointed (`a89f46a`). maintaining-full-coverage: added the git-wizard
  worked example + README fixes (`a12d457`), then folded the relocated reference
  into a `## Restructure Over Exclude` section + AUDIT row (`59e41da`). The
  relocation was a mid-session user call (coverage material in a speed skill) —
  beyond original Session 1 scope but improves coherence. fast-tests HEAD
  `a89f46a`, MFC HEAD `59e41da`. Next: Session 2.
- **2026-05-27 (Session 2):** Done + pushed both hosts. Deleted both stale
  "Not yet built" HANDOFF.md (`fast-tests` → `634893d`,
  `review-in-parallel-pipelines` → `7024414`); diff vs shipped SKILL.md showed
  nothing load-bearing to fold. READMEs updated (repo-tree + installer-excludes
  list). Cleared the last 2 `escalate-over-improvise` refs (they lived only in
  the r-i-p-p HANDOFF; the SKILL.md already used `escalate-over-shortcut`). Sweep
  found no other stale root scaffolding across 17 submodules. Gotcha hit: r-i-p-p
  was in detached HEAD with a stale `main` ref — fixed via `git branch -f main HEAD`
  before pushing. **Discovery:** Session 3's beacon drift-field removal already
  shipped from the other machine (3 progress-beacon bumps on origin); Session 3
  reduced to the cost-estimator README fold. Next: Session 3 (reduced).
- **2026-05-27 (Session 3, reduced):** Done + pushed both hosts. Only the
  cost-estimator README predictive-cost fold remained (beacon drift-field half
  already shipped from the other machine). cost-estimator was detached at `8de0ad6`
  (HEAD==main==origin/main — the stale-ref illusion, nothing upstream); reattached,
  added the "Scope: cost, not time" boundary note → `a89f17c`. Corrected the
  `.maintenance.json` finding in Minor fixes (it was a mix, not a uniform illusion).
  Campaign substantively complete.
