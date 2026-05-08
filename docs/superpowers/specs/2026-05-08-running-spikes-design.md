# Running Spikes — Design Spec

**Date:** 2026-05-08
**Skill name:** `running-spikes`
**Status:** Brainstormed; pending plan-writing.

> Working draft. This spec exists for the brainstorm-to-plan handoff and gets
> distilled into the plan header (Goal / Architecture / Tech Stack), then
> deleted. Lasting artifacts are the SKILL.md itself and skills-dev's CLAUDE.md
> addition.

## Goal

A behavioral skill that flips Claude's default toward **running code** over
**reading more** when the question is about observable behavior of an
external system. Claude over-relies on Read / Grep / WebSearch / thinking
when a 2-minute spike would conclusively answer the question. The user does
this naturally — start a hello-world, hack on it, learn from the running
program. The skill teaches Claude to do the same, within tight gates so it
doesn't become a wandering pest.

**Phase-agnostic.** Fires during brainstorming, plan-writing, AND
mid-implementation. Distinct from `superpowers:systematic-debugging` (which
handles in-flight bug triage) — this skill triggers on *unfamiliarity*, not
on *unexpected failure*.

## Architecture

### New repo + submodule

- **Gitea (primary):** `schoen/skills-running-spikes` (private)
- **GitHub (mirror):** `mtschoen/skills-running-spikes` (public)
- **Submodule path** inside skills-dev: `running-spikes/`
- **Submodule URL** in `.gitmodules`: relative — `../skills-running-spikes.git`
- **Per-submodule remotes:** `origin` → Gitea, `github` → GitHub.
- Use the `gitea` MCP server (per user's global CLAUDE.md) rather than raw
  `curl` for repo creation. The 13-day-old
  `reference_gitea_submodule_workflow.md` has stale `http://llamabox.internal:3000`
  URLs — current state is `https://gitea.llamabox.internal/` and dual tokens
  (`~/.gitea-token` admin / `~/.gitea-token-claude` for the bot identity).

### Repo layout (root layout, matches recent skills)

```
running-spikes/
├── SKILL.md         # the skill itself
├── README.md        # dev-facing
├── evals/           # eval harness; dev-only
├── workspace/       # scratch for eval iteration; gitignored (per pattern)
└── .gitignore       # workspace/, .DS_Store, etc.
```

`install-skills.{sh,bat}` already handles root-layout skills; no installer
changes required. Confirm via `./install-skills.sh -n running-spikes` after
the submodule is added.

## Frontmatter

```yaml
---
name: running-spikes
description: Use when about to do extended Read/Grep/WebSearch/thinking on a question whose answer is observable behavior of an external system, library, framework, or runtime. Default toward action — spin up a hello-world in a scratch dir, hack on it, learn from running code instead of inferring from docs. Tiered: small in-place experiments announce-and-go; new project templates or package installs ask first. Default-throwaway scratch; can be promoted explicitly. Breadcrumbs in ~/.claude/notes/spike_<slug>.md so prior spikes aren't re-litigated; a curated registry indexes the generally-useful ones. Suppressed when the question is about THIS codebase, is subjective/design, or has already been spiked. Fires phase-agnostically — during brainstorming, plan-writing, AND mid-implementation.
---
```

## Trigger model

### Internal signals that suggest a spike

The skill catches these defaults and considers spiking instead:

- "Let me read more docs about how X behaves."
- "Let me grep across other projects for how this is usually done."
- "Let me think through whether Y will work."
- "Let me web-search to confirm Z."

…AND the question is about observable behavior of an external system AND a
small experiment could produce a definitive answer.

### Four suppression gates

Before firing, silently answer. If any is "yes," don't spike — fall back to
the original instinct (read/search/think).

1. **Is this about THIS codebase?** → Read the code or write a test against
   it. Spike scope is for external/unknown systems.
2. **Is the answer subjective / a design opinion?** → No experiment can
   resolve "which feels nicer."
3. **Have I (or have past sessions) already spiked this?** → Check
   `~/.claude/notes/spike_registry.md` first, then glob
   `~/.claude/notes/spike_*.md`. If found, cite and skip.
4. **Did the user just say "just answer"?** → Last-message override beats
   the skill.

Note: the user explicitly chose NOT to suppress on "authoritative docs
exist." Even when docs exist, prefer running code to reading. This is
deliberate — reinforces the skill's bias toward action.

## Mechanics

### Tiering

The boundary is **"does it leave artifacts?"**

**Small (announce-and-go).** One-line heads-up, then go.
- Single-file scripts (`python -c`, `node -e`)
- REPL-style probes (`python -i`, `dotnet fsi`)
- `curl` against a known endpoint
- `<tool> --help` / version checks
- A single file in `.claude/spikes/<slug>/probe.py`

Heads-up format:
> `Spiking on whether httpx follows redirects across schemes — single-file probe.`

**Medium+ (ask first).** Anything that creates artifacts or installs.
- New project templates (`npm init`, `dotnet new`, `cargo new`, `uv init`)
- Package installs
- Cloning third-party repos
- Anything creating `.venv/`, `node_modules/`, `target/`

Ask format:
> `I want to spike on X. Best path is `dotnet new console` in `.claude/spikes/x/` then add SomeThing. ~3 minutes, leaves a scratch dir. OK to proceed?`

### Scratch directory

**Location precedence:**

1. If cwd is a git repo → `.claude/spikes/<slug>/` in the repo root.
   Skill ensures `.gitignore` includes `.claude/spikes/` (adds the entry if
   missing — small in-place change, no separate ask).
2. Otherwise → `~/.claude/spikes/<slug>/`.

**Slug:** kebab-case, 2–4 words. `httpx-redirect-schemes`,
`unity-batch-mode-exit-codes`. On collision (a slug already exists), append
a date suffix (`-20260508`).

**Hygiene:** spike code is **exempt** from TDD, smoke-test,
maintaining-full-coverage, verification-before-completion. Happy path only.
Sloppy is fine. The SKILL.md states this so adjacent skills don't interfere.

### Memory layer

**Per-topic note (always written):** `~/.claude/notes/spike_<slug>.md`

```markdown
---
name: spike <topic>
description: <one-line answer>
type: spike
---

**Question:** <the concrete question this spike answered>

**Answer:** <one or two sentences, lead with conclusion>

**Spiked:** YYYY-MM-DD on <machine>; scratch at `<path>` (may be deleted by now)

**Existence proofs:** <links to working code in this or other projects on
this machine, e.g. `~/cant_stop_the_beat/server.py:42` — only fill in if you
found one>

<free-form narrative: what you tried, what surprised you, gotchas,
references to docs that turned out wrong, etc.>
```

**Curated registry (sometimes):** `~/.claude/notes/spike_registry.md`

Flat list, one line per registered spike, newest at top:

```markdown
# Spike registry

Curated index of spikes whose answers are likely to recur. Per-topic notes
live alongside as `spike_<slug>.md`; only the cross-context-useful ones
get an entry here.

- 2026-05-07 — [httpx redirect schemes](spike_httpx-redirect-schemes.md) — httpx follows http→https but NOT https→http by default; needs custom transport
- 2026-05-03 — [unity batch-mode exit codes](spike_unity-batch-mode-exit-codes.md) — exit 1 on compile error, 2 on test failure, 3 on Editor crash; 0 only on full success
```

### The razor (register-or-not)

After the spike concludes, silently answer:

> *"Would this spike's answer help me on a different project / different
> file / different task in the future?"*

- **Yes** → append a registry line. (Generally useful: library quirks,
  runtime behavior, host-environment facts, framework gotchas.)
- **No** → leave as note-only. (Project-specific: how *this* particular
  service's auth flow works, what *this* schema looks like.)

Not gated on user approval. Cheap, append-only, easy to prune later.

### Pre-spike check (mechanically)

Before firing, in order:

1. Grep `~/.claude/notes/spike_registry.md` for keywords. Hit → cite the
   line, follow the link to the per-topic note, skip the spike.
2. Glob `~/.claude/notes/spike_*.md`. Filename or content match → read the
   note, skip.
3. Check earlier turns of this conversation for in-flight findings the user
   chose not to register.
4. No hit anywhere → proceed.

### Promotion mechanic

When spike yields keep-able code, present three options:

1. **Promote** — user picks destination; agent moves/renames the scratch
   file(s) into the project tree. The per-topic note adds "Promoted to:
   `<path>`."
2. **Keep iterating** — stay in scratch.
3. **Leave as scratch** — answer captured; code disposable.

Promotion crosses a hygiene boundary: once code lands in the project tree,
TDD / smoke-test / maintaining-full-coverage /
verification-before-completion **re-engage**. The SKILL.md states this
explicitly so the agent doesn't carry the "sloppy is fine" license into
production code.

### Exemptions from adjacent skills (while in scratch)

- `superpowers:test-driven-development` — no red-green-refactor.
- `smoke-test` — the spike *is* the smoke test for the question.
- `maintaining-full-coverage` — out of scope until promotion.
- `superpowers:verification-before-completion` — the spike's "completion"
  is "the answer," not "the code is shipped."

All re-engage on promotion.

## Examples (sketch — full text written into SKILL.md)

The SKILL.md will include six example dialogues, modeled on pushback's
example block. Each is a short user/agent exchange showing the trigger
firing or being suppressed:

- **A.** Small spike, announce-and-go (httpx redirect schemes during design).
- **B.** Medium+ spike, ask first (Cosmos DB partition keys mid-implementation).
- **C.** Suppression: this codebase question — agent reads instead.
- **D.** Suppression: prior spike found — agent cites the registry and skips.
- **E.** Promotion offer — three-option gate after a successful spike.
- **F.** User override — "just answer" → no spike.

## Self-check

### Pre-fire

Before announcing a spike, silently answer:

- **Bucket:** is this an *observable behavior* question about an *external*
  system?
- **Gates:** did I check all four suppression gates? Specifically, did I grep
  `~/.claude/notes/spike_*.md` and `spike_registry.md`?
- **Tier:** small or medium+? Asking when I should ask, announcing-and-going
  when I should?
- **Frame:** can I state the spike's question in one concrete sentence? If
  not, scope is too vague — narrow before starting.

### Post-spike

Before reporting back to the user:

- **Answered the question?** Did the spike actually produce evidence for the
  original question, or did I drift? If drifted, summarize what was learned
  but flag the original question is still open.
- **Wrote the note?** Per-topic file at `~/.claude/notes/spike_<slug>.md`
  with Question / Answer / Spiked / Existence-proofs.
- **Applied the razor?** Registered if generally useful; left as note-only
  otherwise.
- **Offered promotion if relevant?** Three-option gate.
- **Closed out scratch?** Either left it or noted that it's deletable.

## Anti-patterns

- **Spiking on the user's codebase.** "Let me write a quick test to see how
  their `parseConfig` behaves" — that's READING with extra steps.
- **Spiking to look thorough.** If one WebFetch / one doc page would answer
  it, do that. The skill's bias toward action is calibrated against a real
  read-loop, not against five-minute lookups.
- **Skipping the prior-spike check.** Cross-session memory only works if
  every spike checks `~/.claude/notes/` first.
- **Skipping the per-topic note.** Without the note, next session re-spikes.
  The note is the value; the scratch code is incidental.
- **Carrying "sloppy is fine" into promoted code.** Once promotion happens,
  full discipline re-engages.
- **Manufacturing "general usefulness" to register every spike.** Registry's
  value is its curation. If everything is generally useful, nothing is.
- **Auto-promoting without the gate.** User picks promotion, not the agent.
- **Spiking on a subjective question.** "Should we use axios or fetch" has
  no experiment-resolvable fundamental answer (though "does fetch handle X
  edge case" might). Frame tightly or don't spike.

## Implementation deliverables (for plan-writing phase)

1. **Create skill repos.** `schoen/skills-running-spikes` on Gitea (private)
   and `mtschoen/skills-running-spikes` on GitHub (public). Use the `gitea`
   MCP server. Bot identity (`~/.gitea-token-claude`) for Claude-acting
   creates.
2. **Write `running-spikes/SKILL.md`.** Frontmatter, "Why this skill exists,"
   trigger model, four gates, mechanics (tiering, scratch dir, memory,
   registry, pre-spike check, promotion, exemptions), six examples, pre-fire
   and post-spike self-check, anti-patterns. Target ~250 lines, modeled on
   `pushback/SKILL.md`.
3. **Write `running-spikes/README.md`.** Dev-facing one-pager.
4. **Add `running-spikes/.gitignore`.** `workspace/`, `.DS_Store`, etc.
5. **Add as submodule in skills-dev.** `git submodule add
   ../skills-running-spikes.git running-spikes` from the skills-dev root.
   Set per-submodule remotes (`origin` → Gitea, `github` → GitHub).
6. **Confirm install-skills picks it up.** `./install-skills.sh -n
   running-spikes` should preview the copy without errors.
7. **Add `CLAUDE.md` to skills-dev root.** This is a real gap — the user
   reminded us the new-skill-needs-new-repo workflow isn't documented in the
   repo. The CLAUDE.md should:
   - State that every new top-level skill in skills-dev requires its own
     `skills-<name>` repo on both Gitea and GitHub.
   - Point at the per-project memory note
     (`reference_gitea_submodule_workflow.md`) for the concrete steps.
   - Note the relative-URL convention in `.gitmodules` and the
     `origin`/`github` remote split.
8. **Stub `running-spikes/evals/`.** At minimum, a placeholder
   `README.md` describing the evaluation approach. Full eval harness can
   come in a follow-up — initial release focuses on shipping the SKILL.md.
9. **Push to both hosts.** `scripts/push-all.{sh,bat}` from skills-dev once
   the submodule is added and committed.

## Open questions / things to revisit

- **Eval methodology.** Memory says "don't iterate skills on n=1 evals"
  (`feedback_no_iteration_on_n1.md`) and "skills shaping conversational
  behavior may not transfer to the agent's own trajectory"
  (`feedback_skill_self_application.md`). Initial release ships the SKILL.md
  and a placeholder evals dir; the eval harness lands in a follow-up. The
  plan should not block first install on full evals.
- **Slug collision.** Spec'd minimal: append a date suffix. SKILL.md will say
  this in one line.
- **Scratch cleanup.** `.claude/spikes/<slug>/` accumulates over time. The
  skill doesn't auto-delete; relies on the user (or the `wrap` skill) to
  clean. Acceptable for v1.
- **Self-application risk.** Behavioral skills sometimes don't apply to the
  agent that authored them. Watch for the user surfacing "you're still
  reading instead of running" in the first few sessions after install — that
  signals the trigger language needs sharpening.
