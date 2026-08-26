# Design Spec: Skill Repository Architecture (Families, not One-Repo-Per-Skill)

Status: Accepted
Issue: schoen/skills-dev#25
Date: 2026-08-19, revised 2026-08-26

## Executive Summary

One repository per skill was the right shape at 5 skills. At 26 it imposes a
configuration and maintenance tax that scales linearly with every skill added
and buys nothing back in practice.

The fix is **three themed submodules**, each a coherent, independently
adoptable set, with `skills-dev` retained as the umbrella index and installer.
Skills that cannot function without a specific tool move out of the public set
entirely and ship with that tool.

This supersedes an earlier revision of this document, which recommended
collapsing every skill into a single flat monorepo. That analysis weighed only
maintenance surface. It did not weigh distribution, which is the axis this
decision actually turns on. See "Why not a single flat repo".

## The Evidence: one-repo-per-skill does not scale

An audit on 2026-08-19, re-verified 2026-08-26, found:

- 26 skill repositories, each with its own CI workflow, branch protection
  policy, markdownlint config, and pair of forge remotes (52 endpoints).
- 24 of 26 still carry push URLs pointing at a retired hostname rather than
  the canonical forge host. They resolve today by accident of DNS, not by
  design.
- Two repositories (`fleet-orchestration`, `promote-project`) had genuinely
  diverged between forges: the same doc fix was performed twice, independently,
  on two machines, because coordinating one change across the fleet is painful
  enough that duplication is cheaper than synchronization. One of the two
  duplicates was also factually wrong, describing a helper as doing the
  opposite of what it does.
- Five local-only WIP branches (the umbrella plus four submodules) with no copy
  on any forge, all belonging to a single cross-cutting change.

The last two are the argument in miniature. A change that touches four
repositories costs four PRs plus a pointer bump, so it gets done ad hoc, twice,
and never pushed.

| Maintenance surface | 26 repos | 3 families | 1 monorepo |
| --- | --- | --- | --- |
| Forge endpoints | 52 | 6 | 2 |
| CI workflow definitions | 27 | 4 | 1 |
| Branch protection policies | 27 | 4 | 1 |
| PRs for a cross-cutting change | up to 26 + bump | up to 3 + bump | 1 |
| Steps to add a skill | 8 (two forge APIs) | 1 (`mkdir` in a family) | 1 (`mkdir`) |
| Pointer drift / detached HEAD risk | high | low | none |

Three families capture roughly 88% of the available reduction.

## Why not a single flat repo

The monorepo wins every operational column above, and on maintenance cost alone
it is the correct answer. It was rejected on distribution grounds.

These skills are published. The agent-skills ecosystem is saturated: the
curated directories index tens of thousands of skills and the aggregator lists
carry over a thousand. In that market an undifferentiated repository of 17
skills reads as a kitchen sink and is skipped. What gets adopted is a coherent
set that carries a whole way of working.

Two clarifications on that reasoning, because it is easy to over-apply:

1. **Repository count is not what creates coherence.** The most-cited positive
   example in this space is a single repository with many skills, and it reads
   as focused because it is framed as a methodology rather than a collection.
   Three repositories with no thesis would read as three small kitchen sinks.
   Each family repository therefore needs a real README argument for why its
   skills belong together, and that is a deliverable of this migration, not a
   nicety.
2. **What splitting buys that framing cannot is independent adoptability.**
   Someone who wants the orchestration set should be able to take it without
   the completion-discipline set. That is the concrete benefit, and it is the
   reason the split is worth its residual cost.

Families also carry a real cost the earlier revision correctly identified:
category boundaries are fuzzy and invite relitigation. This is mitigated, not
solved, by keeping the count at three and by accepting that a skill sitting
slightly awkwardly in a family is cheaper than a fourth family.

## Target architecture

### Three family submodules under `skills-dev`

`skills-dev` remains the umbrella: it holds the index, the installer, the
validation scripts, and three submodules.

**`skills-completion-discipline`** (7) - what an agent owes the work at the
point it stops.

- `maintaining-full-coverage`, `smoke-test`, `docs-update`,
  `escalate-over-shortcut`, `wrap`, `reconcile-tasks`, `project-maintenance`

**`skills-working-method`** (6) - habits applied while the work is happening.

- `research-first`, `running-spikes`, `pushback`, `effective-refactor`,
  `fast-tests`, `using-a-debugger`

**`skills-orchestration`** (6) - multi-agent, multi-machine, and quota
concerns.

- `agent-remote`, `external-harness-routing`, `fleet-orchestration`,
  `review-in-parallel-pipelines`, `project-lock`, `cost-estimator`

### Skills that ship with their tool

A skill whose value collapses without a specific tool belongs with that tool,
not in a set that advertises itself as portable. These leave `skills-dev`:

| Skill | New home |
| --- | --- |
| `check-memory`, `memory-cleanup` | `packages/replica/skills/` |
| `capture-idea`, `promote-project`, `find-task` | `packages/project_tracker/skills/` |
| `progress-beacon` | `satellites/agent-statusline/skills/` |

`progress-beacon` joins the `statusline` skill, which already lives there and
is already installed by `onboard`'s `SkillsFeature` via a direct copy. That
established path is the model for all six.

The test is whether the skill documents a by-hand path that still delivers its
value, not whether it calls the tool or how often. `find-task` never writes to
the tracker and still ships with it, because a cross-project sweep has no
by-hand substitute once the trackerless registry is retired and there is no
defined set of projects to enumerate. `capture-idea` and `promote-project` go
for the same reason: registration is the deliverable, and its fallback chain
loses its last rung with that registry.

Three skills that call `project_tracker` stay in the public set, because each
documents a path that works without it:

- `wrap` declares tool-agnosticism as a design goal.
- `reconcile-tasks` declares the dependency soft in its own README, and three
  of its four write paths never touch the tracker.
- `project-maintenance` pairs every checklist row with a literal shell command,
  and one whole check category stays manual even when the MCP server answers.
  It also reads `wrap`'s hygiene checklist and defers to `docs-update`, so it
  belongs in the same adoptable set as both.

### Retired

`unity-batchmode-worktree` is retired as a skill, with its content reaped as
widely as it will go rather than deleted.

- The persistent warm worktree pool protocol (pool slots, the
  `.worktree-reserved` marker, the survey / reserve / prep / release cycle)
  moves into `fleet-orchestration`, genericized away from Unity. This is not
  redundant with that skill's existing worktree material, which covers
  ephemeral per-dispatch worktrees and base-commit correctness. Reusing an
  expensive-to-build worktree across sessions is a different problem, and it
  applies to any project with costly first-build state (a large
  `node_modules`, a Rust `target/`, a populated ccache), not only to a Unity
  `Library/`.
- Any remaining transferable material should be placed in whichever existing
  skill it fits rather than concentrated in one. Implementers should look for
  homes before discarding anything.
- The genuinely Unity-specific remainder (batch-mode invocation, the `dev`
  scratch-branch squash-merge ritual, `Library/`, `TestResults/`) moves to the
  `liminal` project's `AGENTS.md` and to other Unity projects.

## Retiring the trackerless registry

`~/.project-tracker/projects.json` (hyphenated) is an agent-maintained
convention for installs without project-tracker. It is distinct from
`~/.project_tracker/` (underscored), which is the tool's own database. The
registry is retired along with the skills that maintained it.

Only the **tracker-absent** path is removed. The **MCP-absent** path stays:
`project-tracker list --json`, and direct `PLAN.md` / `TODO.md` /
`.maintenance.json` reads remain valid, because the tool can be installed
without the MCP server being registered.

Scope, confirmed by grep across every `SKILL.md`, `README.md`, and
`references/` file:

- **Edited:** `capture-idea` (SKILL.md frontmatter, workflow step 3, and the
  report-back knock-on; README.md), `promote-project` (frontmatter, the fourth
  registration bullet, and the verify checklist knock-on), `find-task`
  (frontmatter, the fallback paragraph, the calibration note; README.md), and
  `fleet-orchestration` (four sites: frontmatter, pre-flight fleet-wide
  bullet, maintenance breadcrumbs, feature-pass workflow).
- **Untouched:** `reconcile-tasks` and `project-maintenance` never referenced
  the registry. Their fallbacks are already file-and-git based.

### fleet-orchestration declares a dependency

`fleet-orchestration` stays in the public orchestration set, and the registry
was carrying all of its trackerless weight: `project-tracker list --json`
still requires the tool, and no filesystem enumeration is documented anywhere
in the file.

Resolution: drop to two tiers (MCP, then CLI) and state plainly that
**fleet-wide enumeration requires project-tracker installed**. On a machine
without it, the user names the target repositories explicitly. This is honest
about a dependency that already existed rather than implying a fallback that
does not work, and the skill's core value (dispatch discipline, base-commit
correctness, worktree isolation) stays fully portable.

Do not invent a filesystem-walk fallback. Unbounded recursive scans are their
own hazard, and no such practice exists in the corpus to document.

## Consequences that must be handled

### The installer needs a two-level glob

`install-skills.sh` discovers skills with `for src in "$SRC_ROOT"/*/` gated on
`.git` existing at that level. Under families, `SKILL.md` sits at
`<family>/<skill>/SKILL.md`, two levels down. The same change is needed for the
relocated skills, whose directories are plain monorepo subdirectories with no
`.git` of their own.

Both the `.git` gate and the glob depth must change, identically in
`install-skills.sh` and `install-skills.bat`. The gate is already redundant
(`SKILL.md` presence is checked downstream) and the tracked-file filter
underneath works fine on a non-repo subdirectory, because `git -C <dir>
ls-files` resolves the enclosing worktree. Note that CI shellchecks the `.sh`
half only; the `.bat` half has no execution test, so its edit needs manual
verification on Windows.

### Validation must follow the skills

`scripts/validate_skills.py` and `scripts/check_config_drift.py` both derive the
skill set from `.gitmodules`, deliberately, so a broken recursive checkout
cannot pass vacuously. Relocated skills stop being submodules and would drop
out of both silently, losing `agentskills validate` frontmatter checking and
the portability lint that bans machine-specific paths. That lint matters most
precisely for these skills, which are the ones coupled to local tooling.

Either generalize both scripts to also scan `packages/*/skills/*` and
`satellites/*/skills/*`, or stand up a schoen-lab counterpart. schoen-lab CI has
no skill validation today.

### A dangling cross-reference

`project-lock/SKILL.md:155` cross-references `unity-batchmode-worktree` and its
`.worktree-reserved` marker by name. It must repoint at `fleet-orchestration`'s
new warm-pool section.

### pr-crew must be paused on the skill repos

pr-crew opens PRs against these repositories automatically. Any PR that lands
mid-migration may or may not be captured by the subtree merge depending on
timing, and any that lands afterwards goes into a repository nobody reads
again. Pause it on `skills-*` before Phase 1 and resolve the open PRs
deliberately.

## Migration plan

### Phase 0: reconcile before touching history

Nothing below is safe until this is done: at the time of writing, two commits
existed only in `remotes/gitea/main`, reachable from no local branch or tag, so
a subtree operation scoped to local refs would have dropped them silently.

Status as of 2026-08-26:

1. Done. All five local-only WIP branches backed up to Gitea.
2. Done. `fleet-orchestration` reconciled to `1746c94`; the local duplicate was
   a strict subset and also incorrect.
3. Done. `promote-project` reconciled to `4432270`; the local duplicate was a
   strict subset.
4. Done. `project-maintenance` PR #5 squash-merged.
5. Done. `skills-dev#29` closed as superseded (pointer bumps at the three
   replaced commits).
6. Outstanding: `project-lock`'s two commits are pushed to Gitea but not on
   `main`.
7. Outstanding: pause pr-crew and resolve its three open PRs.
8. Outstanding: GitHub `main` still trails Gitea on `fleet-orchestration` and
   `promote-project`.

### Phase 1: create the three family repositories

Create each on both forges, then populate by subtree merge from each skill's
current repository so per-skill history is preserved under its new prefix.
Write each family README's thesis as part of this phase, not afterwards.

### Phase 2: relocate the six tool-coupled skills

Move by subtree into `packages/replica/skills/`,
`packages/project_tracker/skills/`, and `satellites/agent-statusline/skills/`.
Apply the registry retirement per the scope above.

### Phase 3: retire `unity-batchmode-worktree`

Reap the warm-pool protocol into `fleet-orchestration`, place any other
transferable material in whichever skill fits, move the Unity remainder to
`liminal` and the other Unity projects, and fix `project-lock`'s
cross-reference.

### Phase 4: tooling

Update the installer glob and `.git` gate in both implementations, generalize
the validation scripts, extend `onboard`'s `SkillsFeature` to cover the
relocated skills, and update `skills-dev`'s `.gitmodules`, ruff excludes, and
AGENTS.md authoring workflow.

### Phase 5: archive

Archive the 26 standalone repositories read-only on both forges with a README
banner pointing at the new home. Do not delete: existing clones and external
links should keep resolving.

## Non-goals and invariants

- No change to `SKILL.md` frontmatter, body format, or `agentskills validate`
  conformance.
- No change to runtime install destinations: `~/.agents/skills/<name>/`,
  `~/.claude/skills/<name>/`, `~/.gemini/config/skills/<name>/`, and
  `<hermes>/skills/<name>/` stay flat and per-skill. The family grouping is a
  source-layout concern only and must not leak into installed layout, or every
  harness's skill discovery and the `SKILL_HOOKS` entries `onboard` writes into
  `settings.json` would need to handle nesting.
- The portability rule (no machine-specific absolute paths in tracked files)
  continues to apply to every skill in every location.
