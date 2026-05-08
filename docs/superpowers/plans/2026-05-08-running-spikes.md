# Running Spikes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a new behavioral skill `running-spikes` that flips Claude's default toward running code over reading more when the question is observable behavior of an external system. Distribute it as a new submodule of `skills-dev`, with mirrors on both Gitea (`schoen/skills-running-spikes`, primary) and GitHub (`mtschoen/skills-running-spikes`, public). Also fill the `skills-dev` CLAUDE.md gap so the new-skill-needs-new-repo workflow is documented in the repo, not just in cross-project memory.

**Architecture:** New top-level skill directory `running-spikes/` inside `skills-dev`, root layout (`SKILL.md` at root, `evals/` and `README.md` excluded from install). Phase-agnostic behavioral skill (similar in shape to `pushback`): trigger discipline + four suppression gates, tiered announcement (small in-place announce-and-go vs. medium+ ask-first), default-throwaway scratch dir at `.claude/spikes/<slug>/`, breadcrumb memory at `~/.claude/notes/spike_<slug>.md` plus a curated `spike_registry.md`, explicit promotion gate, exemptions from adjacent discipline skills. Mirrored to Gitea + GitHub via the relative-URL submodule convention already in use for the 14 existing skills.

**Tech Stack:** Markdown for SKILL.md / README.md / CLAUDE.md. Bash for git operations on Windows (Git Bash). `curl` against `https://gitea.llamabox.internal/api/v1/` (token `~/.gitea-token` for `schoen` admin) for the Gitea repo create. `gh repo create` for the GitHub repo. Existing `install-skills.sh` and `scripts/push-all.sh` for install verification and dual-host push.

---

## Phase 1: Author skill content locally

Author the skill files in a temporary `running-spikes/` directory inside `skills-dev`. The directory is plain (not yet a git repo or submodule); it gets converted in Phase 3.

### Task 1: Create `running-spikes/SKILL.md`

**Files:**
- Create: `running-spikes/SKILL.md`

- [x] **Step 1: Create the directory and write `SKILL.md` with the full skill text**

```bash
mkdir -p running-spikes
```

Then write `running-spikes/SKILL.md` with this exact content:

````markdown
---
name: running-spikes
description: Use when about to do extended Read/Grep/thinking on a question whose answer is observable behavior of an external system, library, framework, or runtime. Default toward action — spin up a hello-world in a scratch dir, hack on it, learn from running code instead of inferring from docs. Tiered: small in-place experiments announce-and-go; new project templates or package installs ask first. Default-throwaway scratch; can be promoted explicitly. Breadcrumbs in ~/.claude/notes/spike_<slug>.md so prior spikes aren't re-litigated; a curated registry indexes the generally-useful ones. Suppressed when the question is about THIS codebase, is subjective/design, or has already been spiked. Fires phase-agnostically — during brainstorming, plan-writing, AND mid-implementation.
---

# Running Spikes

## Why this skill exists

The agent's default is to read more, search more, think more — even when running code would resolve the question in five minutes. That habit costs sessions: long Read/Grep loops produce confidence-without-evidence, and architectural decisions get made on training-data hunches that fall over on first contact with the actual system.

**Failure mode this skill prevents:** spending 20 minutes "researching" what a 2-minute spike would conclusively answer, then making a decision on inferred behavior that turns out wrong.

**Failure mode this skill must NOT create:** the agent constantly spins up scratch projects to "be thorough," scattering artifacts, blowing the auth-prompt budget on package installs, avoiding the real codebase. The skill is tightly gated.

## The trigger moment

Fires when the agent catches itself reaching for one of these defaults:

- "Let me read more docs about how X behaves."
- "Let me grep across other projects for how this is usually done."
- "Let me think through whether Y will work."

…AND the question is about **observable behavior of an external system** (library, framework, runtime, host environment, third-party API) AND a small experiment could produce a definitive answer.

(Web-search is a natural fourth signal but is parked — the project's UserPromptSubmit hook actively pushes Claude toward WebSearch on design / planning prompts; pairing the spike skill on that signal would over-fire. The three signals above carry the action-bias for now.)

## The four suppression gates

Before firing, silently answer. If any is "yes," don't spike — fall back to the original instinct.

1. **Is this about THIS codebase?** → Read the code or write a test against it. Spike scope is for external/unknown systems.
2. **Is the answer subjective / a design opinion?** → No experiment can resolve "which feels nicer." Reason it out.
3. **Have I (or have past sessions) already spiked this?** → Check `~/.claude/notes/spike_registry.md` first, then glob `~/.claude/notes/spike_*.md`. If found, cite and skip.
4. **Did the user just say "just answer"?** → Last-message override beats the skill.

Note: "authoritative docs exist" is deliberately NOT a suppression gate. Even when docs exist, prefer running code to reading. Reinforces the bias toward action.

## Tiering — small vs. medium+

The boundary is **"does it leave artifacts beyond a single scratch file?"**

**Small (announce-and-go):**
- Single-file scripts (`python -c`, `node -e`)
- REPL-style probes (`python -i`, `dotnet fsi`)
- `curl` against a known endpoint
- `<tool> --help` / version checks
- A single file in `.claude/spikes/<slug>/probe.py` (the dir itself is the only filesystem footprint)

Heads-up format — one line, then go:

> "Spiking on whether httpx follows redirects across schemes — single-file probe."

**Medium+ (ask first):**
- New project templates (`npm init`, `dotnet new`, `cargo new`, `uv init`)
- Package installs (`pip install`, `npm install`)
- Cloning third-party repos to inspect
- Anything creating `.venv/`, `node_modules/`, `target/`, etc.

Ask format:

> "I want to spike on X. Best path is `dotnet new console` in `.claude/spikes/x/` then add SomeThing. ~3 minutes, leaves a scratch dir. OK to proceed?"

## Scratch directory

**Location precedence:**

1. If cwd is a git repo → `.claude/spikes/<slug>/` in repo root, gitignored. Skill adds `.claude/spikes/` to `.gitignore` if missing (one-line in-place change, bundled into the spike setup).
2. Otherwise → `~/.claude/spikes/<slug>/`.

**Slug:** kebab-case, 2–4 words. `httpx-redirect-schemes`, `unity-batch-mode-exit-codes`. On collision (a slug already exists), append a date suffix (e.g., `-20260508`).

**Hygiene:** spike code is exempt from TDD, smoke-test, maintaining-full-coverage, and verification-before-completion (see "Exemptions" below). Happy path only. Sloppy is fine. The spike's only verification is "did the code run and produce the answer."

## Memory layer

### Per-topic note (always written)

`~/.claude/notes/spike_<slug>.md`:

```markdown
---
name: spike <topic>
description: <one-line answer>
type: spike
---

**Question:** <the concrete question this spike answered>

**Answer:** <one or two sentences, lead with the conclusion>

**Spiked:** YYYY-MM-DD on <machine>; scratch at `<path>` (may be deleted by now)

**Existence proofs:** <links to working code in this or other projects on this machine, e.g. `~/cant_stop_the_beat/server.py:42` — only fill in if you found one>

<free-form narrative: what you tried, what surprised you, gotchas, references to docs that turned out wrong>
```

The bar is low — it's a breadcrumb for future-you. Always written.

### Curated registry (sometimes)

`~/.claude/notes/spike_registry.md`:

```markdown
# Spike registry

Curated index of spikes whose answers are likely to recur. Per-topic notes live alongside as `spike_<slug>.md`; only the cross-context-useful ones get an entry here.

- 2026-05-07 — [httpx redirect schemes](spike_httpx-redirect-schemes.md) — httpx follows http→https but NOT https→http by default; needs custom transport
- 2026-05-03 — [unity batch-mode exit codes](spike_unity-batch-mode-exit-codes.md) — exit 1 on compile error, 2 on test failure, 3 on Editor crash; 0 only on full success
```

Newest at top. One line per registered spike: date — title (linked) — one-sentence TL;DR.

### The razor — register or not?

After the spike concludes, silently answer:

> "Would this spike's answer help me on a different project / different file / different task in the future?"

- **Yes** → append a registry line. (Generally useful: library quirks, runtime behavior, host-environment facts, framework gotchas.)
- **No** → leave as note-only. (Project-specific: how *this* particular service's auth flow works, what *this* schema looks like.)

Not gated on user approval. Cheap, append-only, easy to prune later.

## Pre-spike check

Before firing on a topic, in order:

1. Grep `~/.claude/notes/spike_registry.md` for keywords. Hit → cite the line, follow the link to the per-topic note, skip the spike.
2. Glob `~/.claude/notes/spike_*.md`. Filename or content match → read the note, skip.
3. Check earlier turns of this conversation for in-flight findings the user chose not to register.
4. No hit anywhere → proceed.

## Promotion mechanic

When the spike yields keep-able code, present three options:

> "The hello-world is working and matches what your <component> needs. Three options:
> 1. **Promote** — move `.claude/spikes/<slug>/probe.py` into `<destination-path>` as the foundation. From there it re-engages TDD/smoke-test/coverage as normal production code.
> 2. **Keep iterating** — refine in scratch first.
> 3. **Leave as scratch** — I have what I need; the spike note is saved.
>
> Which?"

If promoted, the per-topic note gains a line: `**Promoted to:** <path>`.

Promotion crosses a hygiene boundary. Once code lands in the project tree, TDD / smoke-test / maintaining-full-coverage / verification-before-completion **re-engage**. Don't carry the "sloppy is fine" license into production code.

## Exemptions from adjacent skills (while in scratch)

Spike code is exempt from:

- `superpowers:test-driven-development` — no red-green-refactor; this isn't production.
- `smoke-test` — the spike *is* the smoke test for the question.
- `maintaining-full-coverage` — out of scope until promotion.
- `superpowers:verification-before-completion` — the spike's "completion" is "the answer," not "the code is shipped."

All re-engage on promotion.

## Examples

**Example A — small spike, announce-and-go (during design):**

> User: "I'm thinking about using `httpx` for the new client. Will it follow redirects across http→https and back?"
>
> Agent: "I could read docs but the cleanest way to know is to run it. Spiking on httpx redirect behavior — single-file probe at `.claude/spikes/httpx-redirect-schemes/probe.py`, ~30 seconds.
>
> [runs the probe, observes behavior]
>
> Result: with `follow_redirects=True`, httpx follows http→https but NOT https→http by default — security guardrail. To allow it, you build a custom transport. Note saved at `~/.claude/notes/spike_httpx-redirect-schemes.md` and registered (likely to recur). For your client: do you actually need https→http, or is the default safe?"

**Example B — medium+ spike, ask first (mid-implementation):**

> User: "Add a Cosmos DB persistence layer to the order service."
>
> Agent: "Before I wire this in — I want to confirm a few things about partition key constraints and the bulk-execution path before designing the data access layer. Quickest path is `dotnet new console` in `.claude/spikes/cosmos-bulk-partition/` and a 30-line probe against the local emulator. ~5 minutes, leaves a scratch dir. OK?"

**Example C — suppression: this codebase question (don't spike, read):**

> User: "Does our `sanitizeFilename` actually strip backslashes on Windows, or just forward slashes?"
>
> Agent: [grep + read `sanitizeFilename`, answer from the actual code — gate 1 fires, no spike]

**Example D — suppression: prior spike found (cite the registry):**

> User: "I'm wondering about httpx redirect behavior across schemes."
>
> Agent: "Already spiked this on 2026-05-07 — see `~/.claude/notes/spike_httpx-redirect-schemes.md`. TL;DR: `follow_redirects=True` follows http→https but not https→http by default; needs a custom transport for the latter. Working from that, do you want the default or the custom transport?"

**Example E — promotion offer:**

> Agent (after a spike that yielded a working `redirect_client.py`): "The hello-world is working and matches what your order service needs. Three options:
> 1. **Promote** — move `.claude/spikes/httpx-redirect-schemes/probe.py` into `src/clients/http_client.py` as the starting foundation. From there it re-engages TDD/smoke-test/coverage as normal production code.
> 2. **Keep iterating** — refine in scratch first.
> 3. **Leave as scratch** — I have what I need; the spike note is saved.
>
> Which?"

**Example F — no-spike override:**

> User: "Just answer from the docs — no scratch project right now."
>
> Agent: "Got it, no spike. From the httpx docs: ..." [answers in text — gate 4 fires]

## Pre-fire self-check

Before announcing a spike, silently answer:

- **Bucket:** is this an *observable behavior* question about an *external* system?
- **Gates:** did I check all four suppression gates? Specifically, did I grep `~/.claude/notes/spike_*.md` and `spike_registry.md`?
- **Tier:** small or medium+? Asking when I should ask, announcing-and-going when I should?
- **Frame:** can I state the spike's question in one concrete sentence? If not, scope is too vague — narrow it before starting.

If any check is "no," reset.

## Post-spike self-check

Before reporting back to the user:

- **Answered the question?** Did the spike actually produce evidence for the original question, or did I drift? If drifted, summarize what was learned but flag the original question is still open.
- **Wrote the note?** Per-topic file at `~/.claude/notes/spike_<slug>.md` with Question / Answer / Spiked / Existence-proofs.
- **Applied the razor?** If generally useful, appended a line to `spike_registry.md`.
- **Offered promotion if relevant?** If the spike code is keep-able and the user would plausibly want it in the project, offered the three-option gate.
- **Closed out scratch?** Either left it (default) or noted that it's deletable.

## Anti-patterns

- **Spiking on the user's codebase.** "Let me write a quick test to see how their `parseConfig` behaves" — that's READING with extra steps. Just read it.
- **Spiking to look thorough.** If reading the official docs answers it in one Fetch, do that. The skill's bias toward action is calibrated against a real read-loop, not against five-minute single-page lookups.
- **Skipping the prior-spike check.** Cross-session memory only works if every spike checks `~/.claude/notes/` first. Re-deriving an answer that's already on disk is wasted session.
- **Skipping the per-topic note.** Without the note, the next session re-spikes. The note is the value; the scratch code is incidental.
- **Carrying "sloppy is fine" into promoted code.** Once promotion happens, full discipline re-engages.
- **Manufacturing "general usefulness" to register every spike.** The registry's value is its curation. If everything is generally useful, nothing is.
- **Auto-promoting without the gate.** The user picks promotion, not the agent.
- **Spiking on a subjective question.** "Should we use axios or fetch" doesn't have an experiment-resolvable answer about the fundamental choice — though "does fetch handle X edge case" might. Frame tightly or don't spike.
````

- [x] **Step 2: Verify the file was written and is well-formed**

```bash
test -f running-spikes/SKILL.md && echo "OK: SKILL.md exists ($(wc -l < running-spikes/SKILL.md) lines)" || echo "FAIL: SKILL.md missing"
head -3 running-spikes/SKILL.md
```

Expected: `OK: SKILL.md exists (~280 lines)` and the first three lines being the YAML frontmatter (`---`, `name: running-spikes`, `description: ...`).

---

### Task 2: Write `running-spikes/README.md`

**Files:**
- Create: `running-spikes/README.md`

- [x] **Step 1: Write the dev-facing README**

```markdown
# running-spikes

Claude Code skill that flips Claude's default toward **running code** over **reading more** when the question is observable behavior of an external system.

Lives as a submodule under [skills-dev](https://github.com/mtschoen/skills-dev) and installed via `install-skills.{sh,bat}`.

## What it does

Phase-agnostically detects when Claude is about to do extended Read / Grep / thinking on a question that running code could resolve in a few minutes. Suggests a small spike (single-file probe or scratch hello-world) instead. Findings land in `~/.claude/notes/spike_<slug>.md` so future sessions don't re-litigate.

See [SKILL.md](./SKILL.md) for the full skill text.

## Conventions

- **Repo name:** `skills-running-spikes` on both Gitea (`schoen/`) and GitHub (`mtschoen/`).
- **Submodule path** in skills-dev: `running-spikes/`.
- **Workspace** for eval iteration lives at `running-spikes/workspace/`, gitignored.
- **License:** MIT (inherits from skills-dev).
```

- [x] **Step 2: Verify**

```bash
test -f running-spikes/README.md && echo "OK"
```

---

### Task 3: Write `running-spikes/.gitignore`

**Files:**
- Create: `running-spikes/.gitignore`

- [x] **Step 1: Write the gitignore**

```
workspace/
.DS_Store
*.pyc
__pycache__/
```

- [x] **Step 2: Verify**

```bash
test -f running-spikes/.gitignore && echo "OK"
```

---

### Task 4: Stub `running-spikes/evals/`

**Files:**
- Create: `running-spikes/evals/README.md`

- [x] **Step 1: Create the evals directory and placeholder README**

```bash
mkdir -p running-spikes/evals
```

Then write `running-spikes/evals/README.md`:

```markdown
# running-spikes evals

Placeholder. The eval harness for this skill is deferred for v1 — initial release ships the SKILL.md only.

When implemented, evals should test:

- Trigger fires correctly on observable-behavior questions about external systems.
- All four suppression gates work (this codebase / subjective / prior-spiked / user-override).
- Tiering applies correctly (small announce-and-go vs. medium+ ask-first boundary).
- Memory layer (per-topic note + curated registry) is written and read consistently across spikes.
- Promotion mechanic is offered when scratch code is keep-able.

See `pushback/evals/` for the harness pattern this should follow. Behavioral skills sometimes don't apply to the agent that authored them (see `feedback_skill_self_application.md` in cross-project memory) — qualitative real-session testing matters more than n=1 eval runs (see `feedback_no_iteration_on_n1.md`).
```

- [x] **Step 2: Verify**

```bash
test -f running-spikes/evals/README.md && echo "OK"
```

---

### Task 5: Local content sanity check

- [x] **Step 1: List the directory tree**

```bash
find running-spikes -type f | sort
```

Expected output (exact):
```
running-spikes/.gitignore
running-spikes/README.md
running-spikes/SKILL.md
running-spikes/evals/README.md
```

- [x] **Step 2: Confirm install-skills.sh would pick it up correctly (dry-run)**

Note: `install-skills.sh` only sees skills that are listed as submodules in `.gitmodules`, so a dry run before submodule conversion will report "not initialized." That's expected — full install verification happens in Task 12 after the submodule is added. For now, just confirm the skill content has the right shape:

```bash
head -3 running-spikes/SKILL.md   # Expect: ---, name: running-spikes, description: ...
grep -c '^## ' running-spikes/SKILL.md  # Expect: 12 or so (Why, Trigger, Gates, Tiering, Scratch, Memory, Pre-spike, Promotion, Exemptions, Examples, Pre-fire, Post-spike, Anti-patterns)
```

---

## Phase 2: Create remote repos

Both repos are created **before** any local commits so the local push has a target.

### Task 6: Create Gitea repo `schoen/skills-running-spikes`

**Files:** none locally — remote repo creation only.

- [x] **Step 1: Confirm the repo doesn't already exist**

The user's global CLAUDE.md authoritatively documents the current Gitea state:
- Endpoint: `https://gitea.llamabox.internal/`
- Token for schoen-admin actions: `~/.gitea-token`
- Token for claude-code bot actions: `~/.gitea-token-claude`

Skill repos are owned by `schoen`. To create under that namespace, use the `schoen` token (`~/.gitea-token`) — `claude-code` cannot create repos in another user's namespace via `/user/repos`.

```bash
TOKEN=$(cat ~/.gitea-token | tr -d '\n\r')
curl -sk "https://gitea.llamabox.internal/api/v1/repos/schoen/skills-running-spikes" \
  -H "Authorization: token $TOKEN" -o /dev/null -w "%{http_code}\n"
```

Expected: `404`. If it returns `200`, the repo already exists — stop and investigate.

- [x] **Step 2: Create the repo**

```bash
TOKEN=$(cat ~/.gitea-token | tr -d '\n\r')
curl -sk -X POST "https://gitea.llamabox.internal/api/v1/user/repos" \
  -H "Authorization: token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"skills-running-spikes","description":"Claude Code skill: flips default toward running code over reading more when the question is observable behavior of an external system","private":true,"default_branch":"main","auto_init":false}' \
  -w "\nHTTP %{http_code}\n"
```

Expected: HTTP `201` and a JSON body containing `"full_name":"schoen/skills-running-spikes"`.

- [x] **Step 3: Sanity-check the new repo**

```bash
TOKEN=$(cat ~/.gitea-token | tr -d '\n\r')
curl -sk "https://gitea.llamabox.internal/api/v1/repos/schoen/skills-running-spikes" \
  -H "Authorization: token $TOKEN" | grep -o '"full_name":"[^"]*"'
```

Expected: `"full_name":"schoen/skills-running-spikes"`.

---

### Task 7: Create GitHub repo `mtschoen/skills-running-spikes`

**Files:** none locally — remote repo creation only.

- [x] **Step 1: Confirm `gh` is authenticated as `mtschoen`**

```bash
gh auth status
```

Expected: confirmation that `gh` is logged in as `mtschoen`.

- [x] **Step 2: Create the repo**

```bash
gh repo create mtschoen/skills-running-spikes \
  --public \
  --description "Claude Code skill: flips default toward running code over reading more when the question is observable behavior of an external system"
```

Expected: a URL like `https://github.com/mtschoen/skills-running-spikes`.

- [x] **Step 3: Sanity-check**

```bash
gh repo view mtschoen/skills-running-spikes --json name,visibility,description
```

Expected: JSON with `"name":"skills-running-spikes"`, `"visibility":"PUBLIC"`, the description set above.

---

## Phase 3: Convert local dir to submodule

Following the workflow at `~/.claude/projects/C--Users-mtsch-skills-dev/memory/reference_gitea_submodule_workflow.md`, with the corrected URL/token from the user's global CLAUDE.md (the memory's `http://llamabox.internal:3000` is stale).

### Task 8: Init local repo, configure committer, commit, push to Gitea

**Files:**
- Modify: `running-spikes/` becomes a git repo with one commit on `main`.

- [x] **Step 1: Initialize git in the skill directory**

```bash
cd running-spikes
git init -q -b main
```

- [x] **Step 2: Configure committer as `claude-code`**

Per the user's global CLAUDE.md: "Commits as claude-code: set `user.name=claude-code` and `user.email=claude-code@llamabox.internal` so the PR author matches the token holder." This first commit is Claude-authored content, so use that identity locally for this repo only.

```bash
git config user.name "claude-code"
git config user.email "claude-code@llamabox.internal"
```

- [x] **Step 3: Stage all skill content and commit**

```bash
git add -A
git -c commit.gpgsign=false commit -m "Initial commit: running-spikes skill"
```

(Git-for-Windows CRLF warnings are cosmetic; ignore.)

- [x] **Step 4: Add the Gitea remote and push**

```bash
git remote add origin gitea@llamabox.internal:schoen/skills-running-spikes.git
git push -u origin main
```

Expected: a push report ending with `* [new branch]      main -> main`.

If the push fails with `Host key verification failed`, run once:
```bash
ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes -T gitea@llamabox.internal
```
…then retry the push.

---

### Task 9: Remove the local dir to make room for the submodule clone

**Files:**
- Delete: `running-spikes/` (entire directory)

- [x] **Step 1: Change cwd OUT of the directory before removing it**

The Windows gotcha from the workflow note: `rm -rf` from inside the dir or with stale handles can fail with "Device or resource busy." Step out first.

```bash
cd ..
pwd  # Expect: C:/Users/mtsch/skills-dev (or equivalent)
```

- [x] **Step 2: Remove the directory**

```bash
rm -rf running-spikes
```

If `rm -rf` empties the dir but fails to remove the husk:
```bash
rmdir running-spikes
```

- [x] **Step 3: Verify removal**

```bash
test ! -e running-spikes && echo "OK: removed" || echo "FAIL: still exists"
```

Expected: `OK: removed`.

---

### Task 10: Add `running-spikes` as a submodule with a relative URL

**Files:**
- Modify: `.gitmodules` (new submodule entry appended)
- Create: `running-spikes/` (cloned from Gitea by `git submodule add`)

- [x] **Step 1: Add the submodule with a relative URL**

The relative URL convention is per `feedback_github_skills_naming.md` — `.gitmodules` should have `url = ../skills-running-spikes.git` so a fresh clone resolves the submodule against whichever host the index was cloned from.

```bash
git submodule add ../skills-running-spikes.git running-spikes
```

Expected: a clone log followed by the submodule appearing in `git status`. Internally this:
- Adds a `[submodule "running-spikes"]` entry to `.gitmodules` with `path = running-spikes` and `url = ../skills-running-spikes.git`.
- Clones the Gitea repo into `running-spikes/`.
- Stages `.gitmodules` and `running-spikes` (the gitlink) for commit.

- [x] **Step 2: Verify the relative URL was used**

```bash
grep -A2 'submodule "running-spikes"' .gitmodules
```

Expected output:
```
[submodule "running-spikes"]
	path = running-spikes
	url = ../skills-running-spikes.git
```

If the URL is absolute (e.g., starts with `gitea@` or `https://`), correct it:
```bash
git config -f .gitmodules submodule.running-spikes.url ../skills-running-spikes.git
git config -f running-spikes/.git/config remote.origin.url gitea@llamabox.internal:schoen/skills-running-spikes.git
```

- [x] **Step 3: Verify the working-tree origin is the SSH Gitea URL**

The submodule's *working tree* should still point at the SSH Gitea URL for daily git ops. (Per the user's global memory: don't run `git submodule sync` after fixing — it can overwrite the working-tree URL inconsistently.)

```bash
git -C running-spikes remote -v
```

Expected:
```
origin  gitea@llamabox.internal:schoen/skills-running-spikes.git (fetch)
origin  gitea@llamabox.internal:schoen/skills-running-spikes.git (push)
```

If `origin` shows the relative URL instead of the SSH URL, fix it:
```bash
git -C running-spikes remote set-url origin gitea@llamabox.internal:schoen/skills-running-spikes.git
```

---

### Task 11: Configure the GitHub remote on the submodule and push

**Files:** none locally — submodule git config + remote push.

- [x] **Step 1: Add the `github` remote on the submodule**

Per `feedback_github_skills_naming.md`, the per-submodule remote convention is `origin` → Gitea, `github` → GitHub.

```bash
git -C running-spikes remote add github https://github.com/mtschoen/skills-running-spikes.git
```

- [x] **Step 2: Push to GitHub**

```bash
git -C running-spikes push -u github main
```

Expected: `* [new branch]      main -> main`. If gh is set up to use https with credential helper, no extra steps; if it's set up with ssh, swap the URL to `git@github.com:mtschoen/skills-running-spikes.git` (use whichever pattern the existing skill submodules use — verify with `git -C ../pushback remote -v`).

- [x] **Step 3: Verify both remotes**

```bash
git -C running-spikes remote -v
```

Expected: `origin` → `gitea@llamabox.internal:schoen/skills-running-spikes.git`, `github` → the GitHub URL, both fetch + push lines.

---

### Task 12: Verify `install-skills.sh` picks up the new submodule

**Files:** none modified — read-only verification.

- [x] **Step 1: Run install-skills dry-run for the new skill**

```bash
./install-skills.sh -n running-spikes
```

Expected: a "would copy" listing showing `running-spikes/SKILL.md` and the README/dev files **excluded** (`evals/`, `README.md`, `.gitignore`, `.git/`). No errors. The output should mention "root layout."

If the script reports "not initialized" or "skill not found," check that the submodule's working tree has SKILL.md:
```bash
ls running-spikes/SKILL.md
git -C running-spikes log --oneline -1   # Should show the initial commit
```

- [ ] **Step 2: (Optional) Actually install and verify in `~/.claude/skills/`**

```bash
./install-skills.sh -y running-spikes
ls ~/.claude/skills/running-spikes/SKILL.md && echo "OK: installed"
head -3 ~/.claude/skills/running-spikes/SKILL.md
```

Expected: SKILL.md is present in the install dir with the correct frontmatter.

---

### Task 13: Commit the submodule pointer in skills-dev

**Files:**
- Modify: `.gitmodules` (already staged by `git submodule add`)
- Create: `running-spikes` (gitlink, already staged)

- [x] **Step 1: Confirm what's staged**

```bash
git status
```

Expected: `.gitmodules` and `running-spikes` both staged for commit (modified + new respectively).

- [x] **Step 2: Commit**

```bash
git -c commit.gpgsign=false commit -m "Add running-spikes as submodule"
```

(Use the user's normal committer for skills-dev itself — don't apply the `claude-code` identity from Task 8; that was scoped to the new repo's first commit.)

- [x] **Step 3: Verify the commit**

```bash
git log --oneline -1
git show --stat HEAD | head -20
```

Expected: a single-commit diff showing `.gitmodules` modified and `running-spikes` added (as a 160000-mode gitlink).

---

## Phase 4: Document the new-skill-needs-new-repo workflow in skills-dev

The user explicitly flagged this gap during brainstorming: skills-dev currently has no `CLAUDE.md` or `AGENTS.md`, so the submodule workflow lives only in cross-project memory. This phase fills that gap.

### Task 14: Write `skills-dev/CLAUDE.md`

**Files:**
- Create: `CLAUDE.md` (at the skills-dev repo root)

- [x] **Step 1: Write the CLAUDE.md**

```markdown
# skills-dev — Claude Code instructions

This repo is the umbrella that ties together each skill's own submodule. Every top-level directory other than `.claude/`, `docs/`, `scripts/`, `LICENSE`, and `install-skills.*` is a git submodule pointing at that skill's own repository, mirrored on Gitea (primary) and GitHub (public).

## Adding a new skill

**Every new skill needs its own repo.** Don't add a new top-level directory directly to skills-dev — convert it to a submodule.

The workflow:

1. Author the skill content locally in a temporary `<name>/` directory inside skills-dev.
2. Create the remote repos:
   - Gitea: `schoen/skills-<name>` (private). Owned by `schoen`, so use `~/.gitea-token` (admin), not `~/.gitea-token-claude` (which can't create under another user's namespace).
   - GitHub: `mtschoen/skills-<name>` (public). Use `gh repo create`.
3. Init the local dir as git, commit (with `user.name=claude-code` for Claude-authored first commits, per the user's global CLAUDE.md), push to Gitea.
4. Remove the local dir. **Windows gotcha:** `cd ..` first to avoid `Device or resource busy` on the cwd.
5. Add as submodule. **Important sequencing pitfall:** `git submodule add ../skills-<name>.git <name>` resolves the relative URL against the superproject's first-listed remote (alphabetically `github` before `origin`). At this point in the workflow GitHub is still empty (we only pushed to Gitea in step 3), so the relative-URL form fails with "cloned an empty repository / branch yet to be born." Use the **absolute Gitea URL** initially, then rewrite `.gitmodules` to the relative form afterwards:
   ```bash
   git submodule add gitea@llamabox.internal:schoen/skills-<name>.git <name>
   git config -f .gitmodules submodule.<name>.url ../skills-<name>.git
   ```
   Do NOT run `git submodule sync` after the rewrite — it can propagate the relative URL to `.git/config` and break daily git ops. The submodule's working-tree origin should remain the SSH Gitea URL.
6. Configure per-submodule remotes: `origin` → Gitea (SSH, already set by step 5), `github` → GitHub (SSH, `git@github.com:mtschoen/skills-<name>.git`). Push to GitHub: `git -C <name> push -u github main`.
7. Confirm `install-skills.{sh,bat}` picks up the new skill via dry run: `./install-skills.sh -n <name>`.
8. Commit the submodule pointer in skills-dev.
9. Run `scripts/push-all.{sh,bat}` to push both hosts.

The detailed concrete steps (with current Gitea endpoints and Windows gotchas) live at `~/.claude/projects/C--Users-mtsch-skills-dev/memory/reference_gitea_submodule_workflow.md`. Read that first; the user's global CLAUDE.md (`Gitea (self-hosted)` section) has the current state since the memory note may predate URL/token changes.

## Naming conventions

- Repo names use the `skills-<name>` prefix on **both** hosts. The skills-dev submodule path is the bare `<name>` (no prefix).
- `.gitmodules` uses **relative URLs** (`../skills-<name>.git`) so the same `.gitmodules` resolves correctly whether the index was cloned from Gitea or GitHub.
- Per-submodule remote convention: `origin` → Gitea (SSH), `github` → GitHub.
- Don't run `git submodule sync` after manually fixing a submodule's `origin` URL — it can overwrite working-tree URLs from `.gitmodules` resolution. The submodule directories in skills-dev have full `.git/` dirs (not gitfiles), so daily git ops read from `<sub>/.git/config`, not `.git/modules/<sub>/config`.

## Layout

Per-skill repos use the **root layout**: `SKILL.md` at the repo root, plus `evals/`, `README.md`, and `workspace/` (gitignored). The legacy `skill-draft/` layout is deprecated; new skills use the root layout. The installer (`install-skills.{sh,bat}`) detects which layout is in use and excludes dev-only files (`evals/`, `README.md`, `LICENSE`, etc.) for root-layout skills.

## Working across all submodules

- `scripts/push-all.{sh,bat}` — push every active submodule plus the umbrella to both `origin` (Gitea) and `github` (GitHub).
- `scripts/pull-all.{sh,bat}` — pull latest from Gitea on every submodule plus the umbrella.

Errors are printed inline and don't halt the run.

## Specs and plans

In-flight design specs live in `docs/superpowers/specs/` and implementation plans in `docs/superpowers/plans/`. Both are scaffolding — distilled into the plan header on spec→plan handoff, then deleted at branch-finish. Lasting design rationale folds into per-skill `SKILL.md` and `README.md` files.
```

- [x] **Step 2: Verify**

```bash
test -f CLAUDE.md && echo "OK ($(wc -l < CLAUDE.md) lines)"
head -3 CLAUDE.md
```

Expected: `OK (~50 lines)` and the first three lines starting with `# skills-dev — Claude Code instructions`.

---

### Task 15: Commit the CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` staged for commit.

- [x] **Step 1: Stage and commit**

```bash
git add CLAUDE.md
git -c commit.gpgsign=false commit -m "docs: add CLAUDE.md documenting new-skill submodule workflow

Closes the gap flagged during the running-spikes brainstorm — skills-dev
had no in-tree documentation of the new-skill-needs-new-repo workflow.
Cross-references the existing memory note for concrete steps."
```

- [x] **Step 2: Verify**

```bash
git log --oneline -2
```

Expected: two recent commits — the running-spikes submodule add (Task 13) and the CLAUDE.md (Task 15).

---

## Phase 5: Push to all hosts

### Task 16: Run `scripts/push-all.sh`

**Files:** none modified — pushes only.

- [ ] **Step 1: Push everything**

```bash
./scripts/push-all.sh
```

Expected output:
- For each existing submodule: `=== <name> ===` followed by `-> origin` and `-> github` push lines (likely "Everything up-to-date" since they haven't changed).
- For `running-spikes`: a real push of the gitlink commit on the submodule (already done in Tasks 8 & 11) — push-all should show "Everything up-to-date" too because Task 11 pushed `github`.
- For the index (`=== skills-dev (index) ===`): real pushes to `origin` and `github` carrying the new submodule pointer + `CLAUDE.md`.

Inspect for any `FAILED:` lines.

- [ ] **Step 2: Verify GitHub side received the index update**

```bash
gh repo view mtschoen/skills-dev --json url
git ls-remote https://github.com/mtschoen/skills-dev.git HEAD | head -1
git rev-parse HEAD
```

The two SHAs (`ls-remote HEAD` and local `HEAD`) should match.

---

### Task 17: Final smoke test

**Files:** none modified.

- [ ] **Step 1: Confirm the skill is installable and present in `~/.claude/skills/`**

```bash
./install-skills.sh -y running-spikes
ls ~/.claude/skills/running-spikes/SKILL.md
head -3 ~/.claude/skills/running-spikes/SKILL.md
```

Expected: SKILL.md present in the install dir; first three lines are the YAML frontmatter (`---`, `name: running-spikes`, `description: ...`).

- [ ] **Step 2: Confirm the skill registry shows it (next session start)**

This step is **not automated** — it requires a fresh Claude Code session. After the install, on next session start, the skill should appear in the available-skills list as:

> `running-spikes: Use when about to do extended Read/Grep/thinking on a question whose answer is observable behavior of an external system...`

Note this manually as a follow-up verification; do not block the plan completion on it.

- [ ] **Step 3: Update the auto-memory MEMORY.md to reflect the new skill**

The auto-memory at `C:/Users/mtsch/.claude/projects/C--Users-mtsch-skills-dev/memory/MEMORY.md` should get a one-line entry. Append a project-type note (since this is project-scoped to skills-dev):

```bash
echo "- [running-spikes skill](project_running_spikes_skill.md) — installed at ~/.claude/skills/running-spikes/; flips Claude default toward action; throwaway scratch in .claude/spikes/<slug>/, breadcrumbs in ~/.claude/notes/spike_<slug>.md + curated registry" >> C:/Users/mtsch/.claude/projects/C--Users-mtsch-skills-dev/memory/MEMORY.md
```

Then create the project memory file:

```bash
cat > C:/Users/mtsch/.claude/projects/C--Users-mtsch-skills-dev/memory/project_running_spikes_skill.md <<'EOF'
---
name: running-spikes skill
description: Behavioral skill that flips Claude default toward running code over reading more for observable-behavior questions about external systems
type: project
---

Installed at `~/.claude/skills/running-spikes/`. Source repo: `schoen/skills-running-spikes` (Gitea, primary), `mtschoen/skills-running-spikes` (GitHub).

**Why:** Claude over-relies on Read/Grep/thinking when running code would resolve the question faster. Skill teaches it to spike instead, within tight gates so it doesn't wander.

**How to apply:**
- Phase-agnostic: fires during brainstorming, plan-writing, and mid-implementation.
- Tiered: small in-place probes announce-and-go; new project templates / package installs ask first.
- Default-throwaway scratch in `.claude/spikes/<slug>/` (gitignored).
- Breadcrumbs in `~/.claude/notes/spike_<slug>.md`; curated index in `~/.claude/notes/spike_registry.md`.
- Suppressed when: this codebase, subjective/design, prior-spiked, user said "just answer."
- "Web-search" trigger parked because of the project's UserPromptSubmit hook conflict — revisit when hook is retuned.

**Open follow-ups:**
- Eval harness deferred for v1 (placeholder in `running-spikes/evals/`).
- Self-application risk — behavioral skills sometimes don't transfer to the agent that authored them. Watch for user surfacing "you're still reading instead of running" in the first few sessions.
EOF
```

- [ ] **Step 4: Done — report to user**

Brief report:
- New repo `schoen/skills-running-spikes` (Gitea) and `mtschoen/skills-running-spikes` (GitHub) created.
- Submodule added under `skills-dev/running-spikes/` with the relative-URL convention.
- `skills-dev/CLAUDE.md` added documenting the new-skill workflow.
- Installed locally; ready to use on next session start.
- Eval harness deferred — placeholder in `running-spikes/evals/`.
- Auto-memory updated.

---

## Out of scope (intentional deferrals)

- **Running-spikes eval harness.** Placeholder only. The skill's behavioral character makes self-application brittle (per `feedback_skill_self_application.md`); qualitative real-session feedback matters more than n=1 evals (per `feedback_no_iteration_on_n1.md`). Eval harness lands in a follow-up plan once the skill has been used in a few real sessions.
- **Re-introducing the web-search trigger.** Parked until the user's UserPromptSubmit WebSearch hook is retuned (e.g., made conditional or scoped to specific moments). The other three signals carry the action-bias for v1.
- **Auto-cleanup of `.claude/spikes/<slug>/` dirs.** Skill doesn't auto-delete scratch; relies on the user (or the `wrap` skill) to clean. Acceptable for v1.
- **Cross-machine spike-note sync.** `~/.claude/notes/` is already synced via `~/.claude/sync-memory.py` per the user's global CLAUDE.md, so per-topic notes propagate between chonkers and llamabox without skill-specific work. No new infrastructure needed.
