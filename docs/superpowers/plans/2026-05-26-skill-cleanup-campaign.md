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

Campaign planned; nothing executed yet **except** the `escalate-over-improvise`
→ `escalate-over-shortcut` reference fix in `fast-tests` (already shipped this
session — 4 refs retargeted, committed, pushed; umbrella at `548a596`). Next up:
**Session 1**.

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

### Session 3 — progress-beacon + cost-estimator

- **Fold predictive cost → progress-beacon.** Predictive *time* already lives in
  the beacon's calibrated ETA; predictive *cost* is still "in design" per
  `project_cost_estimator_skill`. Edit `cost-estimator/README.md`: point the
  time-prediction half at progress-beacon, scope cost-estimator's predictive
  section to cost only.
- **Land the beacon drift-field removal.** `feedback_beacon_drift_uninformative`
  says the `progress-beacon` SKILL.md `drift` field is *queued for removal* (the
  status line computes drift objectively now). **CAUTION — cross-repo:** the
  beacon JSON schema is parsed by `schoen-claude-status` (statusline) and a
  `PostToolUse` hook. Verify those sides before/after; check
  `project_beacon_pairing_fix` for the lockstep state. Removing the field from
  the skill must not break the parsers.
- Commit + push (skills-progress-beacon, skills-cost-estimator, + any sibling
  repos the schema change touches).

### Minor fixes (fold into whichever session is already in that repo)

- `maintaining-full-coverage/README.md`: `test-report.txt` → `TEST-REPORT.md`
  (SKILL.md standardized on the latter; README is stale).
- Correct the `.maintenance.json` breadcrumb from 2026-05-26: the note claiming
  "origin/main advanced past the umbrella pointer" was wrong — it was a stale
  local `main` ref (detached HEAD), fixed via `git branch -f main origin/main`.
  Nothing upstream was missing.
- Consider a stronger restructure-over-exclude worked example *in
  `maintaining-full-coverage` itself* (the lever is already banked as
  `feedback_inspections_refactor_over_suppress`).

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
