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

**Session 1 complete** (2026-05-27; pushed to both hosts). fast-tests reference
TODOs trimmed (8 speculative placeholders removed). The `restructure-over-exclude`
reference was relocated wholesale from `fast-tests` to `maintaining-full-coverage`
— it was coverage material (uncovered branches, exclusions) sitting in a speed
skill that explicitly scopes coverage out (mid-session user call, beyond the
original Session 1 scope; improves coherence). It became MFC's new
`## Restructure Over Exclude` section, merging the git-wizard
`AccessToDisposedClosure` example (the original Session 1 item #2) with the
relocated coverage examples. MFC README install/report-file staleness fixed.
fast-tests keeps its speed-only restructuring (Principle 5) plus a pointer to MFC.

Next up: **Session 2** (stale HANDOFF.md scaffolding). Note: `fast-tests/HANDOFF.md`
still lists the now-deleted `restructure-over-exclude.md` in its file tree —
harmless, and Session 2 deletes that HANDOFF.md anyway.

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

- ~~`maintaining-full-coverage/README.md`: `test-report.txt` → `TEST-REPORT.md`~~
  **DONE (Session 1).** Also fixed stale `skill-draft/SKILL.md` install paths
  (post root-layout migration `b3a0a98`).
- Correct the `.maintenance.json` breadcrumb from 2026-05-26: the note claiming
  "origin/main advanced past the umbrella pointer" was wrong — it was a stale
  local `main` ref (detached HEAD), fixed via `git branch -f main origin/main`.
  Nothing upstream was missing. **(still pending)**
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
