# docs-update skill - design

> Working draft. Anchors the brainstorm-to-plan handoff. Will be distilled into
> the plan header and deleted at the next handoff. Lasting rationale lives in the
> skill's own SKILL.md / README once built.

## Problem

Claude does not reliably keep README / CLAUDE.md / other docs in step with the
code it changes. Doing it after every edit is wasted effort (the work may be
undone or redone differently), so there is no natural moment for it. The result
is documentation drift: docs that quietly start lying about the code.

The fix is a disposition skill (smoke-test model) that anchors the docs check to
a specific moment, plus reinforcing hooks in the skills that already own the
relevant moments, plus an explicit docs task in the planning skills.

## Cadence (the crux)

docs-update is NOT its own cadence. It is the step immediately after smoke-test
in the same completion ritual:

```
finish change -> smoke-test (does it work?) -> docs-update (did this change make
any docs lie?) -> declare done / commit / push / open PR
```

The guard that keeps it from firing per-edit: it only runs once the change is
verified working AND there are no further edits planned. This dissolves the
wasted-effort concern - docs are touched only after the change has settled.

External best practice corroborates this: docs updates belong to the "definition
of done" and should ship in the same commit/PR as the code so review sees both
side by side (docs-as-code).

## Approach: canonical skill + thin references

The `docs-update` skill holds the full behavior. project-maintenance, wrap, and
the planning skills get real hooks into the moment but point at the skill for the
procedure. One definition, multiple entry points - avoids the four-copies-drift
problem the skills ecosystem is built to avoid.

(Rejected alternative: independent restated content in each skill. More
self-contained but four places to keep aligned.)

## Section A - the docs-update skill (the anchor)

**Repo:** new submodule `skills-docs-update`, root layout (SKILL.md + evals/ +
README), following the standard skills-dev submodule workflow in CLAUDE.md.
Sibling to smoke-test.

**Name:** `docs-update`.

**Trigger / description** (anchored on the post-smoke-test completion moment):

> Use after you've finished and verified a change (smoke test passed) and have no
> further edits planned - before declaring work done, committing, pushing to
> main, or opening a PR. Checks whether the change made any documentation lie:
> README, CLAUDE.md / AGENTS.md, other in-repo docs, inline doc comments. Most
> invocations end "no docs affected" - that's healthy; the value is the check.
> Does NOT fire per-edit mid-work.

**Body - the check:**

1. **What did this change alter that is described somewhere?** Public API, CLI
   flags, commands, setup / build / test steps, config keys, architecture,
   conventions, observable behavior.
2. **For each surface, ask "does this change make any statement here false or
   incomplete?"**
   - README - usage, examples, flag/command references, feature list.
   - CLAUDE.md / AGENTS.md - build/test commands, conventions, architecture
     pointers. Drift here actively misleads future agent sessions.
   - Other in-repo docs - ARCHITECTURE.md, docs/, CHANGELOG, API docs.
   - Inline doc comments - docstrings / XML doc / module headers next to the
     changed code; easiest to leave stale after a refactor.
3. **Update only what drifted.** Minimal, justified edits - not a gratuitous
   rewrite (escalate-over-shortcut energy).
4. **Bundle doc edits into the same commit / PR as the code** so review sees
   them together.
5. **State the docs impact** when reporting completion - even "no docs affected,
   checked README + CLAUDE.md." Mirrors smoke-test's "report what you verified"
   and the docs-as-code "Documentation Impact" note. Brief is fine.
6. **If unsure whether a doc statement is load-bearing, surface it** to the user
   rather than silently editing or silently skipping.

**Mirrors smoke-test's shape:**
- A "When you'll be tempted to skip" section (late in a long session, "trivial"
  change, the high after a long debugging win).
- An explicit **non-goals** list: NOT for authoring brand-new documentation from
  scratch, NOT style/grammar nitpicking, NOT updating docs for changes you did
  not make.

**Relationship to smoke-test:** sibling skill, sequenced after. smoke-test
answers "does it work?"; docs-update answers "do the docs still tell the truth?"

**Eval harness (confirm at review):** include a lightweight eval-harness scaffold
cloned from the pushback / escalate-over-shortcut W/WO/Delta pattern, but defer
full eval iteration (no SKILL.md tuning on n=1; get variance bars first if/when
we iterate). This is the heaviest single piece; flagged for the user to confirm
keep-vs-drop in this pass.

## Section B - references from existing skills (skills-dev)

- **smoke-test** - add a short closing pointer: after the smoke test passes and
  there are no more changes, use docs-update. Makes the sibling sequence explicit
  from the skill agents already hit at completion.
- **wrap** - add a docs-drift sweep step over repos touched this session,
  pointing at docs-update. Fits wrap's "externalize ephemeral state before close"
  remit.
- **project-maintenance** - add a docs-content-drift check, distinct from its
  existing `agents_convention` structural check (which validates only the
  @AGENTS.md import shape, not whether the content is true). References
  docs-update for the procedure.

## Section C - planning-skill changes (superpowers - separate repo/plugin)

Superpowers is its own repo (the private plugin), so Section C is a separate
commit/PR from Sections A+B in skills-dev.

- **writing-plans** - promote docs from lifecycle prose to an explicit task: a
  "Documentation" task near the end of each feature/phase, added to the plan
  template. This is the real fix for "docs as an explicit phase of the plan."
- **finishing-a-development-branch** - make the existing "fold durable insight
  into docs" line concrete and point at docs-update.
- **executing-plans / subagent-driven-development** - no body change needed; they
  execute whatever the plan contains, so the writing-plans task convention
  carries through. Called out so we do not over-edit.

## Out of scope

- A CI gate / hook that mechanically blocks on docs drift (the user explicitly
  wants disposition, not a hard gate; revisit later if disposition proves weak).
- A docs-freshness dashboard / metric.
- Auto-generating documentation.

## Open question for review

1. Eval harness in this pass: keep the lightweight scaffold (recommended) or drop
   it and ship-and-observe?

## Sources

- https://blog.docuwiz.io/p/docs-as-code-how-to-prevent-api-documentation
- https://ferndesk.com/blog/documentation-drift
- https://www.docsie.io/blog/glossary/documentation-drift/
- https://graphite.com/guides/documenting-code-for-better-reviews-best-practices
